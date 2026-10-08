# Research journal

Newest entry first. Each run: plan → result → what was learned → next step.

## 2026-10-08 — J006 R000 attempt 2 failed (throttling); 130/281 months cached

**Result.** Six fetch runs over 3 days on the runner's Windows host. The
browser User-Agent removed the 429s, but the feed still throttles: final run
had 108 retries (503 x49, connection timeout x46, reset x13). Three runs died
after 8 tries, which used up the 3-rerun budget. 130 months (2003-05 ..
2014-02) are in the runner's local `raw/` cache. Throughput swings from 2 to
76 months per run, by hour. The runner also found that its harness kills
background shells after ~30-40 min, and switched to detached processes.

**Learned.** Throttle windows last tens of minutes; a 5-minute cap with 8
tries cannot wait them out. A fixed rerun count is the wrong stop rule when
every run makes progress.

**Changed (planner).** 12 tries per file, waits up to 15 min, 3 s between
requests; `python -m goldml.dukascopy status` reports cached months. New stop
rule: keep resuming while runs add months; stop only after 2 runs in a row add
nothing, or after 3 days. 30 synthetic tests.

**Next.** R000 attempt 3 on the same machine (keeps the cache). If the feed
stays this slow, fallback options: fetch from another network, or start the
XAU work on GLD and switch when the snapshot lands.

## 2026-10-06 — J005 R000 attempt 1 failed (HTTP 429); fetch hardened

**Result.** Runner (Windows 11, Python 3.13) got HTTP 429 on the 2nd file.
Its probes: 9/9 requests with Python's default User-Agent -> 429; a browser
User-Agent -> 200 (then 503 / connection resets when repeated quickly). No
snapshot was created. Separately, pytest only passed with `PYTHONUTF8=1`:
`analysis.md` (with ✓/✗) was written in cp1252.

**Learned.** The datafeed filters default clients and throttles bursts; a
5-try / 31 s backoff is far too short. Also found by review: on Windows,
pandas writes CSV with CRLF and git may convert line endings, so snapshot
hashes made on Windows would not match a Linux restore.

**Changed (planner).** `_get`: browser User-Agent, 8 tries, backoff 5 s x 2^k
(cap 5 min) or `Retry-After`; 1 s pause between requests; raw `.bi5` cache in
`data/snapshot_xau/raw/` (gitignored) so a rerun resumes; all text output
UTF-8 with LF; snapshot CSVs written with `\n`; `.gitattributes` keeps
`data/**` byte-exact. 4 new synthetic tests (29 total).

**Next.** R000 attempt 2 (`prompts/R000.md`), allowing up to 3 resumed reruns.

## 2026-10-06 — J004 Result analyzer

- Owner asked for an analyzer that also says how to improve. Built
  `goldml/analyze.py`: fold consistency, decay, train-vs-OOS skill, cost drag,
  exposure, importance stability -> verdict ACCEPT / OVERFIT / NO_EDGE /
  FRAGILE plus rule-based "Next" ideas. Rejected a single weighted quality
  score: arbitrary weights, and one fatal failure can hide behind a high
  total. Gates stay pass/fail.
- Runs now also save `folds.csv` (train and OOS AUC/IC per fold) and
  `importance.csv` (per-fold feature importance).
- Guardrail: every "Next" is a new trial. Parameter sensitivity is now
  required before sealing a candidate (PROTOCOL).
- Synthetic check: a deep LightGBM on a random walk gets OVERFIT (train AUC
  1.00, OOS 0.50); a logistic on a planted 5-day signal gets ACCEPT.
- Each dev run now writes `analysis.md` itself at the end, so every pushed
  run arrives complete (summary, leaderboard, analysis). Holdout runs get no
  analysis. CLI wiring covered by a synthetic end-to-end test (25 tests).

## 2026-10-06 — J003 Plan: switch to XAUUSD (Dukascopy), fix FRED lags

