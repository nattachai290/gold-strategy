"""Dukascopy XAUUSD hourly candles -> snapshot -> daily bars at a chosen cut hour.

Run by the RUNNER (network), never by the planner:

    python -m goldml.dukascopy fetch --start 2003-05 --end 2026-09   # once: new snapshot + manifest
    python -m goldml.dukascopy restore                               # every run: re-download, verify hashes
    python -m goldml.dukascopy report                                # data-quality report (no returns)

Data files are NOT committed (size). Only manifest.json is committed; it pins
the month range and the SHA-256 of every file, so `restore` must reproduce the
exact bytes or fail.

Feed format (public datafeed, LZMA-compressed .bi5, big-endian):
    https://datafeed.dukascopy.com/datafeed/XAUUSD/{YYYY}/{MM-1:02d}/{BID|ASK}_candles_hour_1.bi5
    one file per month, 24-byte records: uint32 seconds-from-month-start,
    uint32 open, close, low, high (price * PRICE_SCALE), float32 volume.
The current month is not published as a monthly file, so snapshots end at the
last complete month.
"""
from __future__ import annotations

import argparse
import json
import lzma
import random
import struct
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from .data import REPO, _sha256, fetch_fred

SYMBOL = "XAUUSD"
PRICE_SCALE = 1000.0          # XAUUSD quoted with 3 decimals in the feed; checked by validate_h1
URL = "https://datafeed.dukascopy.com/datafeed/{sym}/{y}/{m:02d}/{side}_candles_hour_1.bi5"
RECORD = struct.Struct(">5If")
XAU_SNAPSHOT_DIR = REPO / "data" / "snapshot_xau"

# Daily bar definition (UTC). Decision at CUT_HOUR using bars closed by then;
# execution at the open of the bar EXEC_DELAY_H hours later.
CUT_HOUR_UTC = 13             # 20:00 Bangkok
EXEC_DELAY_H = 1              # executes 14:00 UTC = 21:00 Bangkok, around the US open


# --------------------------------------------------------------------------- decode

def decode_candles(raw: bytes, month_start: pd.Timestamp, scale: float = PRICE_SCALE) -> pd.DataFrame:
    if not raw:
        return pd.DataFrame(columns=["open", "high", "low", "close", "volume"])
    data = lzma.decompress(raw)
    if len(data) % RECORD.size:
        raise ValueError(f"payload size {len(data)} is not a multiple of {RECORD.size}")
    rows = list(RECORD.iter_unpack(data))
    a = np.array(rows, dtype=float)
    idx = month_start + pd.to_timedelta(a[:, 0], unit="s")
    return pd.DataFrame({"open": a[:, 1] / scale, "close": a[:, 2] / scale, "low": a[:, 3] / scale,
                         "high": a[:, 4] / scale, "volume": a[:, 5]},
                        index=pd.DatetimeIndex(idx, name="time_utc"))[["open", "high", "low", "close", "volume"]]


def encode_candles(df: pd.DataFrame, month_start: pd.Timestamp, scale: float = PRICE_SCALE) -> bytes:
    """Inverse of decode_candles; used by tests only."""
    out = bytearray()
    for t, r in df.iterrows():
        sec = int((t - month_start).total_seconds())
        out += RECORD.pack(sec, *(int(round(r[c] * scale)) for c in ("open", "close", "low", "high")), float(r["volume"]))
    return lzma.compress(bytes(out), format=lzma.FORMAT_ALONE)


# --------------------------------------------------------------------------- fetch

# The datafeed answered 429 to every request with Python's default User-Agent
# (R000 attempt 1) but 200 to a browser one, and throttles bursts.
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                         "(KHTML, like Gecko) Chrome/124.0 Safari/537.36",
           "Accept": "*/*"}
RETRY_CODES = {429, 500, 502, 503, 504}
# R000 attempt 2: throttle windows (503, timeouts, resets) last tens of minutes,
# so be patient: up to 12 tries per file with waits growing to 15 minutes.
REQUEST_PAUSE = 3.0           # seconds between requests


