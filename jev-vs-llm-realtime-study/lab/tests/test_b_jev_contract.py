"""Jev contract + stub end-to-end tests through the REAL typesafe-sdk (owner: LAB-B).

Request shape per https://docs.typesafe.ai/api.md: {state, model, questions{<id>: {type, instructions, criteria}}}.
Response shape: {model, answers{<id>: {type, choice, probabilities, confidence}}, usage{input_tokens, output_tokens}}.
"""
from __future__ import annotations

import math

import pytest
import typesafe_sdk
from typesafe_sdk import Choice, Noul, RetryPolicy, Score

from _b_helpers import LABELS, reset, stub_fixture, synthetic_task
from jevlab.backends.jev import PINNED_MODEL, JevBackend, build_choice_question
from jevlab.stub_server import DOCUMENTED_EXAMPLES

stub = stub_fixture()
DOC_STATE = "Help! My payouts have been failing for 3 days."


def _jev(stub, **kw):
    return JevBackend({"mode": "stub", "base_url": stub.base_url, **kw})


def test_sdk_name_and_version():
    assert typesafe_sdk.__version__ == "0.7.4"


def test_request_json_shape_matches_api_md(stub):
    reset(stub)
    task = synthetic_task()
    with _jev(stub) as b:
        b.predict(task, task.split("test")[:1])
    (req,) = stub.requests
    assert req["path"] == "/v1/systemone"
    body = req["body"]
    assert set(body) == {"state", "model", "questions"}
    assert body["state"] == task.split("test")[0].text  # state = the utterance
    assert body["model"] == PINNED_MODEL == "jev-1.13.0"  # pinned, not jev-latest
    (qid, q), = body["questions"].items()
    assert qid == "intent"
    assert set(q) == {"type", "instructions", "criteria"}
    assert q["type"] == "choice" and q["instructions"] == task.instructions
    assert list(q["criteria"]) == list(task.labels)  # option order preserved
    assert q["criteria"] == task.label_descriptions
    assert req["headers"]["authorization"] == "<dummy-key>"
    assert req["headers"]["content-type"].startswith("application/json")


def test_labels_order_permutes_criteria(stub):
    reset(stub)
    task = synthetic_task()
    order = list(reversed(LABELS))
    with _jev(stub) as b:
        p = b.predict(task, task.split("test")[:1], labels_order=order)[0]
    assert list(stub.requests[0]["body"]["questions"]["intent"]["criteria"]) == order
    assert list(p.probs) == list(task.labels)  # probs always keyed in task.labels order


@pytest.mark.parametrize("ex", range(len(DOCUMENTED_EXAMPLES)))
def test_documented_examples_replayed_and_parsed(stub, ex):
    """The real SDK parses the verbatim api.md examples (answers + usage)."""
    req, expected = DOCUMENTED_EXAMPLES[ex]
    with _jev(stub) as b:
        # dict questions are accepted by the SDK (sdk/python/api/clients/sync.md "Pass questions as dictionaries")
        resp = b.client.system_one(req["state"], req["questions"], model="jev-latest")
    assert resp.model == expected["model"]
    assert resp.usage.input_tokens == expected["usage"]["input_tokens"]
    assert resp.usage.output_tokens == expected["usage"]["output_tokens"]
    assert resp.raw_http_response.json() == expected  # wire body replayed verbatim from api.md
    (qid, ans), = expected["answers"].items()
    got = resp.answers[qid].model_dump()
    for k, v in ans.items():
        if ans["type"] == "score" and k in ("legend", "probabilities"):
            # typesafe-sdk 0.7.4 parses Score level keys to int (dict[int, ...]); the wire uses "0", "1", ...
            v = {int(lv): x for lv, x in v.items()}
        assert got[k] == v, (k, got[k], v)


def test_documented_choice_example_via_sdk_question_objects(stub):
    with _jev(stub) as b:
        resp = b.client.system_one(DOC_STATE, {"department": Choice(
            instructions="Which team should handle this?",
            criteria={"billing": "Payments, invoicing, refunds", "technical": "Bugs, outages, integrations",
                      "sales": "Pricing, upgrades, new accounts"})})
        a = resp.choices["department"]
        assert (a.choice, a.confidence, a.probabilities["billing"]) == ("billing", 0.81, 0.88)
        r2 = b.client.system_one(DOC_STATE, {"is_urgent": Noul(instructions="Does this convey urgency?")})
        assert r2.nouls["is_urgent"].noul == 0.95
        r3 = b.client.system_one(DOC_STATE, {"frustration": Score(
            instructions="How frustrated is the customer?", criteria=["Calm", "Frustrated", "Very angry"])})
        assert r3.scores["frustration"].score == 1.05 and r3.scores["frustration"].legend[2] == "Very angry"  # int keys in SDK


