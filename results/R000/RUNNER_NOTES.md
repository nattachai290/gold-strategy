# R000 attempt 3 — RUNNER_NOTES

Runner record for the attempt-3 prompt in `prompts/R000.md`. Facts only. No
evaluation was run: `python -m goldml.run` was never invoked, no
returns/Sharpe/model output was computed, and no holdout rows (>= 2024-01-01)
were read or printed.

Attempt 1 (`results/R000_FAILED.md`) and attempt 2
(`results/R000/FAILED_attempt2.md`) are kept unchanged.

## Environment

| item | value |
| --- | --- |
| date | 2026-10-08 (local, ICT +07:00); whole attempt ran this one day |
| OS | Microsoft Windows NT 10.0.26200.0, Windows PowerShell 5.1.26100.9444 |
| python | 3.13.13 |
| `git rev-parse HEAD` | `656e203ae38bfdcf8dbd3dc055e7cfc44bf5f5ff` |
| commit at run start | `656e203 R000 prompt: runner reports fetch progress every 5 minutes` |
| branch / working tree | `main`, clean after `git pull` (identical to `origin/main`) |
| env | `$env:PYTHONUTF8 = "1"` set in every shell |

## Step results

| step | command | result |
| --- | --- | --- |
| 1 | `git pull` | fast-forward to `656e203`, contains the attempt-3 prompt |
| 2 | `pip install -e '.[dev]'` | exit 0 |
| 2 | `pytest` | **30 passed**, exit 0 |
| 3 | `python -m goldml.dukascopy status` | `cached 130/281 months; first missing: 2014-03` |
| 4 | `python -m goldml.dukascopy fetch --start 2003-05 --end 2026-09` | exit 1 **with a printed manifest** (see below), 281/281 months cached |
| 5 | `python -m goldml.dukascopy restore` | `restore OK: hashes match manifest`, exit 0, 15.3 s |
| 6 | `python -m goldml.dukascopy report` | exit 0, 1393 bytes -> `results/R000/data_report.txt` |

Step 4's exit code 1 is the prompt's "manifest lists data issues" case, not a
crash: the manifest was printed and no traceback was written.

`pytest` needs `$env:PYTHONUTF8=1` on this host; with the default cp1252
console the suite raises `UnicodeEncodeError` (same as attempts 1 and 2).

## Fetch runs

**One run was needed.** The stop rule (two consecutive runs adding 0 months,
or 3 calendar days) was never reached.

| run | start | duration | exit | months cached after | new months |
| --- | --- | --- | --- | --- | --- |
| 1 | 10:51:57.50 | 6 h 16 m 18.17 s (22,578.2 s) | 1 (manifest printed) | 281 / 281 | 151 (from 130) |

Run 1 resumed from attempt 2's local cache at `2014-03` and ran detached
(`Start-Process -WindowStyle Hidden`), so harness shell teardown could not
interrupt it; it also wrote its own exit code to `%TEMP%\r000_meta.txt`.

### Error mix, run 1

278 retry lines over 281 months:

| error | count |
| --- | --- |
| `HTTP Error 503: Service Unavailable` | 121 |
| `WinError 10060` (connection timeout) | 117 |
| `WinError 10054` (connection reset) | 39 |
| `The read operation timed out` | 1 |

Months reported as **"no data": 0** — every one of the 281 months returned
bars. Throttling was the only obstacle; the hardened `_get` (12 tries, 15 min
cap, 3 s pause) never exhausted its tries.

### Progress lines reported during run 1

Long retry messages were abbreviated as `(...)` in the chat lines.

