"""OpenAI-compatible adapter: probe must fail loudly (LL2). Uses httpx.MockTransport (no network)."""
import json
import math

import httpx
import pytest

from jevlab.backends.openai_compat import Capabilities, OpenAICompatBackend, make_lab_provenance, normalise_quant
from jevlab.types import Item, Task

LABELS = ("pay_bill", "balance", "out_of_scope")
TASK = Task(
    name="toy",
    instructions="Pick one.",
    labels=LABELS,
    label_descriptions={l: l.replace("_", " ") for l in LABELS},
    items=tuple(
        [Item(f"c{i}", t, l, "calibration") for i, (t, l) in enumerate([("pay my bill", "pay_bill"), ("how much money", "balance"), ("tell a joke", "out_of_scope")])]
        + [Item("t0", "pay electricity", "pay_bill", "test")]
    ),
    source="toy",
    seed=0,
)


def make(mode, handler, **kw):
    client = httpx.Client(transport=httpx.MockTransport(handler))
    return OpenAICompatBackend("fake", mode, "http://fake/v1", "m", server="generic", client=client, provenance_prefix="MOCK", **kw)


def chat(content, lps):
    return httpx.Response(200, json={"choices": [{"message": {"content": content}, "logprobs": lps}], "usage": {"prompt_tokens": 10, "completion_tokens": 1}})


def good_code_handler(request):
    return chat("A", {"content": [{"token": "A", "logprob": math.log(0.9), "top_logprobs": [{"token": "A", "logprob": math.log(0.9)}, {"token": " B", "logprob": math.log(0.07)}]}]})


def test_probe_ok_with_good_logprobs():
    info = make("logprob_scoring", good_code_handler).probe(TASK)
    assert info["probe_captured_mass"][0] == pytest.approx(0.97)
    assert info["codes"] == {"pay_bill": "A", "balance": "B", "out_of_scope": "C"}


@pytest.mark.parametrize("lps", [{"content": []}, None, {"content": [{"token": "A", "logprob": -0.1, "top_logprobs": []}]}])
def test_probe_raises_on_empty_logprobs(lps):
    be = make("logprob_scoring", lambda r: chat("A", lps))
    with pytest.raises(RuntimeError, match="(?i)empty"):
        be.probe(TASK)


def test_probe_raises_on_low_captured_mass():
    h = lambda r: chat("The", {"content": [{"token": "The", "logprob": -0.2, "top_logprobs": [{"token": "The", "logprob": -0.2}, {"token": "A", "logprob": -2.5}]}]})
    with pytest.raises(RuntimeError, match="captured mass"):
        make("logprob_scoring", h).probe(TASK)


def test_probe_raises_on_unclosed_think():
    h = lambda r: chat("<think>hmm", {"content": [{"token": "<think>", "logprob": -0.1, "top_logprobs": [{"token": "<think>", "logprob": -0.1}]}, {"token": "hmm", "logprob": -0.1, "top_logprobs": [{"token": "hmm", "logprob": -0.1}]}]})
    with pytest.raises(RuntimeError, match="unclosed_think_block"):
        make("logprob_scoring", h).probe(TASK)


def test_probe_raises_on_invalid_schema_output():
    h = lambda r: chat('{"label": "refund"}', {"content": [{"token": "x", "logprob": -0.1, "top_logprobs": []}]})
    with pytest.raises(RuntimeError, match="invalid schema output"):
        make("json_schema", h).probe(TASK)


def test_probe_raises_when_config_says_no_logprobs():
    be = make("logprob_scoring", good_code_handler, capabilities={"supports_logprobs": False, "label_scoring": "none"})
    with pytest.raises(RuntimeError, match="unsupported"):
        be.probe(TASK)


def test_json_mode_request_shape_and_confidence():
    seen = {}

    def h(request):
        seen.update(json.loads(request.content))
        toks = ['{"', "label", '":', ' "', "pay", "_bill", '"}']
        lps = [{"token": t, "logprob": (math.log(0.5) if t in ("pay", "_bill") else 0.0), "top_logprobs": []} for t in toks]
        return chat('{"label": "pay_bill"}', {"content": lps})

    be = make("json_schema", h)
    p = be.predict(TASK, TASK.split("test"))[0]
    rf = seen["response_format"]
    assert rf["type"] == "json_schema" and rf["json_schema"]["schema"]["properties"]["label"]["enum"] == list(LABELS)
    assert seen["chat_template_kwargs"] == {"enable_thinking": False} and seen["reasoning_effort"] == "none"
    assert p.label == "pay_bill" and p.probs["pay_bill"] == pytest.approx(0.25)  # 0.5 * 0.5
    assert p.provenance == "MOCK:fake"