def test_prediction_parse(stub):
    task = synthetic_task()
    with _jev(stub) as b:
        preds = b.predict(task, task.split("test"))
    for p in preds:
        assert p.label in task.labels
        assert set(p.probs) == set(task.labels)
        assert math.isclose(sum(p.probs.values()), 1.0, abs_tol=1e-9)
        assert p.label == max(p.probs, key=p.probs.get)
        assert 0.0 <= p.raw["confidence"] <= 1.0  # vendor confidence kept in raw
        assert p.input_tokens > 0 and p.output_tokens > 0
        assert p.raw["model_answered"] == "jev-1.13.0"
        assert p.raw["usd"] == pytest.approx(p.input_tokens * 0.042 / 1e6)  # output not billed
        assert p.usd == p.raw["usd"]  # Prediction.usd (types.py contract change 3)
    assert preds[0].cold and not any(p.cold for p in preds[1:])


def test_probe_ok_and_raises_loudly(stub):
    task = synthetic_task()
    with _jev(stub) as b:
        info = b.probe(task)
        assert info["provenance"] == "MOCK:jev" and info["has_distribution"] and info["model"] == "jev-1.13.0"
        reset(stub).configure(jev_model_override="jev-1.14.0")  # alias drift: answer not from the pinned model
        with pytest.raises(RuntimeError, match="answered by"):
            b.probe(task)
        reset(stub).configure(jev_bad_probs=True)  # probabilities do not sum to 1
        with pytest.raises(RuntimeError, match="sum to"):
            b.probe(task)
    reset(stub)


def test_realtime_timeout_returns_none_fast(stub):
    """Explicit per-call timeout: a 600 ms stall must not block the decision path."""
    reset(stub).configure(delay_ms=600)
    task = synthetic_task()
    try:
        with _jev(stub, timeout_s=0.1, max_retries=0) as b:
            p = b.predict(task, task.split("test")[:1])[0]
    finally:
        stub.configure(delay_ms=0)
    assert p.label is None and p.raw["error"] == "timeout"
    assert p.latency_s < 0.45
    assert p.provenance == "MOCK:jev"


def test_retry_cap_respected(stub):
    task = synthetic_task()
    reset(stub).configure(fail_status=529, fail_count=1)
    with _jev(stub, max_retries=0) as b:
        p = b.predict(task, task.split("test")[:1])[0]
    assert p.label is None and p.raw["error"] == "http_529" and len(stub.requests) == 1
    reset(stub).configure(fail_status=529, fail_count=1)
    with _jev(stub, max_retries=1, retry_budget_s=1.0) as b:
        p = b.predict(task, task.split("test")[:1])[0]
    assert p.label in task.labels and len(stub.requests) == 2


def test_sdk_defaults_would_break_realtime_slo():
    """Documents (and pins) the SDK defaults that motivate the explicit settings."""
    assert typesafe_sdk.constants.DEFAULT_TIMEOUT == 10.0
    rp = RetryPolicy()
    assert rp.max_retries == 2 and rp.timeout == 30.0 and rp.backoff_initial == 0.5
    assert typesafe_sdk.constants.DEFAULT_MODEL == "jev-latest"  # hence the explicit pin
    assert typesafe_sdk.constants.BASE_URL_ENV == "TYPESAFE_BASE_URL"


def test_fanout_one_request_many_questions(stub):
    reset(stub)
    task = synthetic_task()
    extra = {"needs_human": {"type": "noul", "instructions": "Does the customer ask for a human agent?"},
             "urgency": {"type": "score", "instructions": "How urgent is this?", "criteria": ["low", "medium", "high"]}}
    with _jev(stub, fanout_questions=extra) as b:
        p = b.predict(task, task.split("test")[:1])[0]
        demo = b.fanout_token_demo(task, task.split("test")[0], extra)
    assert set(stub.requests[0]["body"]["questions"]) == {"intent", "needs_human", "urgency"}
    assert p.raw["fanout_k"] == 3 and set(p.raw["fanout_answers"]) == {"needs_human", "urgency"}
    assert demo["k"] == 3 and demo["provenance"] == "MOCK:jev"
    assert demo["fanout_input_tokens"] < demo["separate_input_tokens"]  # state + overhead paid once


def test_build_choice_question_limits():
    task = synthetic_task()
    q = build_choice_question(task)
    assert q.model_dump(exclude_none=True)["type"] == "choice"
    with pytest.raises(ValueError):
        build_choice_question(task, labels_order=["card_arrival"])


def test_live_mode_requires_key(monkeypatch):
    monkeypatch.delenv("TYPESAFE_API_KEY", raising=False)
    monkeypatch.delenv("TYPESAFE_BASE_URL", raising=False)
    with pytest.raises(RuntimeError, match="TYPESAFE_API_KEY"):
        JevBackend({"mode": "live"})


def test_stub_mode_never_forwards_env_key(stub, monkeypatch):
    reset(stub)
    monkeypatch.setenv("TYPESAFE_API_KEY", "sk-looks-real-but-is-not")
    task = synthetic_task()
    with _jev(stub) as b:
        b.predict(task, task.split("test")[:1])
    assert stub.requests[0]["headers"]["authorization"] == "<dummy-key>"


def test_live_mode_refuses_loopback(monkeypatch, stub):
    monkeypatch.setenv("TYPESAFE_API_KEY", "sk-looks-real-but-is-not")
    with pytest.raises(RuntimeError, match="loopback"):
        JevBackend({"mode": "live", "base_url": stub.base_url})
