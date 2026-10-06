"""Analyzer on synthetic runs: verdicts and recommendations behave sensibly."""
from lightgbm import LGBMClassifier

from goldml.analyze import analyze_run, diagnose
from goldml.evaluate import Experiment, run_experiments
from goldml.synthetic import make_panel
from tests.test_harness import logit


def _run(tmp_path, panel, exps):
    out = tmp_path / "R"
    run_experiments(exps, panel, "R", out, tmp_path / "trials.csv")
    return out


def test_random_walk_is_not_accepted_and_files_exist(tmp_path):
    p = make_panel(3200, seed=21)
    exps = [Experiment("lin", ["ret_1", "ret_5", "ret_20", "vol_20"], 1, logit,
                       first_test_start="2009-01-01", test_months=12),
            Experiment("tree", ["ret_1", "ret_5", "ret_20", "vol_20", "rsi_14", "range_20"], 1,
                       lambda: LGBMClassifier(n_estimators=300, num_leaves=63, min_child_samples=5, verbose=-1),
                       first_test_start="2009-01-01", test_months=12)]
    out = _run(tmp_path, p, exps)
    for e in ("lin", "tree"):
        assert (out / e / "folds.csv").exists() and (out / e / "importance.csv").exists()
    lin, tree = diagnose(out / "lin"), diagnose(out / "tree")
    assert lin["verdict"] in ("NO_EDGE", "FRAGILE", "OVERFIT") and tree["verdict"] != "ACCEPT"
    assert tree["skill_gap"] > 0.1 and "memorising" in tree["flags"] and tree["verdict"] == "OVERFIT"
    assert any("regularisation" in r for r in tree["next"])
    md = analyze_run(out)
    assert "| tree | **OVERFIT** |" in md and "**Next:**" in md


def test_planted_signal_has_oos_skill_and_stable_features(tmp_path):
    p = make_panel(3200, seed=22, signal=0.15)
    out = _run(tmp_path, p, [Experiment("sig", ["ret_5", "ret_20"], 1, logit,
                                         first_test_start="2009-01-01", test_months=12)])
    d = diagnose(out / "sig")
    assert d["oos_skill"] > 0.52 and d["folds_oos_skill"] >= 0.6   # daily edge of 0.15 sd -> AUC ~0.53
    assert d["top_features"][0]["feature"] == "ret_5" and d["top_features"][0]["sign_consistency"] == 1.0
    assert d["verdict"] != "NO_EDGE"


def test_cli_run_writes_summary_leaderboard_and_analysis(tmp_path, monkeypatch):
    """goldml.run end to end on a synthetic panel (no market data)."""
    import goldml.run as runmod

    exp_file = tmp_path / "e.py"
    exp_file.write_text(
        "from goldml.evaluate import Experiment\n"
        "from tests.test_harness import logit\n"
        "EXPERIMENTS = [Experiment('x', ['ret_5', 'ret_20'], 1, logit, first_test_start='2009-01-01', test_months=12)]\n")
    monkeypatch.setattr(runmod, "RESULTS", tmp_path / "results")
    monkeypatch.setattr(runmod, "REGISTRY", tmp_path / "results" / "trials.csv")
    monkeypatch.setattr(runmod, "load_panel", lambda split, cand: make_panel(3000, seed=23))
    monkeypatch.setattr(runmod, "snapshot_hash", lambda: "synthetic")
    assert runmod.main([str(exp_file), "--run-id", "T9"]) == 0
    out = tmp_path / "results"
    for f in ("T9/summary.md", "T9/analysis.md", "T9/x/folds.csv", "LEADERBOARD.md", "trials.csv"):
        assert (out / f).exists(), f
    assert runmod.main([str(exp_file), "--run-id", "T9"]) == 2      # run ids are never reused
