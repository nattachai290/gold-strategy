"""Data snapshot, validation, as-of alignment and the holdout guard.

Conventions
-----------
* Row t is one trading day of the traded instrument (GLD, or XAUUSD daily bars
  built from Dukascopy H1 at a fixed UTC cut hour, see goldml/dukascopy.py).
* Everything stored in row t is known at the decision time of day t.
* Macro series (FRED) are lagged per series (FRED_LAGS, in trading rows) to
  respect publication delays: row t holds the latest observation dated <= t-lag.
* Rows on/after HOLDOUT_START are hidden unless a sealed candidate unlocks them.
"""
from __future__ import annotations

import csv
import hashlib
import io
import json
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[1]
SNAPSHOT_DIR = REPO / "data" / "snapshot"
DATA_SOURCES = {"gld": SNAPSHOT_DIR, "xau": REPO / "data" / "snapshot_xau"}
DATA_SOURCE = "gld"           # switched by the planner, journaled
CANDIDATES_DIR = REPO / "candidates"
HOLDOUT_LOG = REPO / "results" / "holdout_log.csv"

PRICE_TICKER = "GLD"
DEV_START = pd.Timestamp("2005-01-03")
HOLDOUT_START = pd.Timestamp("2024-01-01")

# FRED series id -> panel column
FRED_SERIES = {
    "DFII10": "real_yield_10y",   # 10y TIPS real yield
    "T10YIE": "breakeven_10y",    # 10y breakeven inflation
    "DTWEXBGS": "usd_broad",      # broad trade-weighted USD index (starts 2006)
    "VIXCLS": "vix",
}
# Publication lag in trading rows. H.15 rates (DFII10, T10YIE) for day d appear
# around 16:15 ET on d+1, after the decision time -> 2. DTWEXBGS (H.10) is released
# weekly on Monday for the previous week -> 8. VIX close of d is known before d+1 -> 1.
FRED_LAGS = {"real_yield_10y": 2, "breakeven_10y": 2, "usd_broad": 8, "vix": 1}
PRICE_COLS = ["open", "high", "low", "close", "volume"]


class HoldoutLocked(RuntimeError):
    pass


# --------------------------------------------------------------------------- snapshot