- Owner wants XAU itself. Dukascopy is blocked for the planner, but the runner
  downloads, so: `goldml/dukascopy.py` (decoder for hourly bid/ask `.bi5`
  candles, H1 -> daily bars at a 13:00 UTC cut with a 1-hour execution delay)
  and `prompts/R000.md` (data-only run). Decoder, weekend mapping and the
  no-look-ahead property of the daily bars are covered by synthetic tests;
  the price scale (1000) and field order are checked on the real data by
  `validate_h1` (median price range, OHLC consistency).
- Hourly data also opens intraday models later.
- Found while doing this: a one-row FRED lag was look-ahead for two series.
  H.15 rates for day d appear ~16:15 ET on d+1 (after the decision), and the
  broad USD index is released weekly. Now 2 rows for DFII10/T10YIE, 8 for
  DTWEXBGS, 1 for VIX. Fixed before any market run.
- R001 is on hold until the R000 snapshot is reviewed; it will run on XAU.
- Owner: do not commit data (size). XAU data is gitignored; only the manifest
  with hashes is committed and each run re-downloads and verifies
  (`restore`). Risk noted: FRED or Dukascopy revisions would break the hash;
  that is treated as a new snapshot event, not ignored. The small GLD
  snapshot (0.7 MB) stays committed as the fallback.
- Question for owner: is 21:00 Bangkok a time they can actually trade? The
  cut hour is a parameter and can change before R001 without a new download.

## 2026-10-06 — J002 Data check: GLD vs world spot gold

Owner asked whether GLD matches world spot. Compared GLD close with Alpha
Vantage daily XAU spot (USD/oz), dev period only (2011-06-01 .. 2023-12-29,
3167 common days; holdout not touched):

- Level: GLD/spot ratio 0.0973 -> 0.0924, drift -0.41%/yr = GLD expense
  ratio (0.40%). GLD under-states spot by that much per year: conservative.
- Return correlation: daily 0.92, weekly 0.965, monthly 0.996. Tracking error
  6.1% / 4.2% / 1.5% per year.
- Daily gap is a timestamp effect: the spot print is taken at a different time
  of day than the GLD 16:00 NY close (lag/lead correlations ~0).
- Consequence: over weeks and months GLD is the spot price. Day to day, what
  the backtest earns depends on trading at the time it assumes (GLD open,
  09:30 NY = 20:30/21:30 Bangkok). Short-horizon models (h=1) are the most
  exposed to this; a live rule must execute in that window.
- Alpha Vantage spot starts 2011-06, too short for the 2005 warm-up, so GLD
  stays the research series. Possible follow-up: re-run a finished candidate
  on spot as a robustness check (planned, journaled, counted as a trial).

## 2026-10-06 — J001 Owner decision: long-only spot

- Owner trades long-only spot gold. Harness changed before any market run:
  positions clipped to `[0, 1]`, model output maps to long/flat, cost
  profiles replaced by `spot` (10 bps one-way, primary) and `tight` (2 bps),
  no carry. Baseline `mom250_long_short` became `mom250_long_flat`.
- Consequence: the goal is market timing. Buy & hold gold over 2010-2023 is
  the hurdle; a model must earn a higher Sharpe after spread, not just a
  positive one.
- Account currency is USD (XAUUSD spot), so P&L is in USD and no THB FX
  risk is modelled. GLD daily (USD) stays the price proxy.
- Spread from the owner's venue (MTS Gold via Dime!, quote 2026-10-06;
  corrected from a YLG quote the owner sent first): $0.35/oz on $4,131 =
  0.85 bps round trip. Primary cost set to 2 bps one-way (~5x observed, margin for off-hours, slippage, proxy timing); `wide` 10 bps kept
  as an ungated sensitivity. G4 now stresses the primary profile only.
  Set before R001 ran. One quote is thin evidence: if the owner can share
  quotes at other times (US open, Asia night, news), revisit.

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

**Open question for owner:** trading venue — answered in J001 (long-only spot).
