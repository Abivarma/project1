"""Jev (TypeSafe "System One") backend, using the REAL TypeSafe Python SDK. Owner: LAB-B.

SDK: PyPI ``typesafe-sdk`` == 0.7.4 (import name ``typesafe_sdk``), installed 2026-10-11.
Docs used (fetched 2026-10-11; untrusted data, read for signatures only):
  - client:     https://docs.typesafe.ai/sdk/python/api/clients/sync.md
  - questions:  https://docs.typesafe.ai/sdk/python/api/types/questions.md
  - responses:  https://docs.typesafe.ai/sdk/python/api/types/responses.md
  - retries:    https://docs.typesafe.ai/sdk/python/api/retries.md
  - constants:  https://docs.typesafe.ai/sdk/python/api/constants.md
  - exceptions: https://docs.typesafe.ai/sdk/python/api/exceptions.md
  - wire shape: https://docs.typesafe.ai/api.md

What one decision is: a Choice question. ``state`` = the utterance (plain string);
``instructions`` = Task.instructions; ``criteria`` = {label: label_description} in presentation order.
The answer gives ``choice``, the full ``probabilities`` map and a ``confidence``
(= (p_max - 1/n)/(1 - 1/n), https://docs.typesafe.ai/confidence.md#choice), kept in Prediction.raw.

REAL-TIME SETTINGS (critic fix 2/11; PLAN §0.4). The SDK defaults would break a 300 ms SLO:
  - DEFAULT_TIMEOUT = 10.0 s per HTTP operation (constants.md),
  - RetryPolicy() = max_retries 2, backoff 0.5 s doubling to 5 s, total retry budget 30 s (retries.md),
  so one slow or 429/529 call can block the decision path for up to ~30 s (100x the SLO).
  This backend therefore sets explicitly (configurable, configs/jev.yaml):
  - timeout_s (default 0.25 s, per HTTP operation; it is a per-operation bound, not a whole-request
    deadline, so total wall-clock <= (max_retries + 1) x (connect + read) in the worst case),
  - max_retries (default 0) and retry_budget_s (default 0.3 s; RetryPolicy.timeout),
  and on timeout / 429 / 5xx it returns Prediction(label=None, raw.error=...) so the caller applies its
  fail-open / fail-closed fallback (e.g. C1a or L2) instead of waiting.

Model pinning: requests send model="jev-1.13.0" (not the moving alias "jev-latest"); every response's
``model`` field is checked against the pin (models.md: "pin that version's ID").

Provenance: "LIVE:jev:jev-1.13.0" for the real API; "MOCK:jev" whenever the base URL is loopback, the
config says stub, or the response carries the stub watermark header. LIVE MODE IS UNTESTED HERE (no keys).
"""
from __future__ import annotations

import math
import time
from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

import typesafe_sdk
from typesafe_sdk import (
    Choice,
    RetryPolicy,
    TypeSafeAPIConnectionError,
    TypeSafeAPIError,
    TypeSafeAPITimeoutError,
    TypeSafeClient,
)

from jevlab.backends._vendor import MOCK_HEADER, provenance, resolve_api_key
from jevlab.types import Item, Prediction, Task

PINNED_MODEL = "jev-1.13.0"
QUESTION_ID = "intent"
SIGNUP_HINT = ("Jev is early access with a waitlist: request access and create a key at https://console.typesafe.ai/ "
               "then `export TYPESAFE_API_KEY=...`. See lab/LEARNING.md (Vendor backends).")

RUNNER_KEYS = ("name", "kind", "modes", "quant")  # keys of a runner `backends:` entry that are not backend settings


