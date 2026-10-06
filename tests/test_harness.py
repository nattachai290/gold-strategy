"""Synthetic tests for the research harness. No market data is used here."""
import json

import numpy as np
import pandas as pd
import pytest
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from goldml import metrics as M
from goldml.backtest import CostProfile, backtest, forward_log_return, next_period_return
from goldml.data import HoldoutLocked, build_panel, load_panel, validate_prices
from goldml.evaluate import Experiment, run_experiments, walk_forward_predict
from goldml.features import FEATURE_SETS, build_features
from goldml.splits import walk_forward
from goldml.synthetic import make_panel


def logit():
    return make_pipeline(StandardScaler(), LogisticRegression(C=1.0, max_iter=500))


# ----------------------------------------------------------------- no look-ahead

def test_features_do_not_use_future_rows():
    p = make_panel(800, seed=1)
    cut = 600
    q = p.copy()
    q.iloc[cut + 1:] = q.iloc[cut + 1:] * 1.37      # change everything after row cut
    a, b = build_features(p), build_features(q)
    pd.testing.assert_frame_equal(a.iloc[:cut + 1], b.iloc[:cut + 1])


def test_oos_positions_do_not_use_future_rows():
    p = make_panel(2200, seed=2)
    exp = Experiment("t", FEATURE_SETS["price"], horizon=5, make_model=logit, first_test_start="2010-01-01")
    full = walk_forward_predict(exp, p)
    cut = p.index.get_loc(full.index[300])
    q = p.copy()
    rng = np.random.default_rng(9)
    q.iloc[cut + 1:, :4] = q.iloc[cut + 1:, :4].to_numpy() * rng.uniform(0.5, 1.5, (len(q) - cut - 1, 1))
    part = walk_forward_predict(exp, q)
    common = full.index[full.index <= p.index[cut]]
    pd.testing.assert_series_equal(full.loc[common, "pos"], part.loc[common, "pos"])


def test_fred_is_lagged_one_trading_row():
    px = make_panel(30, seed=3)[["open", "high", "low", "close", "volume"]]
    fred = pd.DataFrame({"vix": np.arange(30.0)}, index=px.index)
    panel = build_panel(px, fred)
    assert np.isnan(panel["vix"].iloc[0])
    assert (panel["vix"].iloc[1:].to_numpy() == np.arange(29.0)).all()


# ----------------------------------------------------------------- splits

@pytest.mark.parametrize("h", [1, 5, 20])
def test_purged_training_labels_never_reach_test(h):
    p = make_panel(3000, seed=4)
    for f in walk_forward(p.index, "2010-01-01", h, test_months=6):
        last_train = f.train_end - 1
        assert last_train + 1 + h < f.test_start       # label uses rows up to t+1+h
        assert f.test_end > f.test_start


def test_label_and_return_alignment():
    p = make_panel(50, seed=5)
    R = next_period_return(p)
    y1 = forward_log_return(p, 1)
    t = 10
    assert R.iloc[t] == pytest.approx(p.open.iloc[t + 2] / p.open.iloc[t + 1] - 1)
    assert np.exp(y1.iloc[t]) - 1 == pytest.approx(R.iloc[t])
    assert np.isnan(R.iloc[-2]) and np.isnan(R.iloc[-1])


# ----------------------------------------------------------------- costs

def test_costs_turnover_and_carry():
    idx = pd.bdate_range("2020-01-01", periods=4)
    R = pd.Series(0.0, index=idx)
    prof = CostProfile("x", spread_bps=10, long_carry_pa=0.252, short_carry_pa=0.504)
    bt = backtest(pd.Series([1, 1, -1, 0], index=idx, dtype=float), R, prof)
    assert bt["turnover"].tolist() == [1, 0, 2, 1]
    assert bt["trade_cost"].tolist() == pytest.approx([0.001, 0, 0.002, 0.001])
    assert bt["carry_cost"].tolist() == pytest.approx([0.001, 0.001, 0.002, 0.0])
    bt2 = backtest(pd.Series([1, 1, -1, 0], index=idx, dtype=float), R, prof, cost_mult=2)
    assert bt2["net"].sum() == pytest.approx(2 * bt["net"].sum())


def test_position_is_clipped():
    idx = pd.bdate_range("2020-01-01", periods=3)
    bt = backtest(pd.Series([3.0, -5.0, 0.5], index=idx), pd.Series(0.01, index=idx), CostProfile("z", 0, 0, 0))
    assert bt["pos"].tolist() == [1.0, -1.0, 0.5]


# ----------------------------------------------------------------- metrics

