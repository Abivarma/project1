"""Local HTTP stub for the Jev (TypeSafe) and Anthropic APIs. Every response it serves is MOCK.

Why this exists (critic fix 11, PLAN §6): there are no API keys in this environment and
Jev has a waitlist. The stub lets the REAL vendor SDKs (typesafe-sdk, anthropic) run their
full request/serialise/HTTP/parse code paths end to end, without keys and without network.

Endpoints
---------
POST /v1/systemone   TypeSafe System One. Request/response shapes follow
                     https://docs.typesafe.ai/api.md (state, model, questions -> model, answers, usage).
                     The documented examples in api.md are replayed VERBATIM when the request matches.
                     Any other request gets a deterministic fake distribution (seeded by a hash of
                     the request), so tests are repeatable. Fake numbers mean nothing.
POST /v1/messages    Anthropic Messages API, structured-output shape: one text block holding JSON
                     that satisfies output_config.format, plus a usage block (with simulated prompt
                     caching). Shape per https://platform.claude.com/docs/en/api/messages.
GET  /__stub/requests        Recorded requests (bodies + non-secret headers) for contract tests.
POST /__stub/config          Fault injection: {"delay_ms": int, "fail_status": int, "fail_count": int,
                             "jev_model_override": str, "jev_bad_probs": bool,
                             "claude_refuse": bool, "claude_thinking_block": bool, "claude_case_flip": bool}
POST /__stub/reset           Clear recorded requests, config, caches and counters.

Watermarks: every response carries the header ``x-jevlab-mock: 1``; request ids are prefixed
``mock-``. Backends set provenance "MOCK:<backend>" whenever they talk to this server.

Run standalone:  python -m jevlab.stub_server --port 8765
Then point the SDKs at it: TypeSafeClient(base_url="http://127.0.0.1:8765", api_key="stub-not-a-real-key")
and anthropic.Anthropic(base_url="http://127.0.0.1:8765", api_key="stub-not-a-real-key").
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import random
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

MOCK_HEADER = "x-jevlab-mock"
DUMMY_KEY = "stub-not-a-real-key"
STUB_JEV_MODEL = "jev-1.13.0"  # what jev-latest / jev-1.13.0 resolve to per https://docs.typesafe.ai/models.md

# Minimum cacheable prompt per model, from the claude-api skill shared/prompt-caching.md
# ("Claude Haiku 5.5 ... 512 tokens"). Used only to SIMULATE cache usage fields.
CLAUDE_MIN_CACHEABLE = {"claude-haiku-5-5": 512}
CLAUDE_DEFAULT_MIN_CACHEABLE = 1024

# --------------------------------------------------------------------------------------
# Documented examples from https://docs.typesafe.ai/api.md (fetched 2026-10-11), replayed
# verbatim when the incoming request matches (state + questions, ignoring the model alias).
# --------------------------------------------------------------------------------------
_DOC_STATE = "Help! My payouts have been failing for 3 days."
DOCUMENTED_EXAMPLES: list[tuple[dict, dict]] = [
    (
        {"state": _DOC_STATE, "questions": {"is_urgent": {"type": "noul", "instructions": "Does this convey urgency?"}}},
        {"model": "jev-1.13.0", "answers": {"is_urgent": {"type": "noul", "noul": 0.95}},
         "usage": {"input_tokens": 296, "output_tokens": 20}},
    ),
    (
        {"state": _DOC_STATE, "questions": {"is_urgent": {
            "type": "noul", "instructions": "Does this convey urgency?",
            "criteria": {"true": "Explicitly time-sensitive", "false": "No urgency expressed"}}}},
        {"model": "jev-1.13.0", "answers": {"is_urgent": {"type": "noul", "noul": 0.95}},
         "usage": {"input_tokens": 307, "output_tokens": 20}},
    ),
    (
        {"state": _DOC_STATE, "questions": {"department": {
            "type": "choice", "instructions": "Which team should handle this?",
            "criteria": {"billing": "Payments, invoicing, refunds", "technical": "Bugs, outages, integrations",
                         "sales": "Pricing, upgrades, new accounts"}}}},
        {"model": "jev-1.13.0", "answers": {"department": {
            "type": "choice", "choice": "billing",
            "probabilities": {"billing": 0.88, "technical": 0.12, "sales": 0.0}, "confidence": 0.81}},
         "usage": {"input_tokens": 318, "output_tokens": 34}},
    ),
    (
        {"state": _DOC_STATE, "questions": {"frustration": {
            "type": "score", "instructions": "How frustrated is the customer?",
            "criteria": ["Calm", "Frustrated", "Very angry"]}}},
        {"model": "jev-1.13.0", "answers": {"frustration": {
            "type": "score", "score": 1.05, "legend": {"0": "Calm", "1": "Frustrated", "2": "Very angry"},
            "probabilities": {"0": 0.0, "1": 0.95, "2": 0.05}, "confidence": 0.92}},
         "usage": {"input_tokens": 304, "output_tokens": 18}},
    ),
]


def _canon(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _seed(*parts: Any) -> int:
    h = hashlib.sha256("\x1f".join(_canon(p) for p in parts).encode()).hexdigest()
    return int(h[:16], 16)


def _approx_tokens(obj: Any) -> int:
    """Crude ~4 chars/token estimate. MOCK only; never used as a measured number."""
    s = obj if isinstance(obj, str) else _canon(obj)
    return max(1, math.ceil(len(s) / 4))


def _fake_distribution(rng: random.Random, n: int, sharpness: float = 2.5) -> list[float]:
    """Deterministic, peaked fake distribution over n options (softmax of seeded gaussians)."""
    logits = [rng.gauss(0.0, 1.0) * sharpness for _ in range(n)]
    mx = max(logits)
    ex = [math.exp(v - mx) for v in logits]
    z = sum(ex)
    probs = [round(e / z, 4) for e in ex]
    # make the rounded floats sum to exactly 1 (to 4 dp) by fixing up the largest entry
    probs[probs.index(max(probs))] += round(1.0 - sum(probs), 4)
    return [max(0.0, round(p, 4)) for p in probs]


def _choice_confidence(probs: list[float]) -> float:
    # Formula from https://docs.typesafe.ai/confidence.md#choice
    n = len(probs)
    return 1.0 if n == 1 else max(0.0, min(1.0, (max(probs) - 1 / n) / (1 - 1 / n)))


def _score_confidence(probs: list[float]) -> float:
    # Formula from https://docs.typesafe.ai/confidence.md#score
    n = len(probs)
    m = probs.index(max(probs))
    spread = sum(p * abs(i - m) for i, p in enumerate(probs))
    even = sum(abs(i - (n - 1) / 2) for i in range(n)) / n
    return max(0.0, 1 - spread / even) if even else 1.0


class StubState:
    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.reset()

    def reset(self) -> None:
        self.requests: list[dict] = []
        self.config: dict[str, Any] = {}
        self.claude_cache: set[str] = set()
        self.sample_counter: dict[str, int] = {}


# ------------------------------- validation (api.md) ---------------------------------
class _Invalid(Exception):
    pass


def validate_systemone(body: Any) -> None:
    """Server-side validation mirroring https://docs.typesafe.ai/api.md (422 on failure)."""
    if not isinstance(body, dict):
        raise _Invalid("body must be a JSON object")
    for f in ("state", "model", "questions"):
        if f not in body:
            raise _Invalid(f"missing required field: {f}")
    if body["state"] is None or not isinstance(body["state"], (str, dict, list)):
        raise _Invalid("state must be a string, object or array")
    if not isinstance(body["model"], str) or not body["model"]:
        raise _Invalid("model must be a non-empty string")
    qs = body["questions"]
    if not isinstance(qs, dict) or not qs:
        raise _Invalid("questions must be a non-empty map")
    for qid, q in qs.items():
        if not isinstance(q, dict) or q.get("type") not in ("noul", "choice", "score"):
            raise _Invalid(f"questions.{qid}.type must be noul|choice|score")
        t = q["type"]
        if t in ("choice", "score") and "instructions" not in q:
            raise _Invalid(f"questions.{qid}.instructions is required")
        if t == "noul" and "instructions" not in q and not q.get("criteria"):
            raise _Invalid(f"questions.{qid} needs instructions or criteria")
        if t == "choice":
            c = q.get("criteria")
            if not isinstance(c, dict) or not c:
                raise _Invalid(f"questions.{qid}.criteria must be a non-empty map")
            if len(c) > 255:
                raise _Invalid(f"questions.{qid}.criteria has more than 255 options")
        if t == "score":
            c = q.get("criteria")
            if not isinstance(c, list) or not (2 <= len(c) <= 10):
                raise _Invalid(f"questions.{qid}.criteria must be an array of 2..10 levels")


