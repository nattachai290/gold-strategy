# Evaluation protocol

The question: does a model trade gold profitably **after costs**, out of
sample, in a way that is not explained by luck, by the number of things we
tried, or by just holding gold?

## Instrument and data

- **Primary (since J007): XAUUSD** from the Dukascopy public
  feed, hourly bid/ask candles (mid prices), fetched by the runner into
  `data/snapshot_xau/`. Daily bars are built at a fixed UTC cut: decision at
  13:00 UTC (20:00 Bangkok) using bars closed by then, fill at the open of the
  14:00 UTC bar (21:00 Bangkok), see `goldml/dukascopy.py`. The spread at the
  fill bar is kept (`exec_spread_bps`) to check the cost assumption.
  Data files are **not committed** (size, owner's request). Only
  `data/snapshot_xau/manifest.json` is: it pins the month range, the FRED end
  date and SHA-256 of each file. Every run starts with
  `python -m goldml.dukascopy restore`, which re-downloads and must reproduce
  the hashes exactly; a mismatch (e.g. a vendor revision) stops the run and
  becomes a planned, journaled new snapshot.
  Snapshot: 141,968 H1 bars, 2003-05-05 .. 2026-09-30, no missing months;
  manifest hashes reproduced by `restore`.
- Fallback: **GLD** daily OHLCV (Yahoo), 2004-11-18 onward. Chosen
  over `GC=F` because the continuous futures series has 441 rows of
  inconsistent OHLC, zero-volume days and roll gaps; GLD had none.
  Dukascopy XAUUSD intraday is blocked from the planner's environment.
- Macro (FRED): `DFII10` real yield, `T10YIE` breakeven, `DTWEXBGS` broad USD
  (from 2006), `VIXCLS`. Lagged per series for publication delay: H.15 rates
  2 rows, weekly-released USD index 8 rows, VIX 1 row (`FRED_LAGS`).
- Frozen snapshot in `data/snapshot/` with SHA-256 hashes in `manifest.json`.
  `load_raw` refuses tampered files. Snapshot fetched 2026-10-06, last bar 2026-10-02.

## Timing (no look-ahead)

- Row `t` features use data up to the decision time of `t` (GLD: close; XAU: 13:00 UTC cut).
- The position decided at `t` is executed at the **`open` of `t+1`** (GLD:
  next open; XAU: the 14:00 UTC fill) and earns `R_t = open[t+2]/open[t+1] - 1`. Trade cost is charged on the same row.
- Labels: `fwd_h = log(open[t+1+h] / open[t+1])`.
- Walk-forward, expanding window, retrain every 6 months. A training row `t`
  is used only if `t + 1 + h < first test row` (purge + 1 row embargo).
- `tests/test_harness.py` perturbs future rows and checks features and
  out-of-sample positions do not change.

## Periods

| period | dates | use |
|---|---|---|
| warm-up / first training | 2005-01-03 .. 2009-12-31 | training only |
| development OOS | 2010-01-01 .. 2023-12-31 | walk-forward results, gates |
| **holdout** | 2024-01-01 .. 2026-09-30 (end of XAU snapshot) | one shot per sealed candidate |

## Trading constraint and costs

The owner trades **long-only spot gold in USD** (XAUUSD, decided 2026-10-06). Positions are
in `[0, 1]`: fully long or flat in cash, no shorting, no leverage, no swap.
Cash earns nothing in the backtest (conservative). The question therefore is
whether a model can **time** gold better than simply holding it.

| profile | one-way spread+slippage | carry |
|---|---|---|
| `spot` (primary) | 2 bps | 0 |
| `wide` (sensitivity, not gated) | 10 bps | 0 |

Venue: MTS Gold via Dime!, spot in USD. Observed quote 2026-10-06: sell
4,130.48 / buy 4,130.83 USD/oz = $0.35 spread = 0.85 bps round trip. The
primary 2 bps one-way (~5x observed) covers wider off-hours spreads and slippage.
Cross-check from Dukascopy (R000): full bid-ask spread at the 14:00 UTC fill
bar, median by year, was 4.0 bps in 2010 falling to ~1.8-2.6 bps in 2011-2023,
i.e. a half-spread of ~1-2 bps one-way. 2 bps one-way is therefore at or above
the feed's own cost through the whole dev period; the 2x stress (4 bps) is
conservative. Spreads widen sharply at 21-23 UTC (rollover), which the 14:00
fill avoids.
Stress test (G4): primary costs x2.

## Gates (development OOS, primary profile)

A configuration becomes a **candidate** only if all pass:

| gate | rule |
|---|---|
| G1 | net Sharpe >= 0.5 and stationary-bootstrap 95% CI lower bound > 0 |
| G2 | deflated Sharpe ratio >= 0.95, using every trial in `results/trials.csv` |
| G3 | P(Sharpe > best baseline Sharpe) >= 0.90 (paired block bootstrap, same costs) |
| G4 | net Sharpe > 0 under 2x primary costs |
| G5 | positive net return in >= 3 of 4 equal sub-periods |
| G6 | max drawdown >= -35% |

Baselines on the same dates and costs: buy & hold, 200-day MA long/flat,
250-day momentum long/flat. For a long-only timer, buy & hold is the real
hurdle: G3 asks for a higher Sharpe than the best of these.

## Result analyzer

Every dev run writes `results/RNNN/analysis.md` automatically at the end
(`python -m goldml.analyze results/RNNN` regenerates it from the recorded
files; holdout runs get no analysis, so the holdout never feeds tuning).
Per experiment it reports fold consistency (share of walk-forward blocks that
beat buy & hold), decay (yearly excess vs buy & hold, first vs second half),
train vs out-of-sample skill (AUC or rank IC per fold), cost drag, exposure,
and feature-importance stability, then a verdict:

| verdict | meaning |
|---|---|
| ACCEPT | all gates pass, >= 60% of folds beat buy & hold, no decay |
| OVERFIT | learns training data but not OOS, or the Sharpe is explained by the trial count |
| NO_EDGE | no OOS skill and no timing value over buy & hold |
| FRAGILE | some edge, but breaks under costs, sub-periods, folds, time or drawdown |

Each verdict comes with "Next" recommendations. A recommendation is always a
**new** experiment (new name, committed before it runs, counted as a trial).
The analyzer is a guide for what to try, not a licence to re-tune the same
experiment on the same OOS data.

**Parameter sensitivity (required before sealing).** An ACCEPT experiment is
re-run with neighbouring settings (each key parameter one step down and up).
To be sealed, every neighbour must keep net Sharpe > 0 and the median
neighbour must keep >= 50% of the experiment's net Sharpe. Neighbours count
as trials.

## Candidates and holdout

1. Planner writes `candidates/CNNN.py` (the exact frozen `EXPERIMENTS`, one
   entry) and `candidates/CNNN.json` with `{"sealed": true, ...}`, commits both.
2. Runner runs it once with `--split holdout --candidate CNNN`. The open is
   logged in `results/holdout_log.csv`; a second open raises.
3. Holdout success: primary net Sharpe > 0, 2x-cost Sharpe > 0, and Sharpe not
   below buy & hold minus 0.3. The result is reported whatever it is.
4. A candidate that fails the holdout is dead. Lessons go to the journal; the
   next candidate needs a new idea, not a re-tune of the dead one.

## Trial accounting

Every configuration evaluated on development data is a trial, appended to
`results/trials.csv` with its primary net Sharpe. The deflated Sharpe in G2
uses the total count and the dispersion of trial Sharpes (floor 0.3 annual
std when fewer than 5 trials). More trials make G2 harder: be deliberate.
