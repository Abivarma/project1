"""Temperature scaling, fitted on the CALIBRATION split only (LL4). Owner: LAB-A.

p_T = softmax(log p / T). T > 1 softens over-confident outputs, T < 1 sharpens.
T is chosen to minimise negative log-likelihood on calibration items, by a bounded
search over log T (pure numpy: coarse grid, then golden-section refinement).

The lesson the lab is built to show: this step NEEDS LABELS. Jev's pitch is calibrated
probabilities without labels; a local emulation only gets there after a labelled
calibration set. Fitting on test items would leak, so `fit_temperature` refuses any
item whose split is not "calibration".
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

import numpy as np

from .types import Item

EPS = 1e-12
LOG_T_BOUNDS = (np.log(0.05), np.log(20.0))


class CalibrationLeakError(AssertionError):
    """Raised when temperature scaling is asked to fit on non-calibration items."""


def apply_temperature(probs: np.ndarray, T: float) -> np.ndarray:
    probs = np.asarray(probs, dtype=float)
    logits = np.log(np.clip(probs, EPS, 1.0)) / float(T)
    logits -= logits.max(axis=1, keepdims=True)
    e = np.exp(logits)
    return e / e.sum(axis=1, keepdims=True)


def _nll(probs: np.ndarray, y_idx: np.ndarray, T: float) -> float:
    p = apply_temperature(probs, T)
    return float(-np.log(np.clip(p[np.arange(len(p)), y_idx], EPS, 1.0)).mean())


@dataclass
class TemperatureFit:
    T: float
    n_fit: int
    nll_before: float
    nll_after: float
    fitted_on: str = "calibration"


def fit_temperature(items: Sequence[Item], probs: np.ndarray, labels: Sequence[str]) -> TemperatureFit:
    """Fit T on calibration items. `probs` rows align with `items`, columns with `labels`."""
    if len(items) == 0:
        raise ValueError("no calibration items")
    bad = [it.id for it in items if it.split != "calibration"]
    if bad:
        raise CalibrationLeakError(
            f"temperature scaling may only be fitted on the calibration split; got {len(bad)} other items, e.g. {bad[:3]}"
        )
    probs = np.asarray(probs, dtype=float)
    if probs.shape != (len(items), len(labels)):
        raise ValueError(f"probs shape {probs.shape} != ({len(items)}, {len(labels)})")
    idx = {l: i for i, l in enumerate(labels)}
    y = np.array([idx[it.label] for it in items], dtype=int)

    grid = np.linspace(*LOG_T_BOUNDS, 61)
    vals = [_nll(probs, y, float(np.exp(g))) for g in grid]
    k = int(np.argmin(vals))
    lo, hi = grid[max(0, k - 1)], grid[min(len(grid) - 1, k + 1)]
    gr = (np.sqrt(5) - 1) / 2
    a, b = lo, hi
    c, d = b - gr * (b - a), a + gr * (b - a)
    for _ in range(60):
        if _nll(probs, y, float(np.exp(c))) < _nll(probs, y, float(np.exp(d))):
            b = d
        else:
            a = c
        c, d = b - gr * (b - a), a + gr * (b - a)
    T = float(np.exp((a + b) / 2))
    return TemperatureFit(T=T, n_fit=len(items), nll_before=_nll(probs, y, 1.0), nll_after=_nll(probs, y, T))