def systemone_response(body: dict) -> dict:
    # 1) documented examples, verbatim
    for req, resp in DOCUMENTED_EXAMPLES:
        if _canon(req["state"]) == _canon(body["state"]) and _canon(req["questions"]) == _canon(body["questions"]):
            return json.loads(json.dumps(resp))
    # 2) deterministic fake answers (MOCK)
    answers: dict[str, dict] = {}
    out_tokens = 0
    for qid, q in body["questions"].items():
        rng = random.Random(_seed(body["state"], qid, q))
        if q["type"] == "noul":
            p = round(rng.random(), 4)
            answers[qid] = {"type": "noul", "noul": p}
            out_tokens += 20
        elif q["type"] == "choice":
            opts = list(q["criteria"].keys())
            probs = _fake_distribution(rng, len(opts))
            best = opts[probs.index(max(probs))]
            answers[qid] = {"type": "choice", "choice": best,
                            "probabilities": dict(zip(opts, probs)),
                            "confidence": round(_choice_confidence(probs), 4)}
            out_tokens += 14 + 7 * len(opts)
        else:
            levels = q["criteria"]
            probs = _fake_distribution(rng, len(levels))
            answers[qid] = {"type": "score",
                            "score": round(sum(i * p for i, p in enumerate(probs)), 4),
                            "legend": {str(i): lv for i, lv in enumerate(levels)},
                            "probabilities": {str(i): p for i, p in enumerate(probs)},
                            "confidence": round(_score_confidence(probs), 4)}
            out_tokens += 18
    # Token model [MOCK]: ~300 fixed overhead + state + per-question text (cf. api.md usage examples)
    in_tokens = 280 + _approx_tokens(body["state"]) + sum(_approx_tokens(q) for q in body["questions"].values())
    model = STUB_JEV_MODEL if body["model"] in ("jev-latest", "jev-preview", "jev-1.13.0") else body["model"]
    return {"model": model, "answers": answers, "usage": {"input_tokens": in_tokens, "output_tokens": out_tokens}}