```
[10:52] run 1 | cached 130/281 | last: 2014-02: 672 bars
[10:57] run 1 | cached 140/281 (+10) | last: 2014-12: 744 bars
[11:02] run 1 | cached 152/281 (+12) | last:   retry 1/11 in 5s (<urlopen error [WinError 10054] An existing connection was forcibly closed by the remote host>)
[11:07] run 1 | cached 157/281 (+5) | last: 2016-05: 744 bars
[11:12] run 1 | cached 157/281 (+0) | last:   retry 6/11 in 200s (HTTP Error 503: Service Unavailable)
[11:17] run 1 | cached 159/281 (+2) | last:   retry 1/11 in 5s (<urlopen error [WinError 10060] A connection attempt failed because the connected party did not properly respond after a period of time, or established connection failed because connected host has failed to respond>)
[11:22] run 1 | cached 163/281 (+4) | last:   retry 1/11 in 6s (The read operation timed out)
[11:27] run 1 | cached 167/281 (+4) | last:   retry 1/11 in 6s (<urlopen error [WinError 10060] A connection attempt failed ...)
[11:33] run 1 | cached 168/281 (+1) | last:   retry 2/11 in 12s (<urlopen error [WinError 10060] A connection attempt failed ...)
[11:38] run 1 | cached 168/281 (+0) | last:   retry 6/11 in 181s (HTTP Error 503: Service Unavailable)
[11:43] run 1 | cached 168/281 (+0) | last:   retry 7/11 in 340s (<urlopen error [WinError 10054] An existing connection was forcibly closed ...)
[11:48] run 1 | cached 168/281 (+0) | last:   retry 8/11 in 712s (HTTP Error 503: Service Unavailable)
[11:53] run 1 | cached 168/281 (+0) | last:   retry 8/11 in 712s (HTTP Error 503: Service Unavailable)
[11:58] run 1 | cached 168/281 (+0) | last:   retry 9/11 in 1061s (<urlopen error [WinError 10054] An existing connection was forcibly closed ...)
[12:03] run 1 | cached 168/281 (+0) | last:   retry 9/11 in 1061s (<urlopen error [WinError 10054] An existing connection was forcibly closed ...)
[12:09] run 1 | cached 168/281 (+0) | last:   retry 9/11 in 1061s (<urlopen error [WinError 10054] An existing connection was forcibly closed ...)
[12:14] run 1 | cached 168/281 (+0) | sleeping in backoff after retry 9/11 (python alive, stdout still empty)
[12:19] run 1 | cached 171/281 (+3) | last: 2017-07: 744 bars
[12:24] run 1 | cached 173/281 (+2) | last:   retry 2/11 in 11s (<urlopen error [WinError 10060] A connection attempt failed ...)
[12:29] run 1 | cached 175/281 (+2) | last:   retry 2/11 in 11s (<urlopen error [WinError 10060] A connection attempt failed ...)
[12:35] run 1 | cached 178/281 (+3) | last:   retry 4/11 in 47s (HTTP Error 503: Service Unavailable)
[12:40] run 1 | cached 178/281 (+0) | last:   retry 6/11 in 176s (<urlopen error [WinError 10054] An existing connection was forcibly closed ...)
[12:45] run 1 | cached 180/281 (+2) | last:   retry 2/11 in 12s (<urlopen error [WinError 10054] An existing connection was forcibly closed ...)
[12:50] run 1 | cached 186/281 (+6) | last:   retry 2/11 in 12s (HTTP Error 503: Service Unavailable)
[14:50] run 1 | cached 230/281 (+44 from 12:50) | last:   retry 7/11 in 338s (HTTP Error 503: Service Unavailable)
[15:45] run 1 | cached 241/281 (+11 from 14:50) | last:   retry 8/11 in 712s (<urlopen error [WinError 10054] ...) | stdout empty (no manifest yet)
[18:11] run 1 | cached 281/281 months; first missing: None | last: 2026-09: 720 bars
```

The 12:50 -> 14:50 gap is a runner-side reporting gap (the 5-minute chat
updates did not fire in between); the fetch itself was running throughout.

## Printed manifest (verbatim, step 4 stdout)

```json
{
  "fetched_utc": "2026-10-08T10:08:15+00:00",
  "source": "dukascopy XAUUSD H1 bid/ask, mid prices",
  "price_scale": 1000.0,
  "months": [
    "2003-05",
    "2026-09"
  ],
  "fred_end": "2026-09-30",
  "h1_rows": 141968,
  "h1_range": [
    "2003-05-05 00:00:00",
    "2026-09-30 23:00:00"
  ],
  "files": {
    "h1.csv.gz": "2fd49bfd8ed2451366e879232e7510a789b7fb678f195e3ba7b44945a44b70d9",
    "fred.csv": "0ad924dc16b1fc23c8230adbd4d4d4a3b3d3bf250aa28978d40c0b8bfa51fe7b"
  },
  "issues": [
    "2 hourly moves > 5%: [Timestamp('2008-09-18 19:00:00'), Timestamp('2026-01-29 15:00:00')]"
  ]
}
```

## Data-quality report headline (`results/R000/data_report.txt`)

| item | value |
| --- | --- |
| h1 rows | 141,968, 2003-05-05 00:00 .. 2026-09-30 23:00 UTC |
| daily rows | 6,109, 2003-05-05 .. 2026-10-01 |
| issues | `2 hourly moves > 5%` at 2008-09-18 19:00 and 2026-01-29 15:00 UTC |
| median exec spread | 11.76 bps (2003) falling to 1.54 bps (2026) |
| widest hourly spread (UTC) | 22h 6.15 bps, 21h 4.52 bps, 23h 4.50 bps (rollover) |

The two >5% hourly moves are real feed events (2008-09 and 2026-01), left
untouched as instructed. The full year/hour tables are in
`results/R000/data_report.txt`.

## State of the repo

Committed in this run: `data/snapshot_xau/manifest.json`,
`results/R000/data_report.txt`, `results/R000/RUNNER_NOTES.md`.

Not committed (gitignored): `data/snapshot_xau/h1.csv.gz` (3,034,362 bytes),
`data/snapshot_xau/fred.csv` (373,278 bytes) and all 562 files in
`data/snapshot_xau/raw/` (the resume cache, local to this machine only).

No file under `goldml/`, `tests/`, `experiments/`, `candidates/`, `docs/` or
`data/snapshot/` was modified, and neither attempt's failure file was touched.

Reproducibility: `restore` re-derived `h1.csv.gz` and `fred.csv` from the
cached raw files and both SHA-256 hashes matched the manifest, so the snapshot
is reproducible on this machine.
