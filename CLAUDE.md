# CLAUDE.md

Research repo: an ML model that trades gold and makes money **after realistic
costs**, proven honestly. Read `docs/PROTOCOL.md` before doing anything.

## Roles

- **Planner** (Claude Code session on this repo): builds the harness, writes
  experiment files, tests, run prompts (`prompts/RNNN.md`) and reviews results
  in `docs/JOURNAL.md`. The planner **never runs research evaluations on market
  data** (`python -m goldml.run ...` on the real snapshot). The planner may:
  download data to check it exists and is clean, run synthetic tests
  (`pytest`), and compute diagnostics on results already recorded under
  `results/`.
- **Runner** (a second AI): executes exactly one run prompt, commits the
  outputs, pushes to `main`. The runner does not edit `goldml/`, `tests/`,
  `experiments/` or `docs/PROTOCOL.md`.
- **Owner**: relays "push เข้า main ละ" when a run is pushed. Talk to the owner in
  Thai; code, docs and journal are in English.

## Hard rules

1. Holdout (`>= 2024-01-01`) is touched only through
   `load_panel("holdout", candidate=...)` for a sealed `candidates/CNNN.json`,
   once per candidate. Never read holdout rows any other way, never print them.
2. Every evaluated configuration is a trial and goes into `results/trials.csv`.
   No silent re-runs, no deleting results, no reusing run ids.
3. Experiments are written and committed **before** the run that evaluates
   them. Never tune on a result and re-run under the same name.
4. The data snapshot is frozen (`data/snapshot/manifest.json` hashes). A new
   snapshot is a planned, journaled event.
5. A failed result is information: record what was learned and the next step.
   Never propose stopping the work.

## Commands

```bash
pip install -e '.[dev]'
pytest                                                    # synthetic tests only
python -m goldml.run experiments/<file>.py --run-id RNNN  # runner only
python -m goldml.dukascopy fetch --end YYYY-MM              # runner only (network)
```

Branch: the planner develops on its feature branch; the runner pushes results
to `main`.