# ------------------------------- Anthropic /v1/messages -------------------------------
def _text_of(system: Any) -> str:
    if isinstance(system, str):
        return system
    if isinstance(system, list):
        return "".join(b.get("text", "") for b in system if isinstance(b, dict))
    return ""


def _cached_prefix(body: dict) -> tuple[str | None, int]:
    """Return (cache key, token estimate) of the prefix up to the last cache_control breakpoint."""
    prefix: list[Any] = []
    key, toks = None, 0
    if body.get("tools"):
        prefix.append(body["tools"])
    system = body.get("system")
    if isinstance(system, list):
        for blk in system:
            prefix.append(blk.get("text", "") if isinstance(blk, dict) else blk)
            if isinstance(blk, dict) and blk.get("cache_control"):
                key = _canon([body.get("model"), prefix])
                toks = sum(_approx_tokens(p) for p in prefix)
    if key is None and body.get("cache_control"):  # top-level automatic caching
        prefix.append(system if isinstance(system, str) else _text_of(system))
        key = _canon([body.get("model"), prefix])
        toks = sum(_approx_tokens(p) for p in prefix)
    return key, toks


def validate_messages(body: Any) -> None:
    if not isinstance(body, dict):
        raise _Invalid("body must be a JSON object")
    for f in ("model", "max_tokens", "messages"):
        if f not in body:
            raise _Invalid(f"{f}: Field required")
    if "output_format" in body:
        raise _Invalid("output_format is deprecated; use output_config.format")
    msgs = body["messages"]
    if not isinstance(msgs, list) or not msgs or msgs[0].get("role") != "user":
        raise _Invalid("messages must be a non-empty list starting with a user turn")
    if msgs[-1].get("role") == "assistant" and str(body["model"]).startswith("claude-haiku-5"):
        raise _Invalid("assistant prefill is not supported on this model")
    if str(body["model"]).startswith("claude-haiku-5"):
        for p in ("top_k",):
            if p in body:
                raise _Invalid(f"{p} is not supported on this model")
        if "temperature" in body and body["temperature"] != 1:
            raise _Invalid("temperature must be 1 on this model")
        th = body.get("thinking") or {}
        if th.get("type") == "enabled":
            raise _Invalid("thinking.type=enabled (budget_tokens) is not supported on this model")
        eff = (body.get("output_config") or {}).get("effort")
        if th.get("type") == "disabled" and eff in ("xhigh", "max"):
            raise _Invalid("thinking disabled is not allowed with effort xhigh/max")
    fmt = (body.get("output_config") or {}).get("format")
    if fmt is not None and (fmt.get("type") != "json_schema" or not isinstance(fmt.get("schema"), dict)):
        raise _Invalid("output_config.format must be {type: json_schema, schema: {...}}")


