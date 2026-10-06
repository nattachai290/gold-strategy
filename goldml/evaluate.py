"""Experiment definition, walk-forward evaluation, baselines and gates."""
from __future__ import annotations

import csv
import hashlib
import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

import numpy as np
import pandas as pd

from . import metrics as M
from .backtest import COST_PROFILES, LONG_ONLY, PRIMARY_PROFILE, backtest, forward_log_return, next_period_return
from .features import build_features
from .splits import train_slice, walk_forward

FIRST_TEST_START = "2010-01-01"


@dataclass
class Experiment:
    name: str                                   # unique, e.g. "E001_logit_h5"
    features: list[str]
    horizon: int                                # label horizon in trading days
    make_model: Callable[[], object]            # fresh sklearn-style estimator
    target: str = "direction"                   # "direction" -> predict_proba, "return" -> predict
    to_position: Callable[[np.ndarray], np.ndarray] | None = None
    smooth: bool = True                         # average the last `horizon` positions (overlapping book)
    test_months: int = 6
    train_window: int | None = None             # None = expanding
    first_test_start: str = FIRST_TEST_START
    params: dict = field(default_factory=dict)  # anything that defines the trial, for hashing
    description: str = ""

    def config_hash(self) -> str:
        d = {k: v for k, v in asdict(self).items() if k not in ("make_model", "to_position", "description")}
        d["model"] = repr(self.make_model())
        return hashlib.sha256(json.dumps(d, sort_keys=True, default=str).encode()).hexdigest()[:10]


def default_position(pred: np.ndarray, target: str, deadband: float = 0.0) -> np.ndarray:
    centre = 0.5 if target == "direction" else 0.0
    x = pred - centre
    if LONG_ONLY:
        return np.where(x > deadband, 1.0, 0.0)
    return np.where(np.abs(x) > deadband, np.sign(x), 0.0)


# --------------------------------------------------------------------------- walk-forward

def walk_forward_predict(exp: Experiment, panel: pd.DataFrame) -> pd.DataFrame:
    X = build_features(panel)[exp.features]
    y = forward_log_return(panel, exp.horizon)
    R = next_period_return(panel)
    folds = walk_forward(panel.index, exp.first_test_start, exp.horizon, exp.test_months)
    if not folds:
        raise ValueError("no walk-forward folds; check dates")
    parts = []
    for k, fold in enumerate(folds):
        tr = train_slice(fold, exp.train_window)
        Xtr, ytr = X.iloc[tr], y.iloc[tr]
        ok = Xtr.notna().all(axis=1) & ytr.notna()
        Xtr, ytr = Xtr[ok], ytr[ok]
        model = exp.make_model()
        if exp.target == "direction":
            model.fit(Xtr.to_numpy(), (ytr > 0).astype(int).to_numpy())
        else:
            model.fit(Xtr.to_numpy(), ytr.to_numpy())
        Xte = X.iloc[fold.test_start:fold.test_end]
        valid = Xte.notna().all(axis=1).to_numpy()
        pred = np.full(len(Xte), np.nan)
        if valid.any():
            xv = Xte.to_numpy()[valid]
            pred[valid] = model.predict_proba(xv)[:, 1] if exp.target == "direction" else model.predict(xv)
        parts.append(pd.DataFrame({"fold": k, "pred": pred, "n_train": int(ok.sum())}, index=Xte.index))
    oos = pd.concat(parts)
    to_pos = exp.to_position or (lambda p: default_position(p, exp.target))
    raw = pd.Series(to_pos(oos["pred"].to_numpy()), index=oos.index, dtype=float).fillna(0.0).clip(0.0 if LONG_ONLY else -1.0, 1.0)
    raw[oos["pred"].isna()] = 0.0
    oos["raw_pos"] = raw
    oos["pos"] = raw.rolling(exp.horizon, min_periods=1).mean() if exp.smooth and exp.horizon > 1 else raw
    oos["R"] = R.reindex(oos.index)
    return oos.dropna(subset=["R"])


# --------------------------------------------------------------------------- baselines

def baseline_positions(panel: pd.DataFrame) -> dict[str, pd.Series]:
    c = np.log(panel["close"])
    return {
        "buy_hold": pd.Series(1.0, index=panel.index),
        "ma200_long_flat": (c > c.rolling(200).mean()).astype(float),
        "mom250_long_flat": (c.diff(250) > 0).astype(float),
    }


# --------------------------------------------------------------------------- registry

