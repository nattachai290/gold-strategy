# R000 FAILED — step 4 (fetch) aborted with HTTP 429

Runner record per the failure rule in `prompts/R000.md`. Facts only. No
evaluation was run; no returns, Sharpe or model output were computed; no holdout
rows (>= 2024-01-01) were read or printed.

## Run metadata

| item | value |
| --- | --- |
| run id | R000 |
| date (local, ICT +07:00) | 2026-10-06 |
| fetch started / failed | 2026-10-06 19:07:09 / 19:09:20 (+07:00) |
| fetch duration | 131.3 s |
| `git rev-parse HEAD` | `358d6ef40928f4b652334d7da35b9f3ae07c977b` |
| branch / working tree | `main`, clean before the run |
| python | 3.13.13 (Windows) |
| host | Windows 11, PowerShell 5.1, curl 8.21.0 |

## Failed step

Step 4, `python -m goldml.dukascopy fetch --start 2003-05 --end 2026-09`
(exit code **1**, uncaught `RuntimeError` — *not* the "manifest lists data
issues" exit-1 case: stdout was empty and no `manifest.json` was written).

```
python -m goldml.dukascopy fetch --start 2003-05 --end 2026-09
```

Full error (verbatim):

```
Traceback (most recent call last):
  File "<frozen runpy>", line 198, in _run_module_as_main
  File "<frozen runpy>", line 88, in _run_code
  File "D:\github\gold-strategy\goldml\dukascopy.py", line 249, in <module>
    raise SystemExit(main())
                     ~~~~^^
  File "D:\github\gold-strategy\goldml\dukascopy.py", line 237, in main
    m = fetch_xau_snapshot(a.start, a.end)
  File "D:\github\gold-strategy\goldml\dukascopy.py", line 152, in fetch_xau_snapshot
    h1 = _write_files(out_dir, start, end, fred_end)
  File "D:\github\gold-strategy\goldml\dukascopy.py", line 141, in _write_files
    h1 = fetch_h1(start, end)
  File "D:\github\gold-strategy\goldml\dukascopy.py", line 99, in fetch_h1
    raw = _get(URL.format(sym=SYMBOL, y=p.year, m=p.month - 1, side=side))
  File "D:\github\gold-strategy\goldml\dukascopy.py", line 88, in _get
    raise RuntimeError(f"failed to fetch {url}: {err}")
RuntimeError: failed to fetch https://datafeed.dukascopy.com/datafeed/XAUUSD/2003/04/ASK_candles_hour_1.bi5: HTTP
Error 429: Too Many Requests
```

The fetch stopped on the second file it requested (`2003/04` ASK = month
2003-05, the first month of the range) after `_get` exhausted its 5 internal
tries. No monthly `{period}: N bars` progress line was printed.

## Steps 1-3 (completed)

1. `main` fast-forwarded to `358d6ef`, which contains `goldml/dukascopy.py`
   and `prompts/R000.md`.
2. `pip install -e '.[dev]'` succeeded. `pytest` **25 passed, exit 0**, but
   only with `PYTHONUTF8=1` / `PYTHONIOENCODING=utf-8`. With the Windows
   default `cp1252` console encoding, `tests/test_analyze.py::test_cli_run_writes_summary_leaderboard_and_analysis`
   fails with `UnicodeEncodeError: 'charmap' codec can't encode characters in
   position 409-414` while writing `analysis.md`. No file was edited to work
   around it.
3. Access check (step 3) did **not** pass consistently, see below.

## Step 3 access check — the datafeed is throttling this host

`curl -sS -o /dev/null -w "%{http_code}\n" https://datafeed.dukascopy.com/datafeed/XAUUSD/2020/00/BID_candles_hour_1.bi5`
(run as `curl.exe -sS -o NUL -w "%{http_code}\n" <same url>`; `-o NUL` is the
Windows equivalent of `/dev/null`) returned, over roughly 10 minutes:

| probe (same URL, unless noted) | client | result |
| --- | --- | --- |
| attempts 1-3 (19:0x) | curl, default UA | `429` |
| 19:06:41 | curl, default UA | `200` |
| 19:06:41 | curl, `-A "Mozilla/5.0 ..."` | `000` (connect timeout) |
| probe script, rounds 1-5 | urllib, **default** UA (`Python-urllib/3.13`) | `429` x5 |
| probe script, round 1 | urllib, `Mozilla/5.0 ...` | `200`, 7392 bytes |
| probe script, rounds 2-3 | urllib, `Mozilla/5.0 ...` | `503`, then connection reset (`WinError 10054`) |
| probe script, other month (2015/05) | urllib, `Mozilla/5.0 ...` | connection reset (`WinError 10054`) |
| probe script | urllib, default UA, 4 more times | `429` x4 |

So: 9 of 9 urllib probes with the default `Python-urllib/3.13` User-Agent were
`429`, while the same URL answered `200` twice for a browser User-Agent and once
for curl's default User-Agent. `503` and connection resets also occurred. No
proxy environment variables were set (`proxy env: {}`). The cause of the 429s
was not established; both "User-Agent is rejected" and "host/IP is rate
limited" remain consistent with the observations.

Relevance to the failure: `goldml/dukascopy.py:_get` calls
`urllib.request.urlopen(url, timeout=60)` with no `User-Agent` header, i.e.
exactly the client that received `429` on every probe, and its backoff
(`time.sleep(2 ** k)` for k in 0..4, about 31 s total) is short for this
server's throttle.

## State left behind

- `data/snapshot_xau/` exists but is **empty**: no `h1.csv.gz`, no `fred.csv`,
  no `manifest.json`. No snapshot was created and nothing under
  `data/snapshot/` was touched.
- No files were modified anywhere in the repo. The runner edited nothing under
  `goldml/`, `tests/`, `experiments/`, `candidates/`, `docs/` or
  `data/snapshot/`, and did not run `python -m goldml.run`.
- Steps 5 (`restore`), 6 (`report`) and 7 (`RUNNER_NOTES.md`) were not run;
  there is no data to restore, report on or describe.

## What the planner needs to decide (not done by the runner)

The runner did not touch the fetch code. Getting R000 unblocked needs a
planner decision on `goldml/dukascopy.py`, e.g. sending a browser-like
`User-Agent`, honouring `Retry-After`/exponential backoff on 429/503, or
resuming month by month across runs — plus a re-check of the step 3 access
probe's reliability.
