# R000 attempt 2 FAILED — step 4 (fetch) could not finish inside the rerun budget

Runner record per the failure rule in `prompts/R000.md` (attempt 2). Attempt 1
is kept unchanged in `results/R000_FAILED.md`. Facts only. No evaluation was
run: `python -m goldml.run` was never invoked, no returns/Sharpe/model output
was computed, and no holdout rows (>= 2024-01-01) were read or printed.

## Run metadata

| item | value |
| --- | --- |
| run id | R000 (attempt 2) |
| dates | 2026-10-06, 2026-10-07, 2026-10-08 (local, ICT +07:00) |
| OS | Microsoft Windows NT 10.0.26200.0, PowerShell 5.1 |
| python | 3.13.13 |
| `git rev-parse HEAD` | `578511accedf2f762a28a33292d6c0fa24fef0cd` |
| branch / working tree | `main`, clean (`git status` empty), identical to `origin/main` |
| env | `$env:PYTHONUTF8 = "1"` set for every python/pytest call |

## Failed step

Step 4, `python -m goldml.dukascopy fetch --start 2003-05 --end 2026-09`.
Exit code **1**, uncaught `RuntimeError` — *not* the "manifest lists data
issues" exit-1 case: stdout was empty, no `manifest.json` was written, and
`data/snapshot_xau/` still contains only `raw/`.

```
python -m goldml.dukascopy fetch --start 2003-05 --end 2026-09
```

Full error (verbatim, final run):

```
Traceback (most recent call last):
  File "<frozen runpy>", line 198, in _run_module_as_main
  File "<frozen runpy>", line 88, in _run_code
  File "D:\github\gold-strategy\goldml\dukascopy.py", line 293, in <module>
    raise SystemExit(main())
                     ~~~~^^
  File "D:\github\gold-strategy\goldml\dukascopy.py", line 281, in main
    m = fetch_xau_snapshot(a.start, a.end)
  File "D:\github\gold-strategy\goldml\dukascopy.py", line 188, in fetch_xau_snapshot
    h1 = _write_files(out_dir, start, end, fred_end)
  File "D:\github\gold-strategy\goldml\dukascopy.py", line 176, in _write_files
    h1 = fetch_h1(start, end, cache_dir=out_dir / "raw")
  File "D:\github\gold-strategy\goldml\dukascopy.py", line 135, in fetch_h1
    raw = _get_cached(URL.format(sym=SYMBOL, y=p.year, m=p.month - 1, side=side), cache)
  File "D:\github\gold-strategy\goldml\dukascopy.py", line 116, in _get_cached
    raw = _get(url)
  File "D:\github\gold-strategy\goldml\dukascopy.py", line 109, in _get
    raise RuntimeError(f"failed to fetch {url} after {tries} tries: {err}")
RuntimeError: failed to fetch https://datafeed.dukascopy.com/datafeed/XAUUSD/2014/02/ASK_candles_hour_1.bi5 after 8 tries: <urlopen error [WinError 10060] A connection attempt failed because the connected party did not properly respond after a period of time, or established connection failed because connected host has failed to respond>
```

## Steps 1-3 (completed)

1. `git pull` clean at `578511a`, which contains the attempt-2 prompt and
   `.gitattributes` (`data/** -text`).
2. `pip install -e '.[dev]'` exit 0. `pytest` **29 passed, exit 0** with
   `$env:PYTHONUTF8=1` (required on this host: without it the console defaults
   to cp1252 and the suite raises `UnicodeEncodeError`, same as attempt 1).
3. Access check printed **`503`** at 2026-10-06 20:30:25. Informational only,
   and `503` is inside `RETRY_CODES`.

## Step 4 history — 6 runs, 3 deaths after 8 tries, rerun budget exhausted