def read_registry(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame(columns=["run_id", "experiment", "config_hash", "sharpe_primary"])
    return pd.read_csv(path)


def append_registry(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    new = not path.exists()
    with path.open("a", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        if new:
            w.writeheader()
        w.writerows(rows)


# --------------------------------------------------------------------------- evaluation + gates

GATES = {
    "G1_sharpe": "primary net Sharpe >= 0.5 and bootstrap 95% CI lower bound > 0",
    "G2_deflated": "deflated Sharpe ratio >= 0.95 given all registered trials",
    "G3_beats_baselines": "P(Sharpe > best baseline Sharpe) >= 0.90 (paired block bootstrap, same costs)",
    "G4_cost_stress": "net Sharpe > 0 under 2x primary costs",
    "G5_stability": "positive net return in >= 3 of 4 equal sub-periods",
    "G6_drawdown": "max drawdown >= -35%",
}


def evaluate_oos(oos: pd.DataFrame, panel: pd.DataFrame, n_trials: int, trial_sharpes, seed: int = 0) -> dict:
    out: dict = {"profiles": {}, "baselines": {}}
    for name, prof in COST_PROFILES.items():
        bt = backtest(oos["pos"], oos["R"], prof)
        bt2 = backtest(oos["pos"], oos["R"], prof, cost_mult=2.0)
        s = M.summary(bt)
        s["sharpe_ci95"] = M.sharpe_ci(bt["net"], seed=seed)
        s["sharpe_2x_cost"] = M.sharpe(bt2["net"])
        s["gross_sharpe"] = M.sharpe(bt["gross"])
        out["profiles"][name] = s

    prim = backtest(oos["pos"], oos["R"], COST_PROFILES[PRIMARY_PROFILE])
    base_bts = {}
    for bname, bpos in baseline_positions(panel).items():
        bbt = backtest(bpos.reindex(oos.index).fillna(0.0), oos["R"], COST_PROFILES[PRIMARY_PROFILE])
        base_bts[bname] = bbt
        out["baselines"][bname] = M.summary(bbt)
    best = max(base_bts, key=lambda k: M.sharpe(base_bts[k]["net"]))
    p_beat = M.prob_sharpe_greater(prim["net"], base_bts[best]["net"], seed=seed)
    dsr = M.deflated_sharpe(prim["net"], n_trials, trial_sharpes)
    chunks = np.array_split(prim["net"].to_numpy(), 4)
    sub = [float(np.prod(1 + c) - 1) for c in chunks]

    p = out["profiles"][PRIMARY_PROFILE]
    out["stats"] = {"best_baseline": best, "p_beats_best_baseline": p_beat, "deflated_sharpe": dsr,
                    "n_trials": n_trials, "subperiod_returns": sub}
    out["gates"] = {
        "G1_sharpe": p["sharpe"] >= 0.5 and p["sharpe_ci95"][0] > 0,
        "G2_deflated": dsr >= 0.95,
        "G3_beats_baselines": p_beat >= 0.90,
        "G4_cost_stress": p["sharpe_2x_cost"] > 0,
        "G5_stability": sum(x > 0 for x in sub) >= 3,
        "G6_drawdown": p["max_dd"] >= -0.35,
    }
    out["gates"] = {k: bool(v) for k, v in out["gates"].items()}
    out["pass_all"] = all(out["gates"].values())
    return out


def run_experiments(exps: list[Experiment], panel: pd.DataFrame, run_id: str, out_dir: Path,
                    registry: Path, register: bool = True, meta: dict | None = None) -> list[dict]:
    """Evaluate a batch. All experiments in the batch count as trials (registered first)."""
    reg = read_registry(registry)
    oos_all = {e.name: walk_forward_predict(e, panel) for e in exps}
    prim = COST_PROFILES[PRIMARY_PROFILE]
    batch_sharpes = {n: M.sharpe(backtest(o["pos"], o["R"], prim)["net"]) for n, o in oos_all.items()}
    n_trials = len(reg) + len(exps)
    trial_sharpes = list(reg["sharpe_primary"].astype(float)) + list(batch_sharpes.values())

    results = []
    ts = datetime.now(timezone.utc).isoformat(timespec="seconds")
    for e in exps:
        oos = oos_all[e.name]
        res = evaluate_oos(oos, panel, n_trials, trial_sharpes)
        res.update({"run_id": run_id, "experiment": e.name, "config_hash": e.config_hash(),
                    "description": e.description, "horizon": e.horizon, "features": e.features,
                    "params": e.params, "model": repr(e.make_model()), "created_utc": ts, **(meta or {})})
        d = out_dir / e.name
        d.mkdir(parents=True, exist_ok=True)
        (d / "metrics.json").write_text(json.dumps(res, indent=2, default=float) + "\n")
        oos.to_csv(d / "oos.csv", float_format="%.6g")
        results.append(res)
    if register:
        append_registry(registry, [{
            "run_id": run_id, "experiment": r["experiment"], "config_hash": r["config_hash"],
            "sharpe_primary": round(batch_sharpes[r["experiment"]], 6),
            "created_utc": ts, "pass_all": r["pass_all"],
        } for r in results])
    return results
