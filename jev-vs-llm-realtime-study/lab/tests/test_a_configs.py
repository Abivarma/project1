"""LAB-A configs parse, declare valid capability flags, and mark untested Mac paths."""
from pathlib import Path

import pytest

from jevlab.backends.openai_compat import Capabilities, from_config
from jevlab.run import load_config

CONFIGS = Path(__file__).resolve().parent.parent / "configs"
LAB_A = ["ci-cpu.yaml", "mac-ollama.yaml", "mac-lmstudio.yaml", "mac-llamacpp.yaml", "mac-mlx.yaml"]


@pytest.mark.parametrize("name", LAB_A)
def test_config_parses_and_backends_construct(name):
    cfg = load_config(CONFIGS / name)
    assert cfg["task"]["name"] in ("clinc150", "banking77")
    n_server = 0
    for b in cfg["backends"]:
        if b.get("kind", "openai_compat") != "openai_compat":
            continue
        Capabilities.from_dict(b.get("capabilities"))
        for mode in b["modes"]:
            be = from_config(b, mode, cfg["hardware"])  # no network at construction
            assert be.provenance.startswith("LAB:")
            n_server += 1
    assert n_server >= 1


@pytest.mark.parametrize("name", [n for n in LAB_A if n.startswith("mac-")])
def test_mac_configs_are_marked_untested(name):
    assert "UNTESTED ON macOS" in (CONFIGS / name).read_text()


def test_model_is_one_line():
    # "load any model": exactly one `model:` line per server entry in the Mac Ollama config
    text = (CONFIGS / "mac-ollama.yaml").read_text()
    assert sum(1 for line in text.splitlines() if line.strip().startswith("model:")) == 1
