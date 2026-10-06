"""Result analyzer: diagnoses recorded results and proposes what to try next.

Runs on files already written by a run (metrics.json, oos.csv, folds.csv,
importance.csv), so the planner may run it. It never reads market data and
never touches the holdout.

    python -m goldml.analyze results/R001        # writes results/R001/analysis.md

Verdicts (one per experiment):
    ACCEPT    all gates pass, folds mostly positive, no decay -> candidate for sensitivity run
    OVERFIT   learns the training set but not out of sample, or luck explains it (DSR)
    NO_EDGE   no out-of-sample skill and no timing value over buy & hold
    FRAGILE   some edge, but it breaks under costs, sub-periods, folds, time or drawdown

Every recommendation is a NEW experiment (a new trial, written and committed
before it runs). It is never a reason to re-run the same experiment.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

from . import metrics as M
from .backtest import COST_PROFILES, PRIMARY_PROFILE, backtest

AUC_NO_SKILL = 0.51       # OOS AUC at or below this = no skill
AUC_GAP_OVERFIT = 0.08    # train AUC - OOS AUC above this = memorising
IC_NO_SKILL = 0.01
IC_GAP_OVERFIT = 0.05
FOLD_OK = 0.6             # share of folds that must beat buy & hold for ACCEPT
TURNOVER_HIGH = 50        # one-way turnover per year


def _sharpe(x) -> float:
    x = np.asarray(x, dtype=float)
    return M.sharpe(x) if len(x) > 2 else float("nan")


def diagnose(exp_dir: Path) -> dict:
    m = json.loads((exp_dir / "metrics.json").read_text(encoding="utf-8"))
    oos = pd.read_csv(exp_dir / "oos.csv", index_col=0, parse_dates=True)
    folds = pd.read_csv(exp_dir / "folds.csv") if (exp_dir / "folds.csv").exists() else pd.DataFrame()
    imp = pd.read_csv(exp_dir / "importance.csv", index_col=0) if (exp_dir / "importance.csv").exists() else pd.DataFrame()

    bt = backtest(oos["pos"], oos["R"], COST_PROFILES[PRIMARY_PROFILE])
    bh = oos["R"]
    excess = bt["net"] - bh
    d: dict = {"experiment": m["experiment"], "run_id": m["run_id"], "gates": m["gates"],
               "pass_all": m["pass_all"]}

    # -- costs and exposure
    prim = m["profiles"][PRIMARY_PROFILE]
    d["net_sharpe"], d["gross_sharpe"] = prim["sharpe"], prim["gross_sharpe"]
    d["bh_sharpe"] = _sharpe(bh)
    d["turnover_pa"], d["exposure"] = prim["turnover_pa"], prim["exposure"]
    d["cost_drag_sharpe"] = d["gross_sharpe"] - d["net_sharpe"]
    d["corr_with_bh"] = float(np.corrcoef(bt["net"], bh)[0, 1]) if bt["net"].std() > 0 else 0.0
    d["p_beats_best_baseline"] = m["stats"]["p_beats_best_baseline"]
    d["dsr"] = m["stats"]["deflated_sharpe"]

    # -- fold consistency (each walk-forward test block)
    g = pd.DataFrame({"net": bt["net"], "ex": excess, "fold": oos["fold"]}).groupby("fold")
    per_fold = pd.DataFrame({"net_ret": g["net"].apply(lambda x: float(np.prod(1 + x) - 1)),
                             "excess_ret": g["ex"].sum()})
    d["n_folds"] = len(per_fold)
    d["folds_positive"] = float((per_fold["net_ret"] > 0).mean())
    d["folds_beat_bh"] = float((per_fold["excess_ret"] > 0).mean())

    # -- decay over time (excess over buy & hold, per calendar year)
    yearly = excess.groupby(excess.index.year).sum()
    d["yearly_excess"] = {int(k): round(float(v), 4) for k, v in yearly.items()}
    if len(yearly) >= 4:
        lr = stats.linregress(np.arange(len(yearly)), yearly.to_numpy())
        d["decay_slope_pa"], d["decay_t"] = float(lr.slope), float(lr.slope / lr.stderr) if lr.stderr > 0 else 0.0
    else:
        d["decay_slope_pa"], d["decay_t"] = 0.0, 0.0
    half = len(bt) // 2
    d["sharpe_first_half"], d["sharpe_second_half"] = _sharpe(bt["net"][:half]), _sharpe(bt["net"][half:])

    # -- train vs out-of-sample skill
    if "oos_auc" in folds:
        d["skill_metric"] = "auc"
        d["train_skill"], d["oos_skill"] = float(folds["train_auc"].mean()), float(folds["oos_auc"].mean())
        d["folds_oos_skill"] = float((folds["oos_auc"] > 0.5).mean())
        no_skill, gap_lim = AUC_NO_SKILL, AUC_GAP_OVERFIT
    elif "oos_ic" in folds:
        d["skill_metric"] = "ic"
        d["train_skill"], d["oos_skill"] = float(folds["train_ic"].mean()), float(folds["oos_ic"].mean())
        d["folds_oos_skill"] = float((folds["oos_ic"] > 0).mean())
        no_skill, gap_lim = IC_NO_SKILL, IC_GAP_OVERFIT
    else:
        d["skill_metric"], d["train_skill"], d["oos_skill"], d["folds_oos_skill"] = None, np.nan, np.nan, np.nan
        no_skill, gap_lim = np.nan, np.nan
    d["skill_gap"] = d["train_skill"] - d["oos_skill"]

    # -- feature importance stability
    if not imp.empty and len(imp) >= 3:
        a = imp.abs()
        rc = a.T.corr(method="spearman").to_numpy()
        d["importance_stability"] = float(rc[np.triu_indices_from(rc, 1)].mean())
        top = a.mean().sort_values(ascending=False).head(5)
        sign_consistency = (np.sign(imp) == np.sign(imp.mean())).mean()
        d["top_features"] = [{"feature": f, "mean_abs": round(float(v), 4),
                              "sign_consistency": round(float(sign_consistency[f]), 2)} for f, v in top.items()]
    else:
        d["importance_stability"], d["top_features"] = np.nan, []

    # -- flags and verdict
    gates = m["gates"]
    flags = []
    no_oos_skill = d["skill_metric"] is not None and d["oos_skill"] <= no_skill
    if no_oos_skill and d["skill_gap"] > gap_lim:
        flags.append("memorising")
    if not gates["G2_deflated"] and gates["G1_sharpe"]:
        flags.append("luck_not_excluded")
    if no_oos_skill and d["p_beats_best_baseline"] < 0.6:
        flags.append("no_skill")
    if "no_skill" not in flags and d["gross_sharpe"] > d["bh_sharpe"] and d["net_sharpe"] <= d["bh_sharpe"]:
        flags.append("cost_killed")
    if d["turnover_pa"] > TURNOVER_HIGH:
        flags.append("high_turnover")
    if d["exposure"] > 0.9:
        flags.append("mostly_buy_and_hold")
    if d["exposure"] < 0.3:
        flags.append("mostly_flat")
    if d["folds_beat_bh"] < 0.5:
        flags.append("inconsistent_folds")
    if d["decay_t"] < -2 or (d["sharpe_first_half"] > 0.5 and d["sharpe_second_half"] < 0):
        flags.append("decaying")
    if not np.isnan(d["importance_stability"]) and d["importance_stability"] < 0.3:
        flags.append("unstable_features")
    for gname, flag in (("G4_cost_stress", "fails_cost_stress"), ("G5_stability", "fails_subperiods"),
                        ("G6_drawdown", "deep_drawdown")):
        if not gates[gname]:
            flags.append(flag)
    d["flags"] = flags

    if m["pass_all"] and d["folds_beat_bh"] >= FOLD_OK and "decaying" not in flags:
        verdict = "ACCEPT"
    elif "memorising" in flags or "luck_not_excluded" in flags:
        verdict = "OVERFIT"
    elif "no_skill" in flags:
        verdict = "NO_EDGE"
    else:
        verdict = "FRAGILE"
    d["verdict"] = verdict
    d["next"] = recommendations(d)
    return d


RECS = {
    "memorising": "Model fits training noise. Next: stronger regularisation (logit C 0.01-0.03; LightGBM "
                  "num_leaves 3-5, min_child_samples 400+), fewer features (keep only stable top features).",
    "luck_not_excluded": "Sharpe is real-looking but explained by the number of trials. Next: do not add more "
                         "variants of this family; only a clearly larger effect can pass G2.",
    "no_skill": "These features carry no out-of-sample information at this horizon. Tuning will not fix it. "
                "Next: change the information (intraday H1 features, cross-asset: silver, USD intraday, rates "
                "surprises, ETF flows/COT) or change the target (e.g. predict large drawdowns to avoid).",
    "cost_killed": "Gross edge exists but costs remove it. Next: cut trading: longer horizon (h=10/20), "
                   "deadband on P(up) (e.g. long > 0.55, flat < 0.45, else hold), minimum holding period.",
    "high_turnover": "Trades too often for a daily edge. Next: smoothing / hysteresis on the signal, longer horizon.",
    "mostly_buy_and_hold": "Model is almost always long, so it is buy & hold with extra costs. Next: reframe as "
                           "'when to step out': target = drawdown / large down move over h days.",
    "mostly_flat": "Model is rarely long and misses gold's drift. Next: check class balance and threshold; "
                   "default to long and only exit on a strong down signal.",
    "inconsistent_folds": "Works in some periods only (regime dependent). Next: add regime features (vol regime, "
                          "trend regime, real-rate regime) or a rolling train window (3-5 years).",
    "decaying": "Edge fades over time. Next: rolling train window or recency weights; check whether the edge "
                "was arbitraged away (if so, drop the idea).",
    "unstable_features": "Different features matter in each fold: the model chases noise. Next: shrink the feature "
                         "set to those with stable importance and consistent sign.",
    "fails_cost_stress": "Too thin to survive 2x costs. Next: same as cost_killed - trade less.",
    "fails_subperiods": "Profit comes from one era. Next: inspect yearly_excess; regime features or a narrower claim.",
    "deep_drawdown": "Drawdown too deep. Next: volatility targeting (scale exposure by 1/vol) or an exit rule.",
}


def recommendations(d: dict) -> list[str]:
    if d["verdict"] == "ACCEPT":
        return ["Passes. Next: parameter-sensitivity run (neighbouring settings must keep most of the Sharpe), "
                "then seal as a candidate for the one-shot holdout."]
    return [f"[{f}] {RECS[f]}" for f in d["flags"] if f in RECS]


def _fmt(x, nd=2):
    return "n/a" if x is None or (isinstance(x, float) and np.isnan(x)) else f"{x:.{nd}f}"


def analyze_run(run_dir: Path) -> str:
    ds = [diagnose(p.parent) for p in sorted(run_dir.glob("*/metrics.json"))]
    lines = [f"# Analysis of {run_dir.name}", "",
             "Diagnostics on recorded dev-period results. Every 'Next' item is a NEW trial, "
             "written and committed before it runs.", "",
             "| experiment | verdict | net Sharpe | B&H Sharpe | gross | train/OOS skill | folds beat B&H | exposure | turnover/yr |",
             "|---|---|---|---|---|---|---|---|---|"]
    for d in ds:
        sk = f"{_fmt(d['train_skill'], 3)} / {_fmt(d['oos_skill'], 3)} ({d['skill_metric']})"
        lines.append(f"| {d['experiment']} | **{d['verdict']}** | {_fmt(d['net_sharpe'])} | {_fmt(d['bh_sharpe'])} "
                     f"| {_fmt(d['gross_sharpe'])} | {sk} | {d['folds_beat_bh']:.0%} | {d['exposure']:.0%} "
                     f"| {d['turnover_pa']:.0f} |")
    for d in ds:
        lines += ["", f"## {d['experiment']} — {d['verdict']}", "",
                  f"- flags: {', '.join(d['flags']) or 'none'}",
                  f"- gates: " + " ".join(f"{k.split('_')[0]}{'✓' if v else '✗'}" for k, v in d["gates"].items()),
                  f"- DSR {_fmt(d['dsr'])}, P(beats best baseline) {_fmt(d['p_beats_best_baseline'])}",
                  f"- folds: {d['n_folds']}, net positive {d['folds_positive']:.0%}, beat B&H {d['folds_beat_bh']:.0%}; "
                  f"OOS skill > chance in {_fmt(d['folds_oos_skill'] * 100, 0)}% of folds",
                  f"- decay: Sharpe first half {_fmt(d['sharpe_first_half'])}, second half {_fmt(d['sharpe_second_half'])}, "
                  f"trend of yearly excess t={_fmt(d['decay_t'])}",
                  f"- yearly excess vs B&H: " + ", ".join(f"{y}: {v:+.1%}" for y, v in d["yearly_excess"].items()),
                  f"- cost drag on Sharpe {_fmt(d['cost_drag_sharpe'])}, correlation with B&H {_fmt(d['corr_with_bh'])}",
                  f"- feature importance stability (rank corr across folds) {_fmt(d['importance_stability'])}"]
        if d["top_features"]:
            lines.append("- top features: " + ", ".join(
                f"{t['feature']} ({t['mean_abs']}, sign {t['sign_consistency']:.0%})" for t in d["top_features"]))
        lines += ["", "**Next:**"] + [f"- {r}" for r in d["next"]]
    return "\n".join(lines) + "\n"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("run_dir", type=Path)
    a = ap.parse_args(argv)
    md = analyze_run(a.run_dir)
    (a.run_dir / "analysis.md").write_text(md, encoding="utf-8", newline="\n")
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass
    print(md)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
