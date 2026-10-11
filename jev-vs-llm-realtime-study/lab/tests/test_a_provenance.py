"""LL5: every results row and every prediction carries a LAB / MOCK (or LIVE) provenance tag."""
import csv
import gzip
import json
from pathlib import Path

import pytest

RESULTS = Path(__file__).resolve().parent.parent / "results"
TAGS = ("LAB:", "MOCK:", "LIVE:")


def _csvs():
    return sorted(p for p in RESULTS.glob("*.csv"))


@pytest.mark.parametrize("path", _csvs() or [None], ids=lambda p: p.name if p else "none")
def test_results_rows_carry_provenance(path):
    if path is None:
        pytest.skip("no results committed yet")
    rows = list(csv.DictReader(path.open()))
    assert rows, f"{path.name} is empty"
    for r in rows:
        assert r["provenance"].startswith(TAGS), f"{path.name}: row without LAB/MOCK/LIVE tag: {r['provenance']!r}"
        if r["provenance"].startswith("LAB:"):
            assert len(r["provenance"].split(":")) == 5, "LAB:<backend>:<model>:<quant>:<hardware>"


@pytest.mark.parametrize("path", sorted(RESULTS.glob("*_predictions.jsonl*")) or [None], ids=lambda p: p.name if p else "none")
def test_prediction_files_carry_provenance(path):
    if path is None:
        pytest.skip("no prediction files committed yet")
    opener = gzip.open if path.suffix == ".gz" else open
    with opener(path, "rt", encoding="utf-8") as f:
        lines = f.read().splitlines()
    assert lines
    for line in lines:
        assert json.loads(line)["provenance"].startswith(TAGS)
