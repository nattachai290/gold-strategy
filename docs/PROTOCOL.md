# Evaluation protocol

The question: does a model trade gold profitably **after costs**, out of
sample, in a way that is not explained by luck, by the number of things we
tried, or by just holding gold?

## Instrument and data

- Traded instrument: **GLD** daily OHLCV (Yahoo), 2004-11-18 onward. Chosen
  over `GC=F` because the continuous futures series has 441 rows of
  inconsistent OHLC, zero-volume days and roll gaps; GLD had none.
  Dukascopy XAUUSD intraday is blocked from the planner's environment.
- Macro (FRED): `DFII10` real yield, `T10YIE` breakeven, `DTWEXBGS` broad USD
  (from 2006), `VIXCLS`. Lagged one trading row (as-of `t-1`) for publication delay.
- Frozen snapshot in `data/snapshot/` with SHA-256 hashes in `manifest.json`.
  `load_raw` refuses tampered files. Snapshot fetched 2026-10-06, last bar 2026-10-02.

## Timing (no look-ahead)

- Row `t` features use data up to the close of `t`.
- The position decided at close `t` is executed at the **open of `t+1`** and
  earns `R_t = open[t+2]/open[t+1] - 1`. Trade cost is charged on the same row.
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
| **holdout** | 2024-01-01 .. end of snapshot | one shot per sealed candidate |

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
primary 2 bps one-way (~5x observed) covers wider off-hours spreads, slippage and the gap
between the GLD open used in the backtest and the owner's real fill.
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
