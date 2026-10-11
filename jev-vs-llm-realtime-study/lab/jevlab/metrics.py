"""Evaluation metrics for the Local Lab (owner: LAB-A). Pure numpy.

Conventions
-----------
- y_true: sequence of gold label ids (str).
- y_pred: sequence of predicted label ids (str) or None (invalid / refused / no answer).
  None always counts as wrong.
- probs: (n, k) float array whose columns follow `labels` order. Rows must sum to 1.
  Use `probs_matrix(prob_dicts, labels)` to build it from Prediction.probs dicts.
- Confidence for ECE / risk-coverage = max row probability ("top-label confidence");
  correctness = argmax(probs) == gold.

Definitions (stated so results are reproducible)
- accuracy: mean(pred == gold); CI95 by percentile bootstrap over items.
- macro_f1: unweighted mean of per-class F1 over the classes in `labels` if given,
  otherwise over the sorted union of gold and (non-None) predicted labels. A class with
  zero support and zero predictions is skipped (it has no defined F1).
  Matches sklearn.metrics.f1_score(average="macro", labels=..., zero_division=0) except
  for that skip rule.
- ece: Expected Calibration Error with EQUAL-MASS bins: items sorted by confidence
  (stable) and split into `n_bins` contiguous chunks of near-equal size
  (numpy.array_split). ECE = sum_b |B_b|/n * |acc(B_b) - conf(B_b)|.
  "equal-width" binning is available for comparison, but reports should use equal-mass.
- brier: multiclass Brier = mean_i sum_k (p_ik - 1[y_i = k])^2, range [0, 2].
- risk_coverage: sort by confidence descending (stable); at coverage c = i/n the risk is
  the error rate among the i most confident items. AURC = mean risk over i = 1..n.
- permutation_flip_rate: mean over permutations j of the fraction of items whose
  predicted label under permutation j differs from the prediction under the reference
  order (None counts as a label value, so valid->invalid is a flip).
- latency percentiles: numpy.percentile with linear interpolation.
"""
from __future__ import annotations

from typing import Callable, Mapping, Sequence

import numpy as np


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def probs_matrix(prob_dicts: Sequence[Mapping[str, float] | None], labels: Sequence[str]) -> np.ndarray:
    """Stack per-item {label: p} dicts into an (n, k) matrix in `labels` order.

    Missing labels get 0. Rows are renormalised to sum to 1. A None row raises
    ValueError: callers must decide how to treat items without a distribution.
    """
    out = np.zeros((len(prob_dicts), len(labels)), dtype=float)
    for i, d in enumerate(prob_dicts):
        if d is None:
            raise ValueError(f"row {i} has no probability distribution")
        for j, lab in enumerate(labels):
            out[i, j] = float(d.get(lab, 0.0))
    s = out.sum(axis=1, keepdims=True)
    if np.any(s <= 0):
        raise ValueError("a probability row sums to 0")
    return out / s


def label_indices(y: Sequence[str], labels: Sequence[str]) -> np.ndarray:
    idx = {l: i for i, l in enumerate(labels)}
    return np.array([idx[v] for v in y], dtype=int)


def _correct(y_true: Sequence[str], y_pred: Sequence[str | None]) -> np.ndarray:
    if len(y_true) != len(y_pred):
        raise ValueError("y_true and y_pred differ in length")
    return np.array([p is not None and p == t for t, p in zip(y_true, y_pred)], dtype=float)


# ---------------------------------------------------------------------------
# Accuracy, bootstrap, macro-F1
# ---------------------------------------------------------------------------
def accuracy(y_true: Sequence[str], y_pred: Sequence[str | None]) -> float:
    c = _correct(y_true, y_pred)
    return float(c.mean()) if len(c) else float("nan")


def bootstrap_ci(
    stat: Callable[[np.ndarray], float],
    n: int,
    n_boot: int = 2000,
    seed: int = 0,
    alpha: float = 0.05,
) -> tuple[float, float]:
    """Percentile bootstrap CI. `stat(idx)` computes the statistic on resampled row indices."""
    rng = np.random.default_rng(seed)
    vals = np.empty(n_boot)
    for b in range(n_boot):
        vals[b] = stat(rng.integers(0, n, size=n))
    lo, hi = np.percentile(vals, [100 * alpha / 2, 100 * (1 - alpha / 2)])
    return float(lo), float(hi)