@dataclass
class JevConfig:
    mode: str = "stub"  # "stub" | "live"
    model: str = PINNED_MODEL
    base_url: str | None = None  # None -> SDK resolves TYPESAFE_BASE_URL, then https://api.typesafe.ai
    api_key_env: str = "TYPESAFE_API_KEY"
    timeout_s: float = 0.25
    max_retries: int = 0
    retry_budget_s: float = 0.3
    backoff_initial_s: float = 0.02
    backoff_max_s: float = 0.05
    question_id: str = QUESTION_ID
    # Speculative fan-out (PLAN P6): extra questions asked over the SAME state in the same request.
    # Mapping of question id -> raw question dict, e.g. {"needs_human": {"type": "noul", "instructions": "..."}}
    fanout_questions: dict[str, dict] = field(default_factory=dict)
    # [Guessing until R3 verifies] list price: $0.042 per 1M input tokens, output not billed (models.md)
    usd_per_m_input: float = 0.042
    usd_per_m_output: float = 0.0

    @classmethod
    def from_dict(cls, d: Mapping[str, Any]) -> "JevConfig":
        unknown = set(d) - set(cls.__dataclass_fields__)
        if unknown:  # fail loudly on config typos (LL2 spirit)
            raise ValueError(f"unknown jev config keys: {sorted(unknown)}")
        return cls(**dict(d))


def build_choice_question(task: Task, labels_order: Sequence[str] | None = None) -> Choice:
    """Choice question per https://docs.typesafe.ai/sdk/python/api/types/questions.md (Choice(instructions, criteria))."""
    order = list(labels_order) if labels_order is not None else list(task.labels)
    if sorted(order) != sorted(task.labels):
        raise ValueError("labels_order must be a permutation of task.labels")
    if len(order) > 255:
        raise ValueError("Jev Choice supports at most 255 options (api.md)")
    criteria = {lab: task.label_descriptions.get(lab) for lab in order}
    # typesafe_sdk.Choice(instructions=..., criteria=...)  -- docs: sdk/python/api/types/questions.md#typesafe_sdk.Choice
    return Choice(instructions=task.instructions, criteria=criteria)


