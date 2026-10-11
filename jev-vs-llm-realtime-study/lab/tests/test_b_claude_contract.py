"""Claude contract + stub end-to-end tests through the REAL anthropic SDK (owner: LAB-B).

Checks that the request uses structured outputs via output_config.format (never the deprecated
output_format), cache_control on the static rubric, low effort, thinking disabled, and no sampling params or
prefill (Haiku 5.5 rejects them); and that responses are parsed by content-block type with usage accounting.
"""
from __future__ import annotations

import math

import anthropic
import pytest

from _b_helpers import LABELS, reset, stub_fixture, synthetic_task
from jevlab.backends.claude import ClaudeBackend, build_request

stub = stub_fixture()


def _claude(stub, **kw):
    return ClaudeBackend({"mode": "stub", "base_url": stub.base_url, **kw})


def test_sdk_name_and_version():
    assert anthropic.__version__ == "1.13.0"


def test_request_uses_output_config_and_cache_control(stub):
    reset(stub)
    task = synthetic_task()
    with _claude(stub) as b:
        b.predict(task, task.split("test")[:1])
    (req,) = stub.requests
    assert req["path"] == "/v1/messages"
    body = req["body"]
    assert "output_format" not in body  # deprecated parameter never sent
    fmt = body["output_config"]["format"]
    assert fmt["type"] == "json_schema"
    assert fmt["schema"]["properties"]["label"]["enum"] == list(task.labels)
    assert fmt["schema"]["required"] == ["label"] and fmt["schema"]["additionalProperties"] is False
    assert body["output_config"]["effort"] == "low"
    assert body["thinking"] == {"type": "disabled"}
    assert body["model"] == "claude-haiku-5-5"
    (sys_block,) = body["system"]
    assert sys_block["cache_control"] == {"type": "ephemeral"}
    for lab in task.labels:
        assert lab in sys_block["text"]  # the static rubric lists every label
    assert task.split("test")[0].text not in sys_block["text"]  # the utterance is NOT in the cached prefix
    assert body["messages"][-1]["role"] == "user"  # no assistant prefill (400 on Haiku 5.5)
    for p in ("temperature", "top_p", "top_k"):
        assert p not in body
    assert req["headers"]["x-api-key"] == "<dummy-key>"
    assert "anthropic-version" in req["headers"]


def test_cache_ttl_1h_and_adaptive_thinking_options():
    task = synthetic_task()
    from jevlab.backends.claude import ClaudeConfig

    req = build_request(task, "hi", ClaudeConfig(cache_ttl="1h", thinking="adaptive", max_tokens=1024))
    assert req["system"][0]["cache_control"] == {"type": "ephemeral", "ttl": "1h"}
    assert req["thinking"] == {"type": "adaptive"}


def test_prompt_cache_accounting_with_long_rubric(stub):
    """A rubric >= 512 tokens (Haiku 5.5 minimum) is written once, then read from cache (stub simulation)."""
    reset(stub)
    task = synthetic_task(long_rubric=True)
    with _claude(stub) as b:
        p1, p2 = b.predict(task, task.split("test")[:2])
    assert p1.raw["usage"]["cache_creation_input_tokens"] > 0 and p1.raw["usage"]["cache_read_input_tokens"] == 0
    assert p2.raw["usage"]["cache_read_input_tokens"] > 0 and p2.raw["usage"]["cache_creation_input_tokens"] == 0
    u = p1.raw["usage"]
    assert p1.input_tokens == u["input_tokens"] + u["cache_creation_input_tokens"] + u["cache_read_input_tokens"]
    expected = (u["input_tokens"] * 0.10 + u["cache_creation_input_tokens"] * 0.125
                + u["output_tokens"] * 0.50) / 1e6
    assert p1.raw["usd"] == pytest.approx(expected)
    assert p2.raw["usd"] < p1.raw["usd"]
    assert p1.usd == p1.raw["usd"] and p2.usd == p2.raw["usd"]  # Prediction.usd (types.py contract change 3)


def test_short_rubric_is_not_cached(stub):
    reset(stub)
    task = synthetic_task(long_rubric=False)
    with _claude(stub) as b:
        preds = b.predict(task, task.split("test")[:2])
    assert all(p.raw["usage"]["cache_read_input_tokens"] == 0 for p in preds)


def test_confidence_none_has_no_distribution(stub):
    task = synthetic_task()
    with _claude(stub) as b:
        preds = b.predict(task, task.split("test"))
        info = b.probe(task)
    for p in preds:
        assert p.label in task.labels and p.probs is None
        assert p.raw["confidence_method"] == "none" and p.raw["logprobs_available"] is False
        assert p.output_tokens > 0
    assert info["logprobs"] is False and info["has_distribution"] is False