def test_metric_basics():
    r = np.array([0.1, -0.5, 0.2])
    assert M.max_drawdown(r) == pytest.approx(-0.5)
    rng = np.random.default_rng(0)
    x = rng.normal(0.001, 0.01, 5000)
    assert M.sharpe(x) == pytest.approx(x.mean() / x.std(ddof=1) * np.sqrt(252))
    lo, hi = M.sharpe_ci(x, n_boot=300)
    assert lo < M.sharpe(x) < hi
    # more trials -> higher bar -> lower deflated Sharpe
    ts = rng.normal(0, 0.5, 50)
    assert M.deflated_sharpe(x, 100, ts) < M.deflated_sharpe(x, 2, ts) <= M.psr(x) + 1e-12
    assert M.expected_max_sharpe(1, 1.0) == 0.0


# ----------------------------------------------------------------- end-to-end on synthetic data

def _exp(name, features=("ret_1", "ret_5", "ret_20", "vol_20"), **kw):
    return Experiment(name, list(features), horizon=1, make_model=logit,
                      first_test_start="2009-01-01", test_months=12, **kw)


def test_random_walk_shows_no_edge(tmp_path):
    p = make_panel(3200, seed=11, signal=0.0)
    res = run_experiments([_exp("rw")], p, "T1", tmp_path / "out", tmp_path / "trials.csv")[0]
    assert not res["pass_all"]
    assert res["profiles"]["spot"]["sharpe_ci95"][0] < 0.3
    oos = pd.read_csv(tmp_path / "out" / "rw" / "oos.csv", index_col=0)
    assert oos["pos"].min() >= 0.0                     # long-only spot


def test_planted_signal_is_detected_and_costs_bite(tmp_path):
    p = make_panel(3200, seed=12, signal=0.15)
    res = run_experiments([_exp("sig", features=["ret_5"])], p, "T2", tmp_path / "out", tmp_path / "trials.csv")[0]
    assert res["profiles"]["tight"]["gross_sharpe"] > 1.0     # long-only oracle on ret_5 > 0 gives ~1.7
    assert res["profiles"]["spot"]["sharpe"] < res["profiles"]["tight"]["sharpe"] < res["profiles"]["spot"]["gross_sharpe"]
    assert res["gates"]["G1_sharpe"]
    saved = json.loads((tmp_path / "out" / "sig" / "metrics.json").read_text())
    assert saved["experiment"] == "sig"
    reg = pd.read_csv(tmp_path / "trials.csv")
    assert len(reg) == 1 and reg["experiment"][0] == "sig"


def test_trials_accumulate(tmp_path):
    p = make_panel(2600, seed=13)
    reg = tmp_path / "trials.csv"
    run_experiments([_exp("a"), _exp("b")], p, "T3", tmp_path / "o1", reg)
    r = run_experiments([_exp("c")], p, "T4", tmp_path / "o2", reg)[0]
    assert r["stats"]["n_trials"] == 3


# ----------------------------------------------------------------- data guard

def _write_snapshot(d, p):
    from goldml.data import _sha256
    d.mkdir()
    p[["open", "high", "low", "close", "volume"]].rename_axis("date").to_csv(d / "prices.csv")
    p[["vix"]].rename_axis("date").to_csv(d / "fred.csv")
    (d / "manifest.json").write_text(json.dumps({"files": {f: _sha256(d / f) for f in ("prices.csv", "fred.csv")}}))


def test_holdout_guard(tmp_path):
    p = make_panel(5300, seed=14)            # 2005 .. 2025
    snap, cands, log = tmp_path / "snap", tmp_path / "cands", tmp_path / "log.csv"
    _write_snapshot(snap, p)
    cands.mkdir()
    kw = dict(snap_dir=snap, log_path=log, cand_dir=cands)
    dev = load_panel("dev", **kw)
    assert dev.index.max() < pd.Timestamp("2024-01-01")
    with pytest.raises(HoldoutLocked):
        load_panel("holdout", **kw)
    with pytest.raises(HoldoutLocked):
        load_panel("holdout", "C001", **kw)
    (cands / "C001.json").write_text(json.dumps({"sealed": True}))
    full = load_panel("holdout", "C001", **kw)
    assert full.index.max() >= pd.Timestamp("2024-01-01")
    with pytest.raises(HoldoutLocked):
        load_panel("holdout", "C001", **kw)    # one shot


def test_snapshot_tamper_detected(tmp_path):
    p = make_panel(100, seed=15)
    snap = tmp_path / "snap"
    _write_snapshot(snap, p)
    with (snap / "prices.csv").open("a") as f:
        f.write("2099-01-01,1,1,1,1,1\n")
    with pytest.raises(RuntimeError):
        load_panel("dev", snap_dir=snap, log_path=tmp_path / "l.csv", cand_dir=tmp_path)


def test_validate_prices_flags_problems():
    p = make_panel(100, seed=16)
    assert validate_prices(p) == []
    q = p.copy()
    q.iloc[5, q.columns.get_loc("high")] = q.iloc[5]["low"] * 0.9
    q.iloc[7, 0] = np.nan
    issues = validate_prices(q)
    assert any("OHLC" in i for i in issues) and any("NaN" in i for i in issues)
