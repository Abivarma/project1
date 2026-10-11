"""Data loader tests. These run offline from the committed JSONL caches in lab/data/."""
from collections import Counter

import pytest

from jevlab.data import OOS_LABEL, _cache_path, _resolve_per_class, load_task


def _have_cache(name):
    return _cache_path(name, 15, 7, _resolve_per_class(None)).exists()


@pytest.mark.skipif(not _have_cache("clinc150"), reason="processed cache missing (run once with network)")
def test_default_task_shape_and_splits():
    t = load_task("clinc150")
    assert t.labels[-1] == OOS_LABEL and len(t.labels) == 16
    assert set(t.label_descriptions) == set(t.labels)
    test = t.split("test")
    assert len(test) >= 200
    assert Counter(it.label for it in test) == {l: 15 for l in t.labels}
    assert len(t.split("calibration")) == 160
    ids = [it.id for it in t.items]
    assert len(ids) == len(set(ids)), "an item appears in two splits"
    # calibration and test come from different CLINC source splits
    assert all(it.id.startswith("clinc:validation:") for it in t.split("calibration"))
    assert all(it.id.startswith("clinc:test:") for it in test)


@pytest.mark.skipif(not _have_cache("clinc150"), reason="processed cache missing")
def test_seeded_and_stable():
    a, b = load_task("clinc150", seed=7), load_task("clinc150", seed=7)
    assert [i.id for i in a.split("test")] == [i.id for i in b.split("test")]


@pytest.mark.skipif(not _have_cache("banking77"), reason="processed cache missing")
def test_banking77_variant():
    t = load_task("banking77")
    assert len(t.labels) == 16 and t.labels[-1] == OOS_LABEL
    cal = {i.id for i in t.split("calibration")}
    tr = {i.id for i in t.split("train")}
    assert not cal & tr


def test_per_class_validation():
    with pytest.raises(ValueError):
        _resolve_per_class({"bogus": 3})
    pc = _resolve_per_class({"train": 10})
    assert pc["train"] == 10 and pc["oos_train"] == 10 and pc["test"] == 15