def test_self_consistency_k_samples_charged_k_times(stub):
    reset(stub)
    task = synthetic_task()
    with _claude(stub, confidence="self_consistency", k=5) as b:
        (p,) = b.predict(task, task.split("test")[:1])
    assert len(stub.requests) == 5 and p.raw["n_calls"] == 5
    assert set(p.probs) == set(task.labels) and math.isclose(sum(p.probs.values()), 1.0)
    assert all(abs(v * 5 - round(v * 5)) < 1e-9 for v in p.probs.values())  # vote fractions in 1/k steps
    assert p.label == max(p.probs, key=p.probs.get)
    assert p.input_tokens == sum(c["input_tokens"] + c["cache_creation_input_tokens"] + c["cache_read_input_tokens"]
                                 for c in p.raw["calls"])
    assert p.output_tokens == sum(c["output_tokens"] for c in p.raw["calls"])
    assert p.raw["confidence_method"] == "self_consistency_k5"
    assert p.usd == pytest.approx(sum(  # all k samples are charged
        (c["input_tokens"] * 0.10 + c["cache_creation_input_tokens"] * 0.125 + c["cache_read_input_tokens"] * 0.01
         + c["output_tokens"] * 0.50) / 1e6 for c in p.raw["calls"]))


def test_self_consistency_requires_k_ge_2(stub):
    with pytest.raises(ValueError):
        _claude(stub, confidence="self_consistency", k=1)


def test_refusal_and_thinking_block_and_case_flip(stub):
    task = synthetic_task()
    with _claude(stub) as b:
        reset(stub).configure(claude_refuse=True)
        (p,) = b.predict(task, task.split("test")[:1])
        assert p.label is None and p.raw["error"] == "stop_refusal"
        reset(stub).configure(claude_thinking_block=True)  # response begins with a thinking block
        (p,) = b.predict(task, task.split("test")[:1])
        assert p.label in task.labels and p.raw["calls"][0]["block_types"][0] == "thinking"
        reset(stub).configure(claude_case_flip=True)  # enum capitalisation not guaranteed
        (p,) = b.predict(task, task.split("test")[:1])
        assert p.label in task.labels and p.raw["calls"][0].get("case_mismatch") is True
    reset(stub)


def test_timeout_and_retry_cap(stub):
    task = synthetic_task()
    reset(stub).configure(delay_ms=600)
    try:
        with _claude(stub, timeout_s=0.1, max_retries=0) as b:
            (p,) = b.predict(task, task.split("test")[:1])
    finally:
        stub.configure(delay_ms=0)
    assert p.label is None and p.raw["error"] == "timeout" and p.latency_s < 0.45
    reset(stub).configure(fail_status=529, fail_count=1)
    with _claude(stub, max_retries=0) as b:
        (p,) = b.predict(task, task.split("test")[:1])
    assert p.label is None and p.raw["error"] == "http_529" and len(stub.requests) == 1
    reset(stub)


def test_labels_order_permutes_enum_and_rubric(stub):
    reset(stub)
    task = synthetic_task()
    order = list(reversed(LABELS))
    with _claude(stub) as b:
        b.predict(task, task.split("test")[:1], labels_order=order)
    body = stub.requests[0]["body"]
    assert body["output_config"]["format"]["schema"]["properties"]["label"]["enum"] == order
    text = body["system"][0]["text"]
    assert [text.index(f"- {lab}") for lab in order] == sorted(text.index(f"- {lab}") for lab in order)


def test_stub_rejects_deprecated_output_format(stub):
    """Guard: the stub returns 400 for output_format, so a regression to the deprecated param fails loudly."""
    c = anthropic.Anthropic(api_key="stub-not-a-real-key", base_url=stub.base_url, max_retries=0)
    with pytest.raises(anthropic.BadRequestError):
        c.messages.create(model="claude-haiku-5-5", max_tokens=16, messages=[{"role": "user", "content": "x"}],
                          extra_body={"output_format": {"type": "json_schema", "schema": {"type": "object"}}})


def test_live_mode_requires_key(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_BASE_URL", raising=False)
    with pytest.raises(RuntimeError, match="ANTHROPIC_API_KEY"):
        ClaudeBackend({"mode": "live"})


def test_stub_mode_never_forwards_env_key(stub, monkeypatch):
    reset(stub)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-looks-real-but-is-not")
    task = synthetic_task()
    with _claude(stub) as b:
        b.predict(task, task.split("test")[:1])
    assert stub.requests[0]["headers"]["x-api-key"] == "<dummy-key>"
