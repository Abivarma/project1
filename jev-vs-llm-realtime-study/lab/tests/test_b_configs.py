"""LAB-B configs (configs/jev.yaml, claude.yaml, c1.yaml) build working backends. Owner: LAB-B."""
from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from _b_helpers import stub_fixture, synthetic_task
from jevlab.backends import c1, claude, jev

CONFIGS = Path(__file__).resolve().parents[1] / "configs"
stub = stub_fixture()


def _load(name: str) -> dict:
    return yaml.safe_load((CONFIGS / name).read_text())


def _entry(name: str, kind: str) -> dict:
    """The single `backends:` entry of a LAB-B config (LAB-A runner schema, cf. configs/ci-cpu.yaml)."""
    cfg = _load(name)
    (entry,) = [b for b in cfg["backends"] if b["kind"] == kind]
    assert cfg["task"] == {"name": "clinc150", "n_intents": 15, "seed": 7}  # P3 reference split
    return entry


@pytest.mark.parametrize("name,kind,mod", [("jev.yaml", "jev", jev), ("claude.yaml", "claude", claude)])
def test_vendor_configs_default_to_stub_and_build(stub, name, kind, mod):
    entry = _entry(name, kind)
    assert entry["mode"] == "stub"  # committed configs never default to live
    entry["base_url"] = stub.base_url  # point at the in-process stub
    task = synthetic_task()
    b = mod.make_backend(entry)
    try:
        info = b.probe(task)
    finally:
        b.close()
    assert info["provenance"] == f"MOCK:{kind}"


def test_jev_config_pins_model_and_realtime_limits():
    s = _entry("jev.yaml", "jev")
    assert s["model"] == "jev-1.13.0"
    assert s["timeout_s"] <= 0.3 and s["max_retries"] <= 1 and s["retry_budget_s"] <= 0.5


def test_c1_config_builds_and_sweep_settings_present():
    e = _entry("c1.yaml", "c1")
    b = c1.make_backend(e)
    assert b.cfg.features == "tfidf" and b.cfg.n_per_class == 50
    assert e["sweep"]["n_per_class"] == [10, 50, 200]


def test_unknown_config_keys_fail_loudly():
    with pytest.raises(ValueError, match="unknown"):
        jev.JevConfig.from_dict({"timout_s": 0.2})
    with pytest.raises(ValueError, match="unknown"):
        claude.ClaudeConfig.from_dict({"temprature": 0})
    with pytest.raises(ValueError, match="unknown"):
        c1.C1Config.from_dict({"featurs": "tfidf"})
