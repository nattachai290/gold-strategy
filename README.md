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
- `results/` — run outputs and `trials.csv` (every trial ever evaluated)
- `candidates/` — sealed candidates for the one-shot holdout

```bash
pip install -e '.[dev]'
pytest
```
