"""Markdown summary of a batch of results, and the all-time leaderboard."""
from __future__ import annotations

from pathlib import Path

import pandas as pd


def _f(x, pct=False):
    return f"{x:+.1%}" if pct else f"{x:.2f}"


def batch_report(results: list[dict], run_id: str) -> str:
    lines = [f"# Run {run_id}", ""]
    if results:
        r0 = results[0]
        lines += [f"- git: `{r0.get('git_sha', '?')}` dirty={r0.get('git_dirty', '?')}",
                  f"- data snapshot: `{r0.get('snapshot', '?')}`  split: `{r0.get('split', '?')}`",
                  f"- trials in registry after this run: {r0['stats']['n_trials']}", ""]
    lines += ["| experiment | net Sharpe (spot) | CI95 | Sharpe wide | 2x cost spot | CAGR spot | MaxDD | exposure | turnover/yr | DSR | P>best base | gates |",
              "|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for r in results:
        c, e, s = r["profiles"]["spot"], r["profiles"]["wide"], r["stats"]
        g = "".join("✓" if v else "✗" for v in r["gates"].values())
        lines.append(f"| {r['experiment']} | {_f(c['sharpe'])} | [{_f(c['sharpe_ci95'][0])}, {_f(c['sharpe_ci95'][1])}] "
                     f"| {_f(e['sharpe'])} | {_f(c['sharpe_2x_cost'])} | {_f(c['cagr'], True)} | {_f(c['max_dd'], True)} "
                     f"| {c['exposure']:.0%} | {c['turnover_pa']:.0f} | {s['deflated_sharpe']:.2f} | {s['p_beats_best_baseline']:.2f} | {g} |")
    if results:
        lines += ["", "Baselines (same OOS dates, spot costs):", "",
                  "| baseline | Sharpe | CAGR | MaxDD |", "|---|---|---|---|"]
        for b, m in results[0]["baselines"].items():
            lines.append(f"| {b} | {_f(m['sharpe'])} | {_f(m['cagr'], True)} | {_f(m['max_dd'], True)} |")
        lines += ["", "Gate order: " + ", ".join(results[0]["gates"].keys())]
    return "\n".join(lines) + "\n"


def leaderboard(registry: Path, top: int = 30) -> str:
    """Every dev trial ever run, best first: gates passed, then primary net Sharpe."""
    t = pd.read_csv(registry)
    t = t.sort_values(["gates_passed", "sharpe_primary"], ascending=False).head(top)
    lines = ["# Leaderboard (development OOS, all trials)", "",
             f"Total trials: {len(pd.read_csv(registry))}. Ranked by gates passed (of 6), then net Sharpe "
             "(spot costs). DSR is as computed at that run; it falls as more trials are added. "
             "Only a row with pass_all=True can become a candidate.", "",
             "| rank | run | experiment | net Sharpe | DSR at run | gates | pass_all |",
             "|---|---|---|---|---|---|---|"]
    for i, r in enumerate(t.itertuples(), 1):
        lines.append(f"| {i} | {r.run_id} | {r.experiment} | {r.sharpe_primary:.2f} | {r.dsr_at_run:.2f} "
                     f"| {r.gates_passed}/6 | {r.pass_all} |")
    return "\n".join(lines) + "\n"
