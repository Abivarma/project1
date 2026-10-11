"""MOCK watermark: everything that came from the stub is tagged MOCK (LL5, critic fix 11). Owner: LAB-B."""
from __future__ import annotations

import json
import urllib.request

from _b_helpers import reset, stub_fixture, synthetic_task
from jevlab.backends._vendor import is_loopback_url, provenance
from jevlab.backends.claude import ClaudeBackend
from jevlab.backends.jev import JevBackend
from jevlab.stub_server import MOCK_HEADER

stub = stub_fixture()


def _all_preds(stub):
    task = synthetic_task()
    items = task.split("test")
    preds = []
    with JevBackend({"mode": "stub", "base_url": stub.base_url}) as j:
        preds += j.predict(task, items)
        preds.append(_probe_pred(j.probe(task)))
    for conf in ("none", "self_consistency"):
        with ClaudeBackend({"mode": "stub", "base_url": stub.base_url, "confidence": conf, "k": 3}) as c:
            preds += c.predict(task, items)
            preds.append(_probe_pred(c.probe(task)))
    return preds


class _probe_pred:  # adapt probe dicts so the same assertion covers them
    def __init__(self, info: dict) -> None:
        self.provenance = info["provenance"]


def test_every_stub_prediction_is_mock(stub):
    preds = _all_preds(stub)
    assert preds
    for p in preds:
        assert p.provenance.startswith("MOCK:"), p.provenance
        assert "LIVE" not in p.provenance and "LAB:" not in p.provenance


def test_failed_calls_are_mock_too(stub):
    task = synthetic_task()
    reset(stub).configure(fail_status=529, fail_count=10)
    try:
        with JevBackend({"mode": "stub", "base_url": stub.base_url}) as j:
            (pj,) = j.predict(task, task.split("test")[:1])
        with ClaudeBackend({"mode": "stub", "base_url": stub.base_url}) as c:
            (pc,) = c.predict(task, task.split("test")[:1])
    finally:
        reset(stub)
    assert pj.label is None and pj.provenance == "MOCK:jev"
    assert pc.label is None and pc.provenance == "MOCK:claude"


def test_stub_watermarks_every_response(stub):
    reset(stub)
    req = urllib.request.Request(
        stub.base_url + "/v1/systemone", method="POST",
        data=json.dumps({"state": "x", "model": "jev-1.13.0",
                         "questions": {"q": {"type": "noul", "instructions": "y?"}}}).encode(),
        headers={"Content-Type": "application/json", "Authorization": "Bearer stub-not-a-real-key"})
    with urllib.request.urlopen(req) as r:
        assert r.headers.get(MOCK_HEADER) == "1"
        assert r.headers.get("x-typesafe-request-id", "").startswith("mock-")
    req422 = urllib.request.Request(stub.base_url + "/v1/systemone", method="POST", data=b"{}",
                                    headers={"Content-Type": "application/json", "Authorization": "Bearer x"})
    try:
        urllib.request.urlopen(req422)
        raise AssertionError("expected 422")
    except urllib.error.HTTPError as e:
        assert e.code == 422 and e.headers.get(MOCK_HEADER) == "1"


def test_provenance_rules():
    # loopback is always MOCK, whatever the config claims
    assert provenance("jev", "jev-1.13.0", mode="live", base_url="http://127.0.0.1:9", mock_header_seen=False) == "MOCK:jev"
    assert provenance("jev", "jev-1.13.0", mode="live", base_url="http://localhost:9", mock_header_seen=False) == "MOCK:jev"
    # the watermark header forces MOCK even for a remote-looking URL (e.g. a stub behind a tunnel)
    assert provenance("claude", "m", mode="live", base_url="https://example.test", mock_header_seen=True) == "MOCK:claude"
    assert provenance("jev", "jev-1.13.0", mode="live", base_url="https://api.typesafe.ai",
                      mock_header_seen=False) == "LIVE:jev:jev-1.13.0"
    assert provenance("claude", "claude-haiku-5-5", mode="live", base_url="https://api.anthropic.com",
                      mock_header_seen=False) == "LIVE:claude:claude-haiku-5-5"
    assert is_loopback_url("http://[::1]:8080") and not is_loopback_url("https://api.typesafe.ai")
