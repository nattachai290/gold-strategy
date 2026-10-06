# gold-strategy

ML research on trading gold (GLD / XAU) that has to make money **after
realistic costs**, with an evaluation protocol designed to make fooling
ourselves hard.

- `docs/PROTOCOL.md` — data, timing, costs, gates, holdout rules
- `docs/JOURNAL.md` — what was run, what was learned, what is next
- `CLAUDE.md` — planner / runner roles and hard rules
- `goldml/` — harness: data snapshot, features, backtest, walk-forward, metrics, gates
- `experiments/` — experiment batches (`EXPERIMENTS = [...]`), committed before they run
- `prompts/` — run prompts for the runner
- `results/` — run outputs, `trials.csv` (every trial ever evaluated) and
  `LEADERBOARD.md` (all trials ranked; the place to see which model is best)
- `candidates/` — sealed candidates for the one-shot holdout

Naming: `RNNN` = a run (one round the runner executes), `ENNNx` = an
experiment (one model configuration = one trial; a run can hold several),
`CNNN` = a sealed candidate for the one-shot holdout.

```bash
pip install -e '.[dev]'
pytest
```
