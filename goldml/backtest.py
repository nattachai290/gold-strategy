"""Execution timing, labels and cost model.

Timing: a position decided with data up to the close of row t is executed at
the OPEN of row t+1 and held until the open of row t+2. So the return it earns is

    R_t = open[t+2] / open[t+1] - 1          (next_period_return)

and the trade cost for changing position is charged on row t too.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd


def next_period_return(p: pd.DataFrame) -> pd.Series:
    o = p["open"]
    return (o.shift(-2) / o.shift(-1) - 1).rename("R")


def forward_log_return(p: pd.DataFrame, h: int) -> pd.Series:
    """Label: log return from open[t+1] to open[t+1+h]. Uses rows up to t+1+h."""
    lo = np.log(p["open"])
    return (lo.shift(-(1 + h)) - lo.shift(-1)).rename(f"fwd_{h}")


@dataclass(frozen=True)
class CostProfile:
    name: str
    spread_bps: float          # one-way cost per unit of notional traded (spread + slippage + fees)
    long_carry_pa: float       # annual holding cost of a long position
    short_carry_pa: float      # annual holding cost of a short position


# The owner trades LONG-ONLY SPOT gold: positions are in [0, 1], no shorting, no swap.
LONG_ONLY = True

COST_PROFILES = {
    # Owner's venue: Dime! / YLG spot gold in USD. Observed quote 2026-10-06:
    # sell 4128.97 / buy 4129.20 = $0.23/oz = 0.56 bps round trip (~0.28 bps one-way).
    # Primary uses 2 bps one-way (~7x observed) to cover wider off-hours spreads,
    # slippage and the GLD-open vs execution-time mismatch.
    "spot": CostProfile("spot", spread_bps=2.0, long_carry_pa=0.0, short_carry_pa=0.0),
    # Sensitivity: much wider retail spread. Reported, not gated.
    "wide": CostProfile("wide", spread_bps=10.0, long_carry_pa=0.0, short_carry_pa=0.0),
}
PRIMARY_PROFILE = "spot"


def backtest(position: pd.Series, R: pd.Series, cost: CostProfile, cost_mult: float = 1.0) -> pd.DataFrame:
    """position in [-1, 1] decided at close of row t; R from next_period_return."""
    df = pd.concat([position.rename("pos"), R.rename("R")], axis=1).dropna(subset=["R"])
    pos = df["pos"].fillna(0.0).clip(-1, 1)
    turnover = pos.diff().abs()
    turnover.iloc[0] = abs(pos.iloc[0])
    trade = turnover * cost.spread_bps / 1e4 * cost_mult
    carry = (pos.clip(lower=0) * cost.long_carry_pa + (-pos).clip(lower=0) * cost.short_carry_pa) / 252 * cost_mult
    gross = pos * df["R"]
    return pd.DataFrame({
        "pos": pos, "R": df["R"], "gross": gross, "trade_cost": trade,
        "carry_cost": carry, "turnover": turnover, "net": gross - trade - carry,
    })
