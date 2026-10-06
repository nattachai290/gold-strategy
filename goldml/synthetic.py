"""Synthetic panels for tests. Never used for research conclusions."""
from __future__ import annotations

import numpy as np
import pandas as pd

from .data import FRED_SERIES


def make_panel(n: int = 3000, seed: int = 0, start: str = "2005-01-03", vol: float = 0.01,
               drift: float = 0.0, signal: float = 0.0) -> pd.DataFrame:
    """Daily OHLCV + macro columns.

    open[t+1] == close[t], so R_t = open[t+2]/open[t+1]-1 is the close-to-close
    return of day t+1. With signal > 0, that return has mean
    signal * vol * sign(5-day close return known at t): a planted, learnable edge.
    """
    rng = np.random.default_rng(seed)
    idx = pd.bdate_range(start, periods=n)
    e = np.empty(n)
    e[:6] = rng.normal(drift, vol, 6)
    for t in range(6, n):
        past5 = e[t - 5:t].sum()                    # close-return over days t-5..t-1 (known at close t-1)
        e[t] = drift + signal * vol * np.sign(past5) + rng.normal(0, vol)
    close = 100 * np.exp(np.cumsum(e))
    open_ = np.concatenate([[100.0], close[:-1]])
    wig = np.abs(rng.normal(0, 0.3 * vol, (2, n)))
    high = np.maximum(open_, close) * (1 + wig[0])
    low = np.minimum(open_, close) * (1 - wig[1])
    vol_ = rng.lognormal(15, 0.3, n)
    p = pd.DataFrame({"open": open_, "high": high, "low": low, "close": close, "volume": vol_}, index=idx)
    for i, col in enumerate(FRED_SERIES.values()):
        p[col] = 2 + np.cumsum(rng.normal(0, 0.03, n)) if col != "vix" else np.exp(3 + 0.3 * np.sin(np.arange(n) / 50) + rng.normal(0, 0.05, n))
    return p