def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def fetch_snapshot(out_dir: Path = SNAPSHOT_DIR) -> dict:
    """Download prices + FRED into out_dir and write manifest.json. Overwrites."""
    import yfinance as yf

    out_dir.mkdir(parents=True, exist_ok=True)
    px = yf.download(PRICE_TICKER, start="2004-11-01", auto_adjust=False,
                     progress=False, multi_level_index=False)
    px = px.rename(columns=str.lower)[PRICE_COLS]
    px = px.dropna(subset=["close"])        # drop an unfinished current session
    px.index = pd.DatetimeIndex(px.index.date, name="date")
    px.to_csv(out_dir / "prices.csv", float_format="%.6f", lineterminator="\n")

    fred = fetch_fred()
    fred.to_csv(out_dir / "fred.csv", float_format="%.6f", lineterminator="\n")

    manifest = {
        "fetched_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "price_ticker": PRICE_TICKER,
        "price_rows": int(len(px)),
        "price_range": [str(px.index.min().date()), str(px.index.max().date())],
        "fred_series": FRED_SERIES,
        "files": {f: _sha256(out_dir / f) for f in ("prices.csv", "fred.csv")},
    }
    manifest["issues"] = validate_prices(px)
    (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8", newline="\n")
    return manifest


def fetch_fred() -> pd.DataFrame:
    frames = []
    for sid, col in FRED_SERIES.items():
        url = f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={sid}"
        raw = urllib.request.urlopen(url, timeout=60).read().decode()
        s = pd.read_csv(io.StringIO(raw), index_col=0, parse_dates=True, na_values=".").iloc[:, 0]
        frames.append(s.rename(col))
    fred = pd.concat(frames, axis=1).sort_index()
    fred.index.name = "date"
    return fred


def snapshot_hash(snap_dir: Path | None = None) -> str:
    snap_dir = snap_dir or DATA_SOURCES[DATA_SOURCE]
    m = json.loads((snap_dir / "manifest.json").read_text(encoding="utf-8"))
    return hashlib.sha256(json.dumps(m["files"], sort_keys=True).encode()).hexdigest()[:12]


def load_raw(snap_dir: Path | None = None) -> tuple[pd.DataFrame, pd.DataFrame]:
    snap_dir = snap_dir or DATA_SOURCES[DATA_SOURCE]
    m = json.loads((snap_dir / "manifest.json").read_text(encoding="utf-8"))
    for f, h in m["files"].items():
        if _sha256(snap_dir / f) != h:
            raise RuntimeError(f"snapshot file {f} does not match manifest hash")
    if "h1.csv.gz" in m["files"]:
        from .dukascopy import daily_from_h1
        h1 = pd.read_csv(snap_dir / "h1.csv.gz", index_col=0, parse_dates=True)
        px = daily_from_h1(h1)
    else:
        px = pd.read_csv(snap_dir / "prices.csv", index_col=0, parse_dates=True)
    fred = pd.read_csv(snap_dir / "fred.csv", index_col=0, parse_dates=True)
    return px, fred


# --------------------------------------------------------------------------- validation

def validate_prices(px: pd.DataFrame) -> list[str]:
    """Return a list of human-readable data issues (empty list = clean)."""
    issues = []
    if not px.index.is_monotonic_increasing:
        issues.append("index not sorted")
    if px.index.duplicated().any():
        issues.append(f"{int(px.index.duplicated().sum())} duplicate dates")
    nan_rows = px[PRICE_COLS[:4]].isna().any(axis=1)
    if nan_rows.any():
        issues.append(f"{int(nan_rows.sum())} rows with NaN OHLC: {list(px.index[nan_rows].date[:5])}")
    ok = px.dropna(subset=PRICE_COLS[:4])
    if (ok[PRICE_COLS[:4]] <= 0).any().any():
        issues.append("non-positive prices")
    bad = (ok.high < ok[["open", "close"]].max(axis=1) - 1e-9) | (ok.low > ok[["open", "close"]].min(axis=1) + 1e-9)
    if bad.any():
        issues.append(f"{int(bad.sum())} rows with inconsistent OHLC")
    r = np.log(ok.close).diff().abs()
    big = r[r > 0.15]
    if len(big):
        issues.append(f"{len(big)} close-to-close moves > 15%: {list(big.index.date[:5])}")
    gaps = ok.index.to_series().diff().dt.days
    long_gaps = gaps[gaps > 5]
    if len(long_gaps):
        issues.append(f"{len(long_gaps)} calendar gaps > 5 days: {list(long_gaps.index.date[:5])}")
    return issues


# --------------------------------------------------------------------------- panel

def build_panel(px: pd.DataFrame, fred: pd.DataFrame | None, lags: dict | None = None) -> pd.DataFrame:
    """Join prices with as-of lagged macro columns. Drops rows with NaN OHLC."""
    lags = FRED_LAGS if lags is None else lags
    extra = [c for c in px.columns if c not in PRICE_COLS and c not in FRED_SERIES.values()]
    panel = px[PRICE_COLS + extra].dropna(subset=PRICE_COLS[:4]).sort_index().copy()
    if fred is not None and len(fred.columns):
        union = panel.index.union(fred.index)
        asof = fred.reindex(union).ffill().reindex(panel.index)   # latest obs dated <= t
        for col in asof.columns:                                   # latest obs dated <= t-lag
            panel[col] = asof[col].shift(lags.get(col, 1))
    return panel


def _check_candidate(candidate: str, log_path: Path, cand_dir: Path) -> None:
    spec = cand_dir / f"{candidate}.json"
    if not spec.exists():
        raise HoldoutLocked(f"no sealed candidate file {spec}")
    if not json.loads(spec.read_text(encoding="utf-8")).get("sealed"):
        raise HoldoutLocked(f"candidate {candidate} is not sealed")
    if log_path.exists():
        with log_path.open() as f:
            if any(row["candidate"] == candidate for row in csv.DictReader(f)):
                raise HoldoutLocked(f"holdout already used by candidate {candidate} (one shot only)")


def load_panel(split: str = "dev", candidate: str | None = None, *,
               snap_dir: Path | None = None, log_path: Path = HOLDOUT_LOG,
               cand_dir: Path = CANDIDATES_DIR) -> pd.DataFrame:
    """split='dev': rows DEV_START..HOLDOUT_START (exclusive).
    split='holdout': all rows from DEV_START, only for a sealed candidate, logged, once."""
    px, fred = load_raw(snap_dir)
    panel = build_panel(px, fred)
    panel = panel[panel.index >= DEV_START]
    if split == "dev":
        return panel[panel.index < HOLDOUT_START]
    if split != "holdout":
        raise ValueError(split)
    if not candidate:
        raise HoldoutLocked("holdout requires a sealed candidate id")
    _check_candidate(candidate, log_path, cand_dir)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    new = not log_path.exists()
    with log_path.open("a", newline="") as f:
        w = csv.writer(f)
        if new:
            w.writerow(["candidate", "opened_utc", "snapshot"])
        w.writerow([candidate, datetime.now(timezone.utc).isoformat(timespec="seconds"),
                    snapshot_hash(snap_dir)])
    return panel