def _get(url: str, tries: int = 12, base_wait: float = 5.0, max_wait: float = 900.0) -> bytes:
    """GET with browser UA; on 429/5xx/network errors back off (Retry-After or 5s*2^k, cap 15 min)."""
    err: Exception | None = None
    for k in range(tries):
        wait = min(max_wait, base_wait * 2 ** k) * (1 + 0.25 * random.random())
        try:
            req = urllib.request.Request(url, headers=HEADERS)
            return urllib.request.urlopen(req, timeout=60).read()
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return b""
            if e.code not in RETRY_CODES:
                raise RuntimeError(f"failed to fetch {url}: {e}") from e
            err = e
            ra = e.headers.get("Retry-After") if e.headers else None
            if ra and ra.strip().isdigit():
                wait = min(max_wait, float(ra))
        except Exception as e:  # timeouts, connection resets
            err = e
        if k < tries - 1:
            print(f"  retry {k + 1}/{tries - 1} in {wait:.0f}s ({err})", file=sys.stderr)
            time.sleep(wait)
    raise RuntimeError(f"failed to fetch {url} after {tries} tries: {err}")


def _get_cached(url: str, cache: Path | None) -> bytes:
    """Raw files are cached so an interrupted fetch resumes where it stopped."""
    if cache is not None and cache.exists():
        return cache.read_bytes()
    raw = _get(url)
    if cache is not None:
        cache.parent.mkdir(parents=True, exist_ok=True)
        tmp = cache.with_suffix(".part")
        tmp.write_bytes(raw)
        tmp.replace(cache)
    time.sleep(REQUEST_PAUSE)
    return raw


def cache_status(start: str, end: str, cache_dir: Path) -> dict:
    """Which months are fully cached (BID and ASK) - used to measure fetch progress."""
    months = pd.period_range(pd.Period(start, "M"), pd.Period(end, "M"), freq="M")
    done = [p for p in months
            if all((cache_dir / f"{p.year}-{p.month:02d}_{s}.bi5").exists() for s in ("BID", "ASK"))]
    missing = [str(p) for p in months if p not in set(done)]
    return {"months_total": len(months), "months_cached": len(done),
            "first_missing": missing[0] if missing else None, "missing": missing}


def fetch_h1(start: str, end: str, cache_dir: Path | None = None) -> pd.DataFrame:
    """Hourly mid OHLC + spread for months start..end inclusive ('YYYY' or 'YYYY-MM')."""
    months = pd.period_range(pd.Period(start, "M"), pd.Period(end, "M"), freq="M")
    parts = []
    for p in months:
        ms = p.start_time.tz_localize(None)
        sides = {}
        for side in ("BID", "ASK"):
            cache = cache_dir / f"{p.year}-{p.month:02d}_{side}.bi5" if cache_dir else None
            raw = _get_cached(URL.format(sym=SYMBOL, y=p.year, m=p.month - 1, side=side), cache)
            sides[side] = decode_candles(raw, ms)
        b, a = sides["BID"], sides["ASK"]
        if b.empty or a.empty:
            print(f"{p}: no data", file=sys.stderr)
            continue
        j = b.join(a, lsuffix="_bid", rsuffix="_ask", how="inner")
        m = pd.DataFrame({c: (j[f"{c}_bid"] + j[f"{c}_ask"]) / 2 for c in ("open", "high", "low", "close")})
        m["spread_open"] = j["open_ask"] - j["open_bid"]
        m["volume"] = j["volume_bid"] + j["volume_ask"]
        parts.append(m)
        print(f"{p}: {len(m)} bars", file=sys.stderr)
    h1 = pd.concat(parts).sort_index()
    flat = (h1["volume"] <= 0) & (h1["high"] == h1["low"])      # filler bars when market is shut
    return h1[~flat]


