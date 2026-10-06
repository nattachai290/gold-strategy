# Research journal

Newest entry first. Each run: plan → result → what was learned → next step.

## 2026-10-06 — J000 Harness and data

**Done**
- Harness `goldml/`: frozen snapshot with hash check, as-of macro lag,
  next-open execution, purged expanding walk-forward, two cost profiles,
  bootstrap Sharpe CI, deflated Sharpe with trial registry, six gates,
  holdout guard (sealed candidate, one shot, logged).
- 16 synthetic tests: no look-ahead (features and OOS positions), FRED lag,
  purge, label alignment, cost arithmetic, random walk shows no edge, planted
  edge is found and costs reduce it, trial counting, holdout guard, tamper check.
- Data checks: GLD clean (5502 rows, 2004-11-18 .. 2026-10-02, no OHLC
  issues, gaps only at known market closures). `GC=F` rejected (441
  inconsistent OHLC rows, roll gaps, GLD return corr only 0.89). Dukascopy
  intraday not reachable from the planner environment; Yahoo hourly only
  covers the last 730 days (all inside holdout) — so daily for now.

**Next: R001** (`prompts/R001.md`) — 4 trials, `experiments/e001_first_models.py`:
logistic h=1 / h=5 on price features, LightGBM h=5 / h=20 on price+macro.
Expectation set in advance: most likely no gate passes; the point is to see
where gross edge exists, how much cost and carry take, and how the models
compare with buy & hold over 2010-2023.

**Open question for owner:** trading venue (CFD XAUUSD / futures / ETF) — it
decides the primary cost profile.
