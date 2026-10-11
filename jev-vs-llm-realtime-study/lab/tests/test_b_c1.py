"""C1a classifier tests (owner: LAB-B). Synthetic data only, so they run offline and fast."""
from __future__ import annotations

import math
import random
from collections import Counter

import numpy as np
import pytest

from jevlab.backends.c1 import C1Backend, apply_temperature, fit_temperature, sample_train
from jevlab.types import Item, Task

LABELS = ("card_arrival", "lost_card", "exchange_rate", "out_of_scope")
VOCAB = {
    "card_arrival": ["when", "will", "my", "new", "card", "arrive", "delivery", "post"],
    "lost_card": ["lost", "stolen", "wallet", "card", "missing", "freeze", "block"],
    "exchange_rate": ["exchange", "rate", "euro", "dollar", "currency", "convert"],
    "out_of_scope": ["weather", "joke", "music", "pizza", "movie", "song"],
}


def _task(n_train=30, n_cal=8, n_test=10, seed=0) -> Task:
    rng = random.Random(seed)
    items = []
    for split, n in (("train", n_train), ("calibration", n_cal), ("test", n_test)):
        for lab in LABELS:
            for i in range(n):
                words = rng.sample(VOCAB[lab], 3) + rng.sample(sum(VOCAB.values(), []), 1)
                items.append(Item(f"{split}-{lab}-{i}", " ".join(words), lab, split))
    return Task(name="synthetic-c1", instructions="intent?", labels=LABELS,
                label_descriptions={k: k for k in LABELS}, items=tuple(items), source="synthetic", seed=7)


def test_sample_train_uses_train_only_and_is_nested():
    t = _task()
    s10, s20 = sample_train(t, 10, 7), sample_train(t, 20, 7)
    assert all(it.split == "train" for it in s10 + s20)
    assert Counter(it.label for it in s10) == {lab: 10 for lab in LABELS}
    assert {it.id for it in s10} <= {it.id for it in s20}  # nested prefixes
    assert len(sample_train(t, 999, 7)) == len(t.split("train"))  # capped at what exists


def test_fit_predict_distribution_and_provenance():
    t = _task()
    b = C1Backend({"features": "tfidf", "n_per_class": 20})
    info = b.probe(t)
    assert info["n_train"] == 80 and info["train_time_s"] > 0
    preds = b.predict(t, t.split("test"))
    assert len(preds) == len(t.split("test"))
    for p in preds:
        assert set(p.probs) == set(LABELS) and math.isclose(sum(p.probs.values()), 1.0, abs_tol=1e-9)
        assert p.label == max(p.probs, key=p.probs.get)
        assert p.latency_s > 0 and p.provenance == "LAB:c1:tfidf-w12-c25-lr:fp32:linux-cpu-4vcpu"
        assert p.input_tokens is None
    acc = np.mean([p.label == it.label for p, it in zip(preds, t.split("test"))])
    assert acc > 0.8  # separable synthetic data


def test_labels_order_does_not_change_predictions():
    t = _task()
    b = C1Backend({"n_per_class": 20})
    a = [p.label for p in b.predict(t, t.split("test"))]
    r = [p.label for p in b.predict(t, t.split("test"), labels_order=list(reversed(LABELS)))]
    assert a == r


def test_temperature_fit_uses_calibration_split_only(monkeypatch):
    t = _task()
    b = C1Backend({"n_per_class": 20})
    b.fit(t, 20)
    seen = []
    orig = b.log_proba

    def spy(texts):
        seen.extend(texts)
        return orig(texts)

    monkeypatch.setattr(b, "log_proba", spy)
    temp = b.fit_calibration(t)
    cal_texts = [it.text for it in t.split("calibration")]
    assert seen == cal_texts and temp > 0
    assert b.temperature == temp


def test_fit_temperature_recovers_known_scale():
    rng = np.random.default_rng(0)
    logits = rng.normal(size=(4000, 5)) * 3
    y = np.array([rng.choice(5, p=np.exp(r) / np.exp(r).sum()) for r in logits])
    t = fit_temperature(logits * 2.0, y)  # logits made 2x too sharp -> T should be ~2
    assert 1.7 < t < 2.3
    p = apply_temperature(logits, 1.0)
    assert np.allclose(p.sum(axis=1), 1.0)


def test_missing_label_in_train_raises():
    t = _task()
    items = tuple(it for it in t.items if not (it.split == "train" and it.label == "exchange_rate"))
    t2 = Task(t.name, t.instructions, t.labels, t.label_descriptions, items, t.source, t.seed)
    with pytest.raises(RuntimeError, match="no train items"):
        C1Backend().fit(t2, 10)