class JevBackend:
    """DecisionBackend over the TypeSafe SDK (see jevlab.types.DecisionBackend)."""

    name = "jev"
    mode = "vendor"

    def __init__(self, config: JevConfig | Mapping[str, Any] | None = None) -> None:
        self.cfg = config if isinstance(config, JevConfig) else JevConfig.from_dict(config or {})
        api_key = resolve_api_key(self.cfg.mode, self.cfg.api_key_env, self.cfg.base_url or _env_base_url(),
                                  "jev", SIGNUP_HINT)
        self.retry_policy = RetryPolicy(  # docs: https://docs.typesafe.ai/sdk/python/api/retries.md
            max_retries=self.cfg.max_retries,
            backoff_initial=self.cfg.backoff_initial_s,
            backoff_max=self.cfg.backoff_max_s,
            timeout=self.cfg.retry_budget_s,
        )
        # TypeSafeClient(*, api_key, model, retry, timeout, headers, transport, http_client, base_url)
        # docs: https://docs.typesafe.ai/sdk/python/api/clients/sync.md#typesafe_sdk.TypeSafeClient
        self.client = TypeSafeClient(
            api_key=api_key,
            model=self.cfg.model,
            retry=self.retry_policy,
            timeout=self.cfg.timeout_s,
            base_url=self.cfg.base_url,
        )
        self._calls = 0
        self.sdk_version = typesafe_sdk.__version__

    # ----------------------------------------------------------------------------------
    @property
    def effective_base_url(self) -> str:
        return self.cfg.base_url or _env_base_url() or typesafe_sdk.constants.DEFAULT_BASE_URL

    def _provenance(self, mock_header_seen: bool) -> str:
        return provenance("jev", self.cfg.model, mode=self.cfg.mode, base_url=self.effective_base_url,
                          mock_header_seen=mock_header_seen)

    def close(self) -> None:
        self.client.close()  # docs: sdk/python/api/clients/sync.md#typesafe_sdk.TypeSafeClient.close

    def __enter__(self) -> "JevBackend":
        return self

    def __exit__(self, *exc: Any) -> None:
        self.close()

    # ----------------------------------------------------------------------------------
    def _ask(self, state: Any, questions: Mapping[str, Any]) -> tuple[Any, float, dict]:
        """One System One request. Returns (response | None, latency_s, error_info)."""
        t0 = time.perf_counter()
        try:
            # client.system_one(state, questions, *, model, retry, timeout, extra_headers, extra_body, response_model)
            # docs: https://docs.typesafe.ai/sdk/python/api/clients/sync.md#typesafe_sdk.TypeSafeClient.system_one
            resp = self.client.system_one(state, questions, model=self.cfg.model)
            return resp, time.perf_counter() - t0, {}
        except TypeSafeAPITimeoutError as e:  # docs: sdk/python/api/exceptions.md
            return None, time.perf_counter() - t0, {"error": "timeout", "detail": str(e)[:200]}
        except TypeSafeAPIConnectionError as e:
            return None, time.perf_counter() - t0, {"error": "connection", "detail": str(e)[:200]}
        except TypeSafeAPIError as e:
            mock = bool(getattr(e, "headers", None) and (e.headers or {}).get(MOCK_HEADER))
            return None, time.perf_counter() - t0, {"error": f"http_{e.status}", "detail": str(e)[:200],
                                                    "request_id": e.request_id, "mock_header": mock}

    def _to_prediction(self, task: Task, item: Item, resp: Any, latency: float, err: dict, cold: bool) -> Prediction:
        if resp is None:
            return Prediction(item_id=item.id, label=None, probs=None, latency_s=latency, input_tokens=None,
                              output_tokens=None, provenance=self._provenance(bool(err.get("mock_header"))),
                              cold=cold, raw={**err, "model_requested": self.cfg.model})
        headers = resp.raw_http_response.headers  # docs: sdk/python/api/types/responses.md (raw_http_response)
        mock_seen = headers.get(MOCK_HEADER) is not None
        ans = resp.choices.get(self.cfg.question_id)  # SystemOneResponse.choices -> dict[str, ChoiceAnswer]
        usage = resp.usage  # Usage(input_tokens, output_tokens), either may be None
        raw: dict[str, Any] = {
            "model_requested": self.cfg.model,
            "model_answered": resp.model,
            "request_id": resp.request_id,
            "usage": {"input_tokens": usage.input_tokens, "output_tokens": usage.output_tokens},
            "usd": _usd(usage.input_tokens, usage.output_tokens, self.cfg),
        }
        if resp.model != self.cfg.model:
            raw["model_mismatch"] = True
        if ans is None:
            raw["error"] = "no_choice_answer"
            return Prediction(item.id, None, None, latency, usage.input_tokens, usage.output_tokens,
                              self._provenance(mock_seen), cold=cold, usd=raw["usd"], raw=raw)
        probs = {lab: float(ans.probabilities.get(lab, 0.0)) for lab in task.labels}
        extra = set(ans.probabilities) - set(task.labels)
        s = sum(probs.values())
        raw.update({"confidence": ans.confidence, "choice_raw": ans.choice, "prob_sum": s})
        if extra:
            raw["unknown_options"] = sorted(extra)
        label = ans.choice if ans.choice in task.labels else None
        if label is None:
            raw["error"] = "choice_not_in_labels"
        if s > 0 and abs(s - 1.0) > 1e-9:
            probs = {k: v / s for k, v in probs.items()}
        others = {qid: a.model_dump() for qid, a in resp.answers.items() if qid != self.cfg.question_id}
        if others:
            raw["fanout_answers"] = others
            raw["fanout_k"] = 1 + len(others)
        return Prediction(item_id=item.id, label=label, probs=probs, latency_s=latency,
                          input_tokens=usage.input_tokens, output_tokens=usage.output_tokens,
                          provenance=self._provenance(mock_seen), cold=cold, usd=raw["usd"], raw=raw)

    # ------------------------------- DecisionBackend ----------------------------------
    def predict(self, task: Task, items: Sequence[Item], labels_order: Sequence[str] | None = None) -> list[Prediction]:
        question = build_choice_question(task, labels_order)
        questions: dict[str, Any] = {self.cfg.question_id: question, **self.cfg.fanout_questions}
        out: list[Prediction] = []
        for item in items:
            cold = self._calls == 0
            resp, latency, err = self._ask(item.text, questions)
            self._calls += 1
            out.append(self._to_prediction(task, item, resp, latency, err, cold))
        return out

    def probe(self, task: Task) -> dict:
        """LL2 capability probe: one real request; raise RuntimeError loudly on anything unexpected."""
        item = (task.split("test") or list(task.items))[0]
        pred = self.predict(task, [item])[0]
        r = pred.raw
        problems = []
        if pred.label is None:
            problems.append(f"no valid label ({r.get('error')}: {r.get('detail', '')})")
        if pred.probs is None or not math.isclose(sum(pred.probs.values()), 1.0, abs_tol=1e-6):
            problems.append("probabilities missing or not normalisable")
        if r.get("prob_sum") is not None and abs(r["prob_sum"] - 1.0) > 0.02:
            problems.append(f"probabilities sum to {r['prob_sum']:.4f} (api.md: sum to 1)")
        if r.get("unknown_options"):
            problems.append(f"answer has options not in criteria: {r['unknown_options']}")
        conf = r.get("confidence")
        if conf is None or not (0.0 <= conf <= 1.0):
            problems.append(f"confidence missing or outside [0,1]: {conf}")
        if r.get("model_mismatch"):
            problems.append(f"answered by {r.get('model_answered')!r}, pinned {self.cfg.model!r}")
        if pred.input_tokens is None:
            problems.append("usage.input_tokens not reported")
        if problems:
            raise RuntimeError("Jev probe failed: " + "; ".join(problems))
        return {"backend": self.name, "provenance": pred.provenance, "model": r.get("model_answered"),
                "sdk": f"typesafe-sdk {self.sdk_version}", "has_distribution": True, "has_confidence": True,
                "timeout_s": self.cfg.timeout_s, "max_retries": self.cfg.max_retries,
                "retry_budget_s": self.cfg.retry_budget_s, "probe_latency_s": pred.latency_s,
                "probe_input_tokens": pred.input_tokens}

    # ------------------------------- token-accounting demo ----------------------------
    def fanout_token_demo(self, task: Task, item: Item, extra_questions: Mapping[str, dict]) -> dict:
        """Speculative fan-out demo (PLAN P6): k questions in ONE request vs k separate requests over the same state.

        Jev ingests the state once per request, so fan-out pays the state (+ fixed overhead) once.
        With the stub, the token counts are MOCK (a ~4 chars/token model) and only illustrate the arithmetic.
        """
        q_intent = build_choice_question(task)
        allq: dict[str, Any] = {self.cfg.question_id: q_intent, **extra_questions}
        one, lat_one, err1 = self._ask(item.text, allq)
        sep_in = sep_out = 0
        sep_lat = 0.0
        for qid, q in allq.items():
            r, lat, err = self._ask(item.text, {qid: q})
            if r is None:
                raise RuntimeError(f"fan-out demo request failed: {err}")
            sep_in += r.usage.input_tokens or 0
            sep_out += r.usage.output_tokens or 0
            sep_lat += lat
        if one is None:
            raise RuntimeError(f"fan-out demo request failed: {err1}")
        mock = one.raw_http_response.headers.get(MOCK_HEADER) is not None
        return {
            "provenance": self._provenance(mock), "k": len(allq),
            "fanout_input_tokens": one.usage.input_tokens, "fanout_output_tokens": one.usage.output_tokens,
            "separate_input_tokens": sep_in, "separate_output_tokens": sep_out,
            "fanout_latency_s": lat_one, "separate_latency_s_sequential": sep_lat,
            "fanout_usd": _usd(one.usage.input_tokens, one.usage.output_tokens, self.cfg),
            "separate_usd": _usd(sep_in, sep_out, self.cfg),
        }


def _env_base_url() -> str | None:
    import os

    v = (os.environ.get(typesafe_sdk.constants.BASE_URL_ENV) or "").strip()  # 'TYPESAFE_BASE_URL' (constants.md)
    return v or None


def _usd(inp: int | None, out: int | None, cfg: JevConfig) -> float | None:
    if inp is None:
        return None
    return inp * cfg.usd_per_m_input / 1e6 + (out or 0) * cfg.usd_per_m_output / 1e6


def make_backend(cfg: Mapping[str, Any] | None = None) -> JevBackend:
    """Factory for LAB-A's runner. Accepts a `backends:` list entry (kind: jev) from configs/jev.yaml;
    runner-level keys (name, kind, modes) are ignored, every other key must be a JevBackend config field."""
    d = {k: v for k, v in dict(cfg or {}).items() if k not in RUNNER_KEYS}
    return JevBackend(d)