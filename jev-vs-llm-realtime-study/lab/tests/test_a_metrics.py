"""Golden-value tests for jevlab.metrics (hand-computed small cases)."""
import math

import numpy as np
import pytest

from jevlab import metrics as M

Y = ["a", "b", "c", "a"]
P = ["a", "b", "a", None]
PROBS = np.array([[0.9, 0.1], [0.8, 0.2], [0.4, 0.6], [0.3, 0.7]])
YIDX = np.array([0, 1, 1, 1])


def test_accuracy_counts_none_as_wrong():
    assert M.accuracy(Y, P) == 0.5


def test_macro_f1_hand_computed():
    # a: tp1 fp1 fn1 -> 0.5 ; b: 1.0 ; c: tp0 fp0 fn1 -> 0.0 ; mean 0.5
    assert M.macro_f1(Y, P, ["a", "b", "c"]) == pytest.approx(0.5)


def test_macro_f1_skips_class_absent_everywhere():
    assert M.macro_f1(["a", "a"], ["a", "a"], ["a", "z"]) == pytest.approx(1.0)


def test_ece_equal_mass_hand_computed():
    # conf sorted asc: .6(ok) .7(ok) | .8(wrong) .9(ok) -> |1-.65|*.5 + |.5-.85|*.5 = .35
    assert M.ece(PROBS, YIDX, n_bins=2) == pytest.approx(0.35)


def test_reliability_bins_counts():
    rows = M.reliability_data(PROBS, YIDX, n_bins=2)
    assert [r["count"] for r in rows] == [2, 2]
    assert rows[0]["conf_mean"] == pytest.approx(0.65) and rows[0]["acc"] == 1.0
    assert rows[1]["conf_mean"] == pytest.approx(0.85) and rows[1]["acc"] == 0.5


def test_ece_equal_width_variant():
    # width bins [0,.5],(.5,1] -> all conf in upper bin: |0.75 - 0.75| = 0
    assert M.ece(PROBS, YIDX, n_bins=2, binning="equal-width") == pytest.approx(0.0)


def test_brier_hand_computed():
    # .02 + 1.28 + .32 + .18 = 1.8 ; /4 = .45
    assert M.brier(PROBS, YIDX) == pytest.approx(0.45)


def test_risk_coverage_and_aurc():
    conf = PROBS.max(axis=1)
    corr = (PROBS.argmax(axis=1) == YIDX).astype(float)
    cov, risk, aurc = M.risk_coverage(conf, corr)
    assert list(cov) == [0.25, 0.5, 0.75, 1.0]
    assert risk == pytest.approx([0.0, 0.5, 1 / 3, 0.25])
    assert aurc == pytest.approx((0 + 0.5 + 1 / 3 + 0.25) / 4)
    assert M.accuracy_at_coverage(conf, corr, 0.5) == pytest.approx(0.5)


def test_permutation_flip_rate():
    base = ["a", "b", "c", None]
    assert M.permutation_flip_rate(base, [["a", "b", "c", None], ["b", "b", "c", "a"]]) == pytest.approx(0.25)


def test_latency_percentiles_linear():
    p = M.latency_percentiles([0.1, 0.2, 0.3, 0.4, 1.0])
    assert p["p50"] == pytest.approx(0.3)
    assert p["p95"] == pytest.approx(0.88)


def test_bootstrap_ci_degenerate_and_bounds():
    assert M.accuracy_ci95(["a"] * 10, ["a"] * 10) == (1.0, 1.0)
    lo, hi = M.accuracy_ci95(Y * 25, P * 25, seed=1)
    assert lo < 0.5 < hi


def test_probs_matrix_renormalises_and_rejects_none():
    m = M.probs_matrix([{"a": 2.0, "b": 2.0}], ["a", "b"])
    assert m.tolist() == [[0.5, 0.5]]
    with pytest.raises(ValueError):
        M.probs_matrix([None], ["a"])


def test_jev_confidence_formulas_match_vendor_doc_examples():
    # confidence.md: (0.9, .06, .04) -> (3*.9-1)/2 = .85 ; (.6,.3,.1) and (.6,.2,.2) -> .4
    assert M.jev_choice_confidence([0.9, 0.06, 0.04]) == pytest.approx(0.85)
    assert M.jev_choice_confidence([0.6, 0.3, 0.1]) == pytest.approx(0.4)
    assert M.jev_choice_confidence([0.6, 0.2, 0.2]) == pytest.approx(0.4)
    # Score: (0,.5,.5) -> .25 ; (.5,0,.5) -> 0 ; bug_severity (0,.57,.43) -> ~.355
    assert M.jev_score_confidence([0, 0.5, 0.5]) == pytest.approx(0.25)
    assert M.jev_score_confidence([0.5, 0, 0.5]) == pytest.approx(0.0)
    assert M.jev_score_confidence([0, 0.57, 0.43]) == pytest.approx(1 - 0.43 / (2 / 3))
    assert M.jev_noul_confidence(0.8) == pytest.approx(0.6)
    assert M.top2_ratio([0.6, 0.3, 0.1]) == pytest.approx(2.0)


def test_summarize_keys():
    s = M.summarize(["a", "b"], ["a", "a"], ["a", "b"], probs=np.array([[0.7, 0.3], [0.6, 0.4]]), n_bins=2, n_boot=50)
    assert s["accuracy"] == 0.5 and s["ece_binning"] == "equal-mass" and s["ece_bins"] == 2
    assert not math.isnan(s["brier"])