def accuracy_ci95(
    y_true: Sequence[str], y_pred: Sequence[str | None], n_boot: int = 2000, seed: int = 0
) -> tuple[float, float]:
    c = _correct(y_true, y_pred)
    return bootstrap_ci(lambda idx: float(c[idx].mean()), len(c), n_boot=n_boot, seed=seed)


def macro_f1(y_true: Sequence[str], y_pred: Sequence[str | None], labels: Sequence[str] | None = None) -> float:
    if labels is None:
        labels = sorted({*y_true, *(p for p in y_pred if p is not None)})
    f1s = []
    for lab in labels:
        tp = sum(1 for t, p in zip(y_true, y_pred) if t == lab and p == lab)
        fp = sum(1 for t, p in zip(y_true, y_pred) if t != lab and p == lab)
        fn = sum(1 for t, p in zip(y_true, y_pred) if t == lab and p != lab)
        if tp + fp + fn == 0:
            continue  # class absent from both gold and predictions
        f1s.append(2 * tp / (2 * tp + fp + fn))
    return float(np.mean(f1s)) if f1s else float("nan")


# ---------------------------------------------------------------------------
# Calibration
# ---------------------------------------------------------------------------
def _bins(conf: np.ndarray, n_bins: int, binning: str) -> list[np.ndarray]:
    n = len(conf)
    if binning == "equal-mass":
        order = np.argsort(conf, kind="stable")
        return [b for b in np.array_split(order, min(n_bins, n)) if len(b)]
    if binning == "equal-width":
        edges = np.linspace(0.0, 1.0, n_bins + 1)
        ids = np.clip(np.digitize(conf, edges[1:-1], right=True), 0, n_bins - 1)
        return [np.where(ids == b)[0] for b in range(n_bins) if np.any(ids == b)]
    raise ValueError(f"unknown binning {binning!r}")


def reliability_data(probs: np.ndarray, y_idx: np.ndarray, n_bins: int = 10, binning: str = "equal-mass") -> list[dict]:
    """Per-bin {conf_mean, acc, count, conf_lo, conf_hi} for a reliability diagram."""
    probs = np.asarray(probs, dtype=float)
    conf = probs.max(axis=1)
    correct = (probs.argmax(axis=1) == np.asarray(y_idx)).astype(float)
    rows = []
    for b in _bins(conf, n_bins, binning):
        rows.append(
            {
                "conf_mean": float(conf[b].mean()),
                "acc": float(correct[b].mean()),
                "count": int(len(b)),
                "conf_lo": float(conf[b].min()),
                "conf_hi": float(conf[b].max()),
            }
        )
    return rows


def ece(probs: np.ndarray, y_idx: np.ndarray, n_bins: int = 10, binning: str = "equal-mass") -> float:
    rows = reliability_data(probs, y_idx, n_bins=n_bins, binning=binning)
    n = sum(r["count"] for r in rows)
    return float(sum(r["count"] / n * abs(r["acc"] - r["conf_mean"]) for r in rows))


def brier(probs: np.ndarray, y_idx: np.ndarray) -> float:
    probs = np.asarray(probs, dtype=float)
    onehot = np.zeros_like(probs)
    onehot[np.arange(len(probs)), np.asarray(y_idx)] = 1.0
    return float(((probs - onehot) ** 2).sum(axis=1).mean())


def nll(probs: np.ndarray, y_idx: np.ndarray, eps: float = 1e-12) -> float:
    probs = np.asarray(probs, dtype=float)
    return float(-np.log(np.clip(probs[np.arange(len(probs)), np.asarray(y_idx)], eps, 1.0)).mean())


# ---------------------------------------------------------------------------
# Selective prediction
# ---------------------------------------------------------------------------
def risk_coverage(confidence: Sequence[float], correct: Sequence[float]) -> tuple[np.ndarray, np.ndarray, float]:
    """Return (coverage, risk, AURC). Sort by confidence desc (stable on ties)."""
    conf = np.asarray(confidence, dtype=float)
    corr = np.asarray(correct, dtype=float)
    order = np.argsort(-conf, kind="stable")
    errs = 1.0 - corr[order]
    i = np.arange(1, len(conf) + 1)
    risk = np.cumsum(errs) / i
    coverage = i / len(conf)
    return coverage, risk, float(risk.mean())


