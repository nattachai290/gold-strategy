"""CLI used by the runner.

    python -m goldml.run experiments/e001_linear_price.py --run-id R001
    python -m goldml.run candidates/C001.py --run-id H001 --split holdout --candidate C001

An experiment file must define EXPERIMENTS: list[Experiment].
"""
from __future__ import annotations

import argparse
import importlib.util
import subprocess
import sys
from pathlib import Path

from .data import REPO, load_panel, snapshot_hash
from .evaluate import run_experiments
from .report import batch_report, leaderboard

RESULTS = REPO / "results"
REGISTRY = RESULTS / "trials.csv"


def _git(*args) -> str:
    return subprocess.run(["git", *args], cwd=REPO, capture_output=True, text=True).stdout.strip()


def load_experiments(path: Path):
    spec = importlib.util.spec_from_file_location(path.stem, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.EXPERIMENTS


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("experiment_file", type=Path)
    ap.add_argument("--run-id", required=True)
    ap.add_argument("--split", default="dev", choices=["dev", "holdout"])
    ap.add_argument("--candidate")
    a = ap.parse_args(argv)

    out_dir = RESULTS / a.run_id
    if out_dir.exists():
        print(f"refusing: {out_dir} exists (run ids are never reused)", file=sys.stderr)
        return 2
    dirty = bool(_git("status", "--porcelain", "--", "goldml", "experiments", "candidates"))
    exps = load_experiments(a.experiment_file)
    panel = load_panel(a.split, a.candidate)
    if a.split == "holdout":
        from .data import HOLDOUT_START
        for e in exps:
            e.first_test_start = str(HOLDOUT_START.date())
    meta = {"git_sha": _git("rev-parse", "--short", "HEAD"), "git_dirty": dirty,
            "snapshot": snapshot_hash(), "split": a.split, "candidate": a.candidate,
            "experiment_file": str(a.experiment_file)}
    results = run_experiments(exps, panel, a.run_id, out_dir, REGISTRY,
                              register=(a.split == "dev"), meta=meta)
    if a.split == "dev":
        (RESULTS / "LEADERBOARD.md").write_text(leaderboard(REGISTRY))
    md = batch_report(results, a.run_id)
    (out_dir / "summary.md").write_text(md)
    print(md)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
