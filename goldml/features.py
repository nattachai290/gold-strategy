"""Feature builders. Row t may only use data known at the close of day t.

tests/test_no_lookahead.py enforces this by perturbing future rows.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .data import FRED_SERIES

ANN = np.sqrt(252)


def price_features(p: pd.DataFrame) -> pd.DataFrame:
    c = np.log(p["close"])
    r1 = c.diff()
    f = {}
    for k in (1, 5, 20, 60, 120, 250):
        f[f"ret_{k}"] = c.diff(k)
    vol20 = r1.rolling(20).std()
    vol60 = r1.rolling(60).std()
    f["vol_20"] = vol20 * ANN
    f["vol_60"] = vol60 * ANN
    f["vol_ratio"] = vol20 / vol60
    for k in (20, 60):
        f[f"ret_z_{k}"] = c.diff(k) / (vol60 * np.sqrt(k))
    for k in (50, 200):
        f[f"ma_dist_{k}"] = (c - c.rolling(k).mean()) / vol60
    up = r1.clip(lower=0).ewm(alpha=1 / 14, adjust=False).mean()
    dn = (-r1).clip(lower=0).ewm(alpha=1 / 14, adjust=False).mean()
    f["rsi_14"] = 100 - 100 / (1 + up / dn.replace(0, np.nan))
    f["gap"] = np.log(p["open"]) - c.shift(1)
    f["intraday"] = c - np.log(p["open"])
    hl = np.log(p["high"]) - np.log(p["low"])
    f["range_1"] = hl
    f["range_20"] = hl.rolling(20).mean()
    lv = np.log(p["volume"].where(p["volume"] > 0))
    f["volume_z_20"] = (lv - lv.rolling(20).mean()) / lv.rolling(20).std()
    f["dow"] = pd.Series(p.index.dayofweek, index=p.index).astype(float)
    return pd.DataFrame(f, index=p.index)


def macro_features(p: pd.DataFrame) -> pd.DataFrame:
    f = {}
    for col in FRED_SERIES.values():
        if col not in p:
            continue
        s = p[col]
        if col in ("usd_broad", "vix"):
            s = np.log(s)
        for k in (5, 20, 60):
            f[f"{col}_chg_{k}"] = s.diff(k)
        if col in ("real_yield_10y", "breakeven_10y", "vix"):
            f[f"{col}_lvl"] = p[col]
    return pd.DataFrame(f, index=p.index)


def build_features(p: pd.DataFrame) -> pd.DataFrame:
    return pd.concat([price_features(p), macro_features(p)], axis=1)


PRICE_SET = [
    "ret_1", "ret_5", "ret_20", "ret_60", "ret_120", "ret_250", "vol_20", "vol_60",
    "vol_ratio", "ret_z_20", "ret_z_60", "ma_dist_50", "ma_dist_200", "rsi_14", "gap",
    "intraday", "range_1", "range_20", "volume_z_20",
]
MACRO_SET = [
    f"{c}_chg_{k}" for c in FRED_SERIES.values() for k in (5, 20, 60)
] + ["real_yield_10y_lvl", "breakeven_10y_lvl", "vix_lvl"]
FEATURE_SETS = {"price": PRICE_SET, "macro": MACRO_SET, "price_macro": PRICE_SET + MACRO_SET}