def _schema_instance(schema: dict, rng: random.Random, case_flip: bool) -> Any:
    t = schema.get("type")
    if "enum" in schema:
        opts = list(schema["enum"])
        probs = _fake_distribution(random.Random(rng.random()), len(opts))
        v = rng.choices(opts, weights=probs, k=1)[0]
        if case_flip and isinstance(v, str):
            v = v[:1].swapcase() + v[1:]
        return v
    if t == "object":
        return {k: _schema_instance(s, rng, case_flip) for k, s in (schema.get("properties") or {}).items()}
    if t == "array":
        return [_schema_instance(schema.get("items") or {"type": "string"}, rng, case_flip)]
    if t == "integer":
        return rng.randint(0, 9)
    if t == "number":
        return round(rng.random(), 3)
    if t == "boolean":
        return rng.random() < 0.5
    return "mock"


def messages_response(body: dict, st: StubState) -> dict:
    cfg = st.config
    model = body["model"]
    user_text = _canon(body["messages"])
    base_seed = _seed(model, _text_of(body.get("system")), user_text)
    with st.lock:
        n = st.sample_counter.get(str(base_seed), 0)
        st.sample_counter[str(base_seed)] = n + 1
    # Per-content distribution is fixed; each repeat draws a new SAMPLE from it (temperature-1 analogue).
    rng = random.Random(base_seed * 1_000_003 + n)

    # usage with simulated prompt caching
    key, prefix_toks = _cached_prefix(body)
    total_in = _approx_tokens(body.get("system") or "") + _approx_tokens(body["messages"]) + 8
    min_cache = CLAUDE_MIN_CACHEABLE.get(model, CLAUDE_DEFAULT_MIN_CACHEABLE)
    cache_write = cache_read = 0
    if key is not None and prefix_toks >= min_cache:
        with st.lock:
            if key in st.claude_cache:
                cache_read = prefix_toks
            else:
                st.claude_cache.add(key)
                cache_write = prefix_toks
    uncached_in = max(1, total_in - cache_write - cache_read)

    content: list[dict] = []
    if cfg.get("claude_thinking_block") or (body.get("thinking") or {}).get("type") == "adaptive":
        # Haiku 5.5 omits thinking text by default (display omitted): empty text + signature
        content.append({"type": "thinking", "thinking": "", "signature": "mock-signature"})
    if cfg.get("claude_refuse"):
        content.append({"type": "text", "text": "I can't help with that."})
        stop_reason = "refusal"
    else:
        fmt = (body.get("output_config") or {}).get("format")
        if fmt:
            payload = _schema_instance(fmt["schema"], rng, bool(cfg.get("claude_case_flip")))
            content.append({"type": "text", "text": json.dumps(payload)})
        else:
            content.append({"type": "text", "text": "mock reply"})
        stop_reason = "end_turn"
    out_tokens = sum(_approx_tokens(b.get("text", "")) for b in content) + 2
    return {
        "id": f"msg_mock_{base_seed:x}_{n}",
        "type": "message",
        "role": "assistant",
        "model": model,
        "content": content,
        "stop_reason": stop_reason,
        "stop_sequence": None,
        "usage": {
            "input_tokens": uncached_in,
            "output_tokens": out_tokens,
            "cache_creation_input_tokens": cache_write,
            "cache_read_input_tokens": cache_read,
        },
    }


# ------------------------------------ HTTP layer --------------------------------------
_SECRET = {"authorization", "x-api-key", "api-key", "cookie", "proxy-authorization"}


