"""The CLI runs end-to-end on a tiny FAKE OpenAI-compatible server (MOCK provenance).

Also verifies, inside a real run, that temperature scaling only ever sees calibration
items, and that every results row and prediction carries a LAB/MOCK tag.
"""
import csv
import dataclasses
import json
from pathlib import Path

import pytest
import yaml

import jevlab.run as R
from jevlab.__main__ import main
from jevlab.calibration import fit_temperature as real_fit
from jevlab.data import _cache_path, _resolve_per_class
from jevlab.types import RunResult

from _a_fake_server import FakeServer

pytestmark = pytest.mark.skipif(not _cache_path("clinc150", 15, 7, _resolve_per_class(None)).exists(), reason="processed task cache missing")


def _config(tmp_path: Path, base_url: str) -> Path:
    cfg = {
        "run_name": "test-fake",
        "hardware": "pytest",
        "task": {"name": "clinc150", "n_intents": 15, "seed": 7},
        "limits": {"n_test": 24, "n_calibration": 32},
        "permutation": {"k": 2, "n_items": 8, "seed": 3},
        "backends": [{
            "name": "fake-llama-server", "kind": "openai_compat", "server": "llama-server", "base_url": base_url,
            "model": "fake:tiny", "quant": "auto", "modes": ["json_schema", "logprob_scoring"],
            "provenance_prefix": "MOCK", "captured_mass_threshold": 0.5,
        }],
    }
    p = tmp_path / "fake.yaml"
    p.write_text(yaml.safe_dump(cfg))
    return p


def test_cli_run_on_fake_backend(tmp_path, monkeypatch):
    seen_splits = []

    def spy(items, probs, labels):
        seen_splits.extend(it.split for it in items)
        return real_fit(items, probs, labels)

    monkeypatch.setattr(R, "fit_temperature", spy)
    out = tmp_path / "results"
    with FakeServer() as srv:
        rc = main(["run", "--config", str(_config(tmp_path, srv.base_url)), "--out", str(out)])
    assert rc == 0
    csvs = list(out.glob("*.csv"))
    assert len(csvs) == 1
    rows = list(csv.DictReader(csvs[0].open()))
    expected = []
    for f in dataclasses.fields(RunResult):
        expected += [f"{f.name}_lo", f"{f.name}_hi"] if f.name == "accuracy_ci95" else [f.name]
    assert expected == list(rows[0].keys())  # RunResult.to_row() convention
    assert all(float(r["accuracy_ci95_lo"]) <= float(r["accuracy"]) <= float(r["accuracy_ci95_hi"]) for r in rows)
    assert {(r["mode"], r["calibrated"]) for r in rows} == {("json_schema", "False"), ("json_schema", "True"), ("logprob_scoring", "False"), ("logprob_scoring", "True")}
    assert all(r["provenance"].startswith("MOCK:") for r in rows)
    assert all(r["n_test"] == "24" and r["ece_binning"] == "equal-mass" for r in rows)
    assert all(r["permutation_flip_rate"] != "" for r in rows)
    # temperature scaling saw calibration items only
    assert seen_splits and set(seen_splits) == {"calibration"}
    log = next(out.glob("*.log")).read_text()
    assert "$-equivalent formula" in log and "[Guessing]" in log and "illustrative only" in log
    assert next(out.glob("*_reliability.png")).stat().st_size > 1000
    for line in next(out.glob("*_predictions.jsonl")).read_text().splitlines():
        assert json.loads(line)["provenance"].startswith("MOCK:")


def test_cli_exit_code_and_loud_log_on_probe_failure(tmp_path):
    out = tmp_path / "results"
    with FakeServer(empty_logprobs=True) as srv:
        rc = main(["run", "--config", str(_config(tmp_path, srv.base_url)), "--out", str(out), "--only", "fake-llama-server:logprob_scoring"])
    assert rc == 2
    log = next(out.glob("*.log")).read_text()
    assert "PROBE FAILED" in log and "EMPTY logprobs" in log
