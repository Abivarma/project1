"""Temperature scaling: fitted on the calibration split ONLY (LL4)."""
import numpy as np
import pytest

from jevlab.calibration import CalibrationLeakError, apply_temperature, fit_temperature
from jevlab.types import Item

LABELS = ["a", "b"]


def _items(split, n, seed=0):
    rng = np.random.default_rng(seed)
    return [Item(f"{split}{i}", "x", LABELS[int(rng.integers(0, 2))], split) for i in range(n)]


def _overconfident_probs(items, seed=1):
    # predicts the right label only 70% of the time but always with p = 0.99
    rng = np.random.default_rng(seed)
    rows = []
    for it in items:
        right = rng.random() < 0.7
        k = LABELS.index(it.label) if right else 1 - LABELS.index(it.label)
        r = [0.01, 0.01]
        r[k] = 0.99
        rows.append(r)
    return np.array(rows)


def test_fit_on_calibration_softens_overconfidence():
    cal = _items("calibration", 400)
    fit = fit_temperature(cal, _overconfident_probs(cal), LABELS)
    assert fit.T > 1.5 and fit.nll_after < fit.nll_before and fit.fitted_on == "calibration"
    # optimum: sigmoid(log(99)/T) ~ 0.7  ->  T ~ log(99)/log(0.7/0.3)
    assert fit.T == pytest.approx(np.log(99) / np.log(0.7 / 0.3), rel=0.15)


def test_fit_refuses_test_items():
    items = _items("calibration", 10) + _items("test", 1)
    with pytest.raises(CalibrationLeakError):
        fit_temperature(items, _overconfident_probs(items), LABELS)


def test_fit_refuses_train_items():
    items = _items("train", 5)
    with pytest.raises(CalibrationLeakError):
        fit_temperature(items, _overconfident_probs(items), LABELS)


def test_apply_temperature_keeps_argmax_and_normalises():
    p = np.array([[0.7, 0.2, 0.1], [0.2, 0.5, 0.3]])
    for T in (0.5, 1.0, 3.0):
        q = apply_temperature(p, T)
        assert np.allclose(q.sum(1), 1) and (q.argmax(1) == p.argmax(1)).all()
    assert np.allclose(apply_temperature(p, 1.0), p)