def validate_h1(h1: pd.DataFrame) -> list[str]:
    issues = []
    if h1.index.duplicated().any():
        issues.append(f"{int(h1.index.duplicated().sum())} duplicate hours")
    bad = (h1.high < h1[["open", "close"]].max(axis=1) - 1e-6) | (h1.low > h1[["open", "close"]].min(axis=1) + 1e-6)
    if bad.mean() > 0.001:
        issues.append(f"{int(bad.sum())} bars with inconsistent OHLC ({bad.mean():.2%}) - check field order/scale")
    med = h1["close"].median()
    if not 200 < med < 10000:
        issues.append(f"median price {med:.2f} outside 200..10000 - check PRICE_SCALE")
    if (h1["spread_open"] < 0).any():
        issues.append(f"{int((h1['spread_open'] < 0).sum())} negative spreads")
    r = np.log(h1["close"]).diff().abs()
    if (r > 0.05).any():
        issues.append(f"{int((r > 0.05).sum())} hourly moves > 5%: {list(r[r > 0.05].index[:5])}")
    gaps = h1.index.to_series().diff()
    long = gaps[gaps > pd.Timedelta(days=4)]
    if len(long):
        issues.append(f"{len(long)} gaps > 4 days: {list(long.index[:5])}")
    return issues


def _write_files(out_dir: Path, start: str, end: str, fred_end: str) -> pd.DataFrame:
    out_dir.mkdir(parents=True, exist_ok=True)
    h1 = fetch_h1(start, end, cache_dir=out_dir / "raw")
    # lineterminator fixed so the bytes (and hashes) are identical on Windows and Linux
    h1.to_csv(out_dir / "h1.csv.gz", float_format="%.4f", lineterminator="\n",
              compression={"method": "gzip", "mtime": 0})
    fred = fetch_fred()
    fred = fred[fred.index <= pd.Timestamp(fred_end)]          # pin FRED to the snapshot end
    fred.to_csv(out_dir / "fred.csv", float_format="%.6f", lineterminator="\n")
    return h1