def test_ollama_native_endpoint_shape():
    seen = {}

    def h(request):
        seen["url"] = str(request.url)
        seen.update(json.loads(request.content))
        return httpx.Response(200, json={"message": {"content": "A"}, "logprobs": [{"token": "A", "logprob": -0.05, "top_logprobs": [{"token": "A", "logprob": -0.05}]}], "prompt_eval_count": 50, "eval_count": 1})

    be = make("logprob_scoring", h, capabilities={"logprobs_endpoint": "ollama_native"})
    p = be.predict(TASK, TASK.split("test"))[0]
    assert seen["url"].endswith("/api/chat") and seen["think"] is False and seen["top_logprobs"] == 20
    assert p.label == "pay_bill" and p.input_tokens == 50


def test_low_mass_item_routes_to_fallback():
    class FB:
        def score_full_sequence(self, task, item, order):
            return {"pay_bill": 0.1, "balance": 0.8, "out_of_scope": 0.1}, {"input_tokens": 5}

    h = lambda r: chat("The", {"content": [{"token": "The", "logprob": -0.2, "top_logprobs": [{"token": "The", "logprob": -0.2}, {"token": "A", "logprob": -2.5}]}]})
    p = make("logprob_scoring", h, fallback=FB()).predict(TASK, TASK.split("test"))[0]
    assert p.label == "balance" and "fallback" in p.raw["method"]


def test_capabilities_validation():
    with pytest.raises(ValueError):
        Capabilities.from_dict({"label_scoring": "magic"})
    with pytest.raises(ValueError):
        Capabilities.from_dict({"not_a_flag": 1})


def test_provenance_fields_and_quant_names():
    p = make_lab_provenance("ollama", "qwen2.5:0.5b", "Q4_K_M", "mac m3")
    assert p.startswith("LAB:") and len(p.split(":")) == 5
    assert normalise_quant("Q4_K - Medium") == "Q4_K_M" and normalise_quant("Q8_0") == "Q8_0"


def test_lmstudio_responses_endpoint_shape():
    # Shape from the LM Studio Open Responses blog (ledger LOC-016). UNTESTED against a real LM Studio.
    seen = {}

    def h(request):
        seen["url"] = str(request.url)
        seen.update(json.loads(request.content))
        return httpx.Response(200, json={"output": [{"type": "message", "content": [{"type": "output_text", "text": "B", "logprobs": [
            {"token": "B", "logprob": -0.1, "bytes": [66], "top_logprobs": [{"token": "B", "logprob": -0.1}, {"token": "A", "logprob": -2.6}]}]}]}],
            "usage": {"input_tokens": 80, "output_tokens": 1}})

    be = make("logprob_scoring", h, capabilities={"logprobs_endpoint": "lmstudio_responses"})
    p = be.predict(TASK, TASK.split("test"))[0]
    assert seen["url"].endswith("/v1/responses") and seen["include"] == ["message.output_text.logprobs"] and seen["top_logprobs"] == 20
    assert p.label == "balance" and p.input_tokens == 80 and p.captured_mass == pytest.approx(math.exp(-0.1) + math.exp(-2.6))


def test_failing_fallback_is_flagged_not_fatal():
    class Broken:
        def score_full_sequence(self, task, item, order):
            raise RuntimeError("prompt exceeds n_ctx")

    h = lambda r: chat("The", {"content": [{"token": "The", "logprob": -0.2, "top_logprobs": [{"token": "The", "logprob": -0.2}, {"token": "A", "logprob": -2.5}]}]})
    p = make("logprob_scoring", h, fallback=Broken()).predict(TASK, TASK.split("test"))[0]
    assert p.label == "pay_bill" and "FLAGGED: fallback failed" in p.raw["method"]
