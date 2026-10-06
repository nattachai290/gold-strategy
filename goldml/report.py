"""Markdown summary of a batch of results."""
from __future__ import annotations


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
