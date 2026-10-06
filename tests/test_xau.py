"""Synthetic tests for the Dukascopy decoder, H1 -> daily bars and FRED lags. No network."""
import numpy as np
import pandas as pd
import pytest

from goldml.data import build_panel
from goldml.dukascopy import daily_from_h1, decode_candles, encode_candles, validate_h1


def make_h1(start="2020-01-01", days=40, seed=0):
    """Hourly mid bars, 24h on weekdays, shut from Fri 21:00 to Sun 22:00 UTC."""
    rng = np.random.default_rng(seed)
    idx = pd.date_range(start, periods=days * 24, freq="h")
    wd, hr = idx.dayofweek, idx.hour
    open_ = ~((wd == 5) | ((wd == 4) & (hr >= 21)) | ((wd == 6) & (hr < 22)))
    idx = idx[open_]
    c = 1500 * np.exp(np.cumsum(rng.normal(0, 0.002, len(idx))))
    o = np.concatenate([[1500.0], c[:-1]])
    hi = np.maximum(o, c) + 0.5
    lo = np.minimum(o, c) - 0.5
    return pd.DataFrame({"open": o, "high": hi, "low": lo, "close": c,
                         "volume": rng.uniform(1, 5, len(idx)), "spread_open": 0.3}, index=idx)


def test_decode_roundtrip():
    ms = pd.Timestamp("2021-03-01")
    df = pd.DataFrame({"open": [1700.123, 1701.5], "high": [1702.0, 1703.25], "low": [1699.0, 1700.0],
                       "close": [1701.5, 1702.75], "volume": [12.5, 3.25]},
                      index=[ms + pd.Timedelta(hours=1), ms + pd.Timedelta(hours=2)])
    out = decode_candles(encode_candles(df, ms), ms)
    pd.testing.assert_frame_equal(out, df, check_names=False, check_freq=False, atol=1e-3)
    assert decode_candles(b"", ms).empty


def test_validate_h1_catches_bad_scale_and_order():
    h1 = make_h1()
    assert validate_h1(h1) == []
    assert any("PRICE_SCALE" in i for i in validate_h1(h1.assign(**{c: h1[c] / 1000 for c in ("open", "high", "low", "close")})))
    swapped = h1.rename(columns={"high": "low", "low": "high"})
    assert any("OHLC" in i for i in validate_h1(swapped))


def test_daily_bars_timing_and_weekends():
    h1 = make_h1()
    d = daily_from_h1(h1, cut_hour=13, exec_delay_h=1)
    assert set(d.index.dayofweek) <= {0, 1, 2, 3, 4}               # no weekend rows
    t = pd.Timestamp("2020-01-08")                                   # Wednesday
    assert d.loc[t, "close"] == pytest.approx(h1.loc["2020-01-08 12:00", "close"])   # last bar before cut
    assert d.loc[t, "open"] == pytest.approx(h1.loc["2020-01-07 14:00", "open"])     # fill of Tuesday's decision
    mon = pd.Timestamp("2020-01-13")
    assert d.loc[mon, "open"] == pytest.approx(h1.loc["2020-01-10 14:00", "open"])   # Friday's decision fills Friday 14:00
    assert d.loc[mon, "close"] == pytest.approx(h1.loc["2020-01-13 12:00", "close"])
    assert (d["high"] >= d[["open", "close"]].max(axis=1)).all()
    assert (d["low"] <= d[["open", "close"]].min(axis=1)).all()


def test_daily_bars_do_not_use_bars_after_cut():
    h1 = make_h1(days=60, seed=1)
    cut = pd.Timestamp("2020-02-12 13:00")
    q = h1.copy()
    later = q.index >= cut
    q.loc[later, ["open", "high", "low", "close"]] *= 1.3
    a, b = daily_from_h1(h1), daily_from_h1(q)
    keep = a.index <= pd.Timestamp("2020-02-12")
    pd.testing.assert_frame_equal(a[keep], b[b.index <= pd.Timestamp("2020-02-12")])


def test_fred_lags_per_series():
    idx = pd.bdate_range("2020-01-01", periods=30)
    px = pd.DataFrame({"open": 1.0, "high": 1.0, "low": 1.0, "close": 1.0, "volume": 1.0}, index=idx)
    fred = pd.DataFrame({"vix": np.arange(30.0), "real_yield_10y": np.arange(30.0), "usd_broad": np.arange(30.0)}, index=idx)
    p = build_panel(px, fred)
    assert p["vix"].iloc[10] == 9
    assert p["real_yield_10y"].iloc[10] == 8
    assert p["usd_broad"].iloc[10] == 2