def fetch_xau_snapshot(start: str, end: str, out_dir: Path = XAU_SNAPSHOT_DIR) -> dict:
    fred_end = str((pd.Period(end, "M").end_time).date())
    h1 = _write_files(out_dir, start, end, fred_end)
    manifest = {
        "fetched_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "source": f"dukascopy {SYMBOL} H1 bid/ask, mid prices", "price_scale": PRICE_SCALE,
        "months": [start, end], "fred_end": fred_end,
        "h1_rows": int(len(h1)),
        "h1_range": [str(h1.index.min()), str(h1.index.max())],
        "files": {f: _sha256(out_dir / f) for f in ("h1.csv.gz", "fred.csv")},
        "issues": validate_h1(h1),
    }
    (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8", newline="\n")
    return manifest


# --------------------------------------------------------------------------- daily bars

def daily_from_h1(h1: pd.DataFrame, cut_hour: int = CUT_HOUR_UTC, exec_delay_h: int = EXEC_DELAY_H) -> pd.DataFrame:
    """Daily bars for the existing harness.

    Day t covers hourly bars starting in [cut_{t-1}, cut_t), cut_t = date_t + cut_hour (UTC).
    close_t = last price before cut_t (what the model sees at decision time).
    open_t  = price at the first bar starting >= cut_{t-1} + exec_delay_h: the fill
              for a decision made at cut_{t-1}. So the harness's
              R_t = open[t+2]/open[t+1] - 1 is: fill at cut_t + delay -> fill at cut_{t+1} + delay.
    high/low/volume cover the whole day; exec_spread_bps is the spread at the fill bar.
    """
    h = h1.copy()
    day = (h.index - pd.Timedelta(hours=cut_hour)).floor("D") + pd.Timedelta(days=1)
    wd = day.dayofweek
    day = day + pd.to_timedelta(np.select([wd == 5, wd == 6], [2, 1], 0), unit="D")   # weekend -> Monday
    h["day"] = day
    prev = day - pd.to_timedelta(np.where(day.dayofweek == 0, 3, 1), unit="D")      # previous weekday
    period_start = pd.Series(prev + pd.Timedelta(hours=cut_hour), index=h.index)
    after = h.index >= period_start + pd.Timedelta(hours=exec_delay_h)
    g = h.groupby("day")
    fill = h[after].groupby("day").first()
    out = pd.DataFrame({
        "open": fill["open"],
        "high": g["high"].max(), "low": g["low"].min(), "close": g["close"].last(),
        "volume": g["volume"].sum(),
        "exec_spread_bps": fill["spread_open"] / fill["open"] * 1e4,
        "n_bars": g.size(),
    }).dropna(subset=["open", "close"])
    out = out[out["n_bars"] >= 6]                         # drop Sunday-evening stubs etc.
    # drop a trailing day whose cut lies after the last bar (its close is not the cut price)
    out = out[out.index + pd.Timedelta(hours=cut_hour) <= h1.index.max() + pd.Timedelta(hours=1)]
    out.index = pd.DatetimeIndex(out.index.date, name="date")
    out["high"] = out[["high", "open", "close"]].max(axis=1)
    out["low"] = out[["low", "open", "close"]].min(axis=1)
    return out


def restore_xau_snapshot(out_dir: Path = XAU_SNAPSHOT_DIR) -> list[str]:
    """Re-download the files pinned by the committed manifest; return mismatching files."""
    m = json.loads((out_dir / "manifest.json").read_text(encoding="utf-8"))
    _write_files(out_dir, m["months"][0], m["months"][1], m["fred_end"])
    return [f for f, h in m["files"].items() if _sha256(out_dir / f) != h]


def quality_report(out_dir: Path = XAU_SNAPSHOT_DIR) -> str:
    """Counts, gaps and spreads only - no returns, no performance."""
    h1 = pd.read_csv(out_dir / "h1.csv.gz", index_col=0, parse_dates=True)
    d = daily_from_h1(h1)
    lines = [f"h1 rows {len(h1)}  {h1.index.min()} .. {h1.index.max()}",
             f"daily rows {len(d)}  {d.index.min().date()} .. {d.index.max().date()}",
             "issues: " + json.dumps(validate_h1(h1)), "",
             "year | h1 bars | daily bars | median exec spread bps | p90 exec spread bps"]
    hy = h1.groupby(h1.index.year).size()
    for y, g in d.groupby(d.index.year):
        s = g["exec_spread_bps"]
        lines.append(f"{y} | {hy.get(y, 0)} | {len(g)} | {s.median():.2f} | {s.quantile(0.9):.2f}")
    sp = h1["spread_open"] / h1["open"] * 1e4
    lines += ["", "hour UTC | median spread bps (all years)"]
    lines += [f"{hr:02d} | {v:.2f}" for hr, v in sp.groupby(h1.index.hour).median().items()]
    return "\n".join(lines)


def _utf8_stdout() -> None:
    try:                       # Windows consoles default to cp1252
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    f = sub.add_parser("fetch")
    f.add_argument("--start", default="2003-05")
    f.add_argument("--end", required=True, help="last COMPLETE month, YYYY-MM")
    sub.add_parser("restore")
    sub.add_parser("report")
    st = sub.add_parser("status", help="how many months are cached (progress of an interrupted fetch)")
    st.add_argument("--start", default="2003-05")
    st.add_argument("--end", default="2026-09")
    a = ap.parse_args(argv)
    _utf8_stdout()
    if a.cmd == "status":
        s = cache_status(a.start, a.end, XAU_SNAPSHOT_DIR / "raw")
        print(f"cached {s['months_cached']}/{s['months_total']} months; first missing: {s['first_missing']}")
        return 0
    if a.cmd == "fetch":
        m = fetch_xau_snapshot(a.start, a.end)
        print(json.dumps(m, indent=2))
        return 1 if m["issues"] else 0
    if a.cmd == "restore":
        bad = restore_xau_snapshot()
        print("restore OK: hashes match manifest" if not bad else f"HASH MISMATCH: {bad}")
        return 1 if bad else 0
    print(quality_report())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
