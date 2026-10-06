"""Walk-forward splits with purging.

A training row t has a label that uses opens up to row t+1+h. For a fold whose
first test row is s, a training row is allowed only if t + 1 + h < s
(strict, one extra row of embargo), so no training label overlaps the test period.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class Fold:
    train_end: int     # exclusive positional end of training rows
    test_start: int
    test_end: int      # exclusive


def walk_forward(index: pd.DatetimeIndex, first_test_start, horizon: int,
                 test_months: int = 6, min_train: int = 750,
                 train_window: int | None = None) -> list[Fold]:
    """Expanding (or rolling if train_window) walk-forward folds over index."""
    first = pd.Timestamp(first_test_start)
    edges = pd.date_range(first, index.max() + pd.offsets.Day(1), freq=pd.DateOffset(months=test_months))
    edges = list(edges) + [index.max() + pd.offsets.Day(1)]
    folds = []
    for a, b in zip(edges[:-1], edges[1:]):
        s = int(np.searchsorted(index, a))
        e = int(np.searchsorted(index, b))
        if e <= s:
            continue
        train_end = s - horizon - 1          # rows 0..train_end-1 satisfy t + 1 + h < s
        if train_end < min_train:
            continue
        folds.append(Fold(train_end, s, e))
    return folds


def train_slice(fold: Fold, train_window: int | None) -> slice:
    start = 0 if train_window is None else max(0, fold.train_end - train_window)
    return slice(start, fold.train_end)