| # | started (local) | duration | exit | outcome | new months |
| --- | --- | --- | --- | --- | --- |
| 1 | 10-06 20:32:27 | 25.4 min | killed | stopped on owner request, mid-download | 15 |
| 2 | 10-07 19:02:07 | 19.7 min | 1 | `after 8 tries` on `2004/09/ASK` (month 2004-10) | 2 |
| 3 | 10-07 19:38 | ~25 min | killed | killed when the harness tore down its background shell; no traceback, so not a fetch error | 14 |
| 4 | 10-07 20:30 | 21.2 min | 1 | `after 8 tries` on `2007/08/ASK` (month 2007-09) | 21 |
| 5 | 10-08 06:45:31 | 21.0 min | 1 | `after 8 tries` on `2007/10/ASK` (month 2007-11) | 2 |
| 6 | 10-08 07:53:18 | 108.1 min | 1 | `after 8 tries` on `2014/02/ASK` (month 2014-03) | 76 |

130 months downloaded in total. Runs 2, 4 and 6 are the three failures of the
"8 tries" kind; run 6 was the third allowed rerun, so the failure rule applies.

Final-run error mix: 108 retries, of which **503 x49**, **`WinError 10060`
connection timeout x46**, **`WinError 10054` connection reset x13**.

Throughput varies by hour: 76 months in 108 min (run 6, morning) but only
2 months in 21 min (run 5, same morning window one run earlier), and 21 months
in 21 min (run 4, evening).

## Progress left on disk

| item | value |
| --- | --- |
| `data/snapshot_xau/raw/*.bi5` | **261 / 562** files, 1,887,578 bytes |
| months complete (BID+ASK) | **130 / 281** (2003-05 .. 2014-02) |
| resume point | `2014-03 ASK` (`2014-03_BID.bi5` is cached) |
| months remaining | 151 |
| `.part` leftovers | 0 |
| `h1.csv.gz` / `fred.csv` / `manifest.json` | **none written** |

**The resume cache is machine-local and not committed.** `.gitignore` keeps
`data/snapshot_xau/*` except `manifest.json`, so these 261 files exist only in
this working copy; a fresh clone cannot resume from them.

## Root cause (as observed)

The datafeed throttles this host. The User-Agent change made in attempt 2 did
not remove it: with the browser User-Agent now in `HEADERS`, requests still
fail with `503`, connection timeouts and connection resets (numbers above). In
attempt 1 the same host returned `429` to urllib's default User-Agent 9 times
out of 9 and `200` to a browser one, which is what motivated the change; during
attempt 2 the browser User-Agent also drew `503`/`10054`/`10060`. `503` carries
no `Retry-After` header, so `_get` falls back to `5s * 2^k` capped at 5 min,
and 8 tries is not enough to cross a throttle window that lasts tens of
minutes.

Two runner-side environment facts, recorded so they are not mistaken for feed
errors: the harness kills background shells after roughly 30-40 min (run 3),
and `echo EXITCODE=%ERRORLEVEL%> file` is parsed by cmd as `1>`, which lost run
4's exit code; the wrapper now writes the redirect first. Runs 5 and 6 were
launched detached (`Start-Process -WindowStyle Hidden`) so the download
survives harness teardown, and both reported their exit code correctly.

## State of the repo

- Only this file is committed. `git status` was empty before the commit.
- No file under `goldml/`, `tests/`, `experiments/`, `candidates/`, `docs/` or
  `data/snapshot/` was modified; the runner edited nothing in the repo.
- `results/R000_FAILED.md` (attempt 1) is untouched.
- Steps 5 (`restore`), 6 (`report`), 7 (`RUNNER_NOTES.md`) and 8 (commit of
  manifest + report) were **not** run: there is no snapshot to restore, report
  on, or commit.

## What the planner needs to decide (not done by the runner)

The download is resumable and machine-local, so a later runner session on this
host can continue from `2014-03 ASK` with the same command. Getting R000 to
finish needs a planner decision, e.g.: a pause longer than 1 s between
requests, treating `503`/timeout as a long cooldown rather than 8 short tries,
many more resume rounds than the prompt's 3, or another source for XAUUSD H1.
Committing the `raw/` cache is not an option: it is gitignored by design and
`manifest.json` is the only file the protocol pins.