def accuracy_at_coverage(confidence: Sequence[float], correct: Sequence[float], coverage: float) -> float:
    cov, risk, _ = risk_coverage(confidence, correct)
    k = max(1, int(np.ceil(coverage * len(cov))))
    return float(1.0 - risk[k - 1])


# ---------------------------------------------------------------------------
# Order bias, latency
# ---------------------------------------------------------------------------
def permutation_flip_rate(base_preds: Sequence[str | None], perm_preds: Sequence[Sequence[str | None]]) -> float:
    if not perm_preds:
        return float("nan")
    rates = []
    for pp in perm_preds:
        if len(pp) != len(base_preds):
            raise ValueError("permutation prediction list length mismatch")
        rates.append(np.mean([a != b for a, b in zip(base_preds, pp)]))
    return float(np.mean(rates))


def latency_percentiles(latencies_s: Sequence[float]) -> dict[str, float]:
    a = np.asarray(latencies_s, dtype=float)
    if len(a) == 0:
        return {"p50": float("nan"), "p95": float("nan"), "p99": float("nan")}
    p50, p95, p99 = np.percentile(a, [50, 95, 99])
    return {"p50": float(p50), "p95": float(p95), "p99": float(p99)}


# ---------------------------------------------------------------------------
# Jev-style confidence statistics (docs.typesafe.ai/concepts/confidence, read 2026-10-11)
# These reproduce the vendor's documented formulas so the lab can emulate the *shape*
# of Jev's outputs. They say nothing about Jev's accuracy or calibration.
# ---------------------------------------------------------------------------
def jev_choice_confidence(p: Sequence[float]) -> float:
    """(p_max - 1/n) / (1 - 1/n), clipped to [0, 1]."""
    p = np.asarray(p, dtype=float)
    p = p / p.sum()
    n = len(p)
    return float(np.clip((p.max() - 1 / n) / (1 - 1 / n), 0.0, 1.0))


def jev_noul_confidence(p_yes: float) -> float:
    """|2p - 1| (the docs' optional confidence-style number for a Noul)."""
    return float(abs(2 * p_yes - 1))


def jev_score_confidence(p: Sequence[float]) -> float:
    """max(0, 1 - sum_i p_i |i - m| / MAD_unif) with m = argmax level."""
    p = np.asarray(p, dtype=float)
    p = p / p.sum()
    n = len(p)
    m = int(np.argmax(p))
    spread = float(np.sum(p * np.abs(np.arange(n) - m)))
    even = float(np.mean(np.abs(np.arange(n) - (n - 1) / 2)))
    return max(0.0, 1 - spread / even)


def top2_ratio(p: Sequence[float]) -> float:
    s = np.sort(np.asarray(p, dtype=float))[::-1]
    return float(s[0] / s[1]) if len(s) > 1 and s[1] > 0 else float("inf")


# ---------------------------------------------------------------------------
# Convenience: everything for one prediction set
# ---------------------------------------------------------------------------
def summarize(
    y_true: Sequence[str],
    y_pred: Sequence[str | None],
    labels: Sequence[str],
    probs: np.ndarray | None = None,
    n_bins: int = 10,
    n_boot: int = 2000,
    seed: int = 0,
) -> dict:
    out = {
        "n": len(y_true),
        "accuracy": accuracy(y_true, y_pred),
        "accuracy_ci95": accuracy_ci95(y_true, y_pred, n_boot=n_boot, seed=seed),
        "macro_f1": macro_f1(y_true, y_pred, labels),
        "invalid_rate": float(np.mean([p is None for p in y_pred])) if len(y_pred) else float("nan"),
    }
    if probs is not None:
        y_idx = label_indices(y_true, labels)
        conf = probs.max(axis=1)
        correct = (probs.argmax(axis=1) == y_idx).astype(float)
        _, _, aurc = risk_coverage(conf, correct)
        out.update(
            ece=ece(probs, y_idx, n_bins=n_bins, binning="equal-mass"),
            ece_bins=n_bins,
            ece_binning="equal-mass",
            brier=brier(probs, y_idx),
            nll=nll(probs, y_idx),
            aurc=aurc,
            reliability=reliability_data(probs, y_idx, n_bins=n_bins),
        )
    return out
