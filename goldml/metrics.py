"""Performance metrics and the statistics used by the gates."""
from __future__ import annotations

import numpy as np
import pandas as pd
from scipy import stats

ANN = 252
EULER_GAMMA = 0.5772156649


def sharpe(r) -> float:
    r = np.asarray(r, dtype=float)
    sd = r.std(ddof=1)
    return float(r.mean() / sd * np.sqrt(ANN)) if sd > 0 else 0.0


def max_drawdown(r) -> float:
    eq = np.cumprod(1 + np.asarray(r, dtype=float))
    peak = np.maximum.accumulate(np.concatenate([[1.0], eq]))[1:]
    return float((eq / peak - 1).min())


def summary(bt: pd.DataFrame) -> dict:
    r = bt["net"].to_numpy()
    n = len(r)
    eq_end = float(np.prod(1 + r))
    downside = r[r < 0]
    active = bt["pos"].abs() > 1e-9
    return {
        "n_days": n,
        "start": str(bt.index.min().date()),
        "end": str(bt.index.max().date()),
        "total_return": eq_end - 1,
        "cagr": eq_end ** (ANN / n) - 1 if n else 0.0,
        "ann_vol": float(r.std(ddof=1) * np.sqrt(ANN)),
        "sharpe": sharpe(r),
        "sortino": float(r.mean() / downside.std(ddof=1) * np.sqrt(ANN)) if len(downside) > 1 else 0.0,
        "max_dd": max_drawdown(r),
        "turnover_pa": float(bt["turnover"].sum() / n * ANN),
        "cost_pa": float((bt["trade_cost"] + bt["carry_cost"]).sum() / n * ANN),
        "exposure": float(active.mean()),
        "long_frac": float((bt["pos"] > 1e-9).mean()),
        "hit_rate": float((bt.loc[active, "net"] > 0).mean()) if active.any() else 0.0,
    }


def stationary_bootstrap_idx(n: int, mean_block: int, rng: np.random.Generator) -> np.ndarray:
    idx = np.empty(n, dtype=int)
    p = 1.0 / mean_block
    idx[0] = rng.integers(n)
    jumps = rng.random(n) < p
    starts = rng.integers(n, size=n)
    for i in range(1, n):
        idx[i] = starts[i] if jumps[i] else (idx[i - 1] + 1) % n
    return idx


def bootstrap_sharpe(r, n_boot: int = 2000, block: int = 20, seed: int = 0, other=None):
    """Return bootstrap Sharpe samples of r (and of r - other's Sharpe if other given, paired)."""
    r = np.asarray(r, dtype=float)
    o = None if other is None else np.asarray(other, dtype=float)
    rng = np.random.default_rng(seed)
    out = np.empty(n_boot)
    for b in range(n_boot):
        i = stationary_bootstrap_idx(len(r), block, rng)
        out[b] = sharpe(r[i]) - (sharpe(o[i]) if o is not None else 0.0)
    return out


def sharpe_ci(r, level: float = 0.95, **kw) -> tuple[float, float]:
    s = bootstrap_sharpe(r, **kw)
    a = (1 - level) / 2
    return float(np.quantile(s, a)), float(np.quantile(s, 1 - a))


def prob_sharpe_greater(r, other, **kw) -> float:
    """Paired block-bootstrap P(Sharpe(r) > Sharpe(other))."""
    return float((bootstrap_sharpe(r, other=other, **kw) > 0).mean())


def psr(r, sr_benchmark_daily: float = 0.0) -> float:
    """Probabilistic Sharpe ratio (Bailey & Lopez de Prado), daily units."""
    r = np.asarray(r, dtype=float)
    n = len(r)
    sd = r.std(ddof=1)
    if n < 3 or sd == 0:
        return 0.0
    sr = r.mean() / sd
    g3 = stats.skew(r)
    g4 = stats.kurtosis(r, fisher=False)
    denom = np.sqrt(max(1 - g3 * sr + (g4 - 1) / 4 * sr ** 2, 1e-12))
    return float(stats.norm.cdf((sr - sr_benchmark_daily) * np.sqrt(n - 1) / denom))


def expected_max_sharpe(n_trials: int, sharpe_var_annual: float) -> float:
    """Expected max annual Sharpe of n_trials skill-less strategies (False Strategy Theorem)."""
    if n_trials <= 1:
        return 0.0
    z = stats.norm.ppf
    e = (1 - EULER_GAMMA) * z(1 - 1 / n_trials) + EULER_GAMMA * z(1 - 1 / (n_trials * np.e))
    return float(np.sqrt(sharpe_var_annual) * e)


SHARPE_STD_FLOOR = 0.3   # annual; used when the registry has too few trials to estimate dispersion


def deflated_sharpe(r, n_trials: int, trial_sharpes_annual) -> float:
    ts = np.asarray(trial_sharpes_annual, dtype=float)
    var = ts.var(ddof=1) if len(ts) >= 5 else 0.0
    var = max(var, SHARPE_STD_FLOOR ** 2)
    sr0 = expected_max_sharpe(n_trials, var) / np.sqrt(ANN)
    return psr(r, sr0)