def _make_handler(st: StubState):
    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"
        server_version = "jevlab-stub/0.1 (MOCK)"
        disable_nagle_algorithm = True  # avoid ~40 ms Nagle/delayed-ACK stalls on keep-alive connections

        def log_message(self, fmt: str, *args: Any) -> None:  # keep test output quiet
            pass

        def _send(self, status: int, payload: Any, extra: dict[str, str] | None = None) -> None:
            data = json.dumps(payload).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.send_header(MOCK_HEADER, "1")
            for k, v in (extra or {}).items():
                self.send_header(k, v)
            self.end_headers()
            self.wfile.write(data)

        def _record(self, body: Any) -> None:
            hdrs = {}
            for k, v in self.headers.items():
                lk = k.lower()
                if lk in _SECRET:
                    # never store secrets; only whether the dummy key was used
                    hdrs[lk] = "<dummy-key>" if DUMMY_KEY in v else "<redacted-non-dummy>"
                else:
                    hdrs[lk] = v
            with st.lock:
                st.requests.append({"path": self.path, "headers": hdrs, "body": body, "t": time.time()})

        def do_GET(self) -> None:  # noqa: N802
            if self.path == "/__stub/requests":
                with st.lock:
                    self._send(200, {"requests": list(st.requests)})
            elif self.path == "/v1/models":
                self._send(200, {"models": [
                    {"name": "jev-latest", "description": "MOCK alias", "release_date": "2026-10-11"},
                    {"name": "jev-preview", "description": "MOCK alias", "release_date": "2026-10-11"}]})
            else:
                self._send(404, {"error": "not found (stub)"})

        def do_POST(self) -> None:  # noqa: N802
            length = int(self.headers.get("Content-Length") or 0)
            raw = self.rfile.read(length) if length else b""
            try:
                body = json.loads(raw.decode() or "null")
            except json.JSONDecodeError:
                self._send(400, {"error": "invalid JSON"})
                return
            if self.path == "/__stub/reset":
                with st.lock:
                    st.reset()
                self._send(200, {"ok": True})
                return
            if self.path == "/__stub/config":
                with st.lock:
                    st.config.update(body or {})
                self._send(200, {"ok": True, "config": st.config})
                return
            if self.path not in ("/v1/systemone", "/v1/messages"):
                self._send(404, {"error": f"unknown path {self.path} (stub)"})
                return
            self._record(body)
            cfg = st.config
            if cfg.get("delay_ms"):
                time.sleep(cfg["delay_ms"] / 1000.0)
            with st.lock:
                failing = cfg.get("fail_count", 0) > 0 and cfg.get("fail_status")
                if failing:
                    cfg["fail_count"] -= 1
            if failing:
                self._send(int(cfg["fail_status"]), {"error": {"type": "mock_failure", "message": "injected by stub"}},
                           {"retry-after-ms": "1"})
                return
            rid = f"mock-{_seed(body, len(st.requests)) & 0xFFFFFFFF:08x}"
            try:
                if self.path == "/v1/systemone":
                    if not (self.headers.get("Authorization") or "").startswith("Bearer "):
                        self._send(401, {"detail": "Missing or invalid API key (stub)"})
                        return
                    validate_systemone(body)
                    resp = systemone_response(body)
                    if cfg.get("jev_model_override"):  # simulate alias drift / unpinned model
                        resp["model"] = cfg["jev_model_override"]
                    if cfg.get("jev_bad_probs"):  # simulate a malformed distribution
                        for a in resp["answers"].values():
                            if "probabilities" in a:
                                a["probabilities"] = {k: 0.5 for k in a["probabilities"]}
                    self._send(200, resp, {"x-typesafe-request-id": rid})
                else:
                    if not self.headers.get("x-api-key") and not self.headers.get("Authorization"):
                        self._send(401, {"type": "error", "error": {"type": "authentication_error",
                                                                     "message": "missing key (stub)"}})
                        return
                    validate_messages(body)
                    self._send(200, messages_response(body, st), {"request-id": f"req_{rid}"})
            except _Invalid as e:
                status = 422 if self.path == "/v1/systemone" else 400
                err = ({"detail": str(e)} if status == 422 else
                       {"type": "error", "error": {"type": "invalid_request_error", "message": str(e)}})
                self._send(status, err)

    return Handler


class StubServer:
    """In-process stub. Use as a context manager: ``with StubServer() as s: s.base_url``."""

    def __init__(self, host: str = "127.0.0.1", port: int = 0) -> None:
        self.state = StubState()
        self.httpd = ThreadingHTTPServer((host, port), _make_handler(self.state))
        self.httpd.daemon_threads = True
        self.thread: threading.Thread | None = None

    @property
    def base_url(self) -> str:
        host, port = self.httpd.server_address[:2]
        return f"http://{host}:{port}"

    def start(self) -> "StubServer":
        self.thread = threading.Thread(target=self.httpd.serve_forever, name="jevlab-stub", daemon=True)
        self.thread.start()
        return self

    def stop(self) -> None:
        self.httpd.shutdown()
        self.httpd.server_close()

    def __enter__(self) -> "StubServer":
        return self.start()

    def __exit__(self, *exc: Any) -> None:
        self.stop()

    # convenience for tests
    @property
    def requests(self) -> list[dict]:
        with self.state.lock:
            return list(self.state.requests)

    def configure(self, **cfg: Any) -> None:
        with self.state.lock:
            self.state.config.update(cfg)

    def reset(self) -> None:
        with self.state.lock:
            self.state.reset()


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description="jevlab MOCK stub for /v1/systemone and /v1/messages")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8765)
    args = ap.parse_args(argv)
    srv = StubServer(args.host, args.port)
    print(f"jevlab stub (MOCK) listening on {srv.base_url}  -- every response is MOCK", flush=True)
    try:
        srv.httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        srv.httpd.server_close()


if __name__ == "__main__":
    main()
