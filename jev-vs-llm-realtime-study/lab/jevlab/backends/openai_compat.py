"""ONE adapter for Ollama, LM Studio, llama.cpp llama-server and mlx-lm (LL1). Owner: LAB-A.

All four expose an OpenAI-compatible POST /v1/chat/completions. They differ in which
features work, so behaviour is driven by per-backend capability flags (config), not by
server-specific code paths, except where a server needs a different endpoint for logprobs:

  logprobs_endpoint = "chat_completions"   OpenAI /v1/chat/completions logprobs+top_logprobs
                                           (llama-server; Ollama >= v0.12.11; mlx-lm)
                    = "ollama_native"      Ollama POST /api/chat {"logprobs": true, "top_logprobs": k}
                    = "lmstudio_responses" LM Studio POST /v1/responses with
                                           include=["message.output_text.logprobs"] (UNTESTED here)

Modes
  json_schema      The LLM way. response_format json_schema with enum = labels; parse
                   {"label": ...}. If json_logprobs is on, the generated label's sequence
                   probability is used as a top-label confidence (rest spread uniformly).
  logprob_scoring  Jev-style decision primitive (emulation). Options get single-token
                   codes; the code distribution at the label position is the option
                   distribution (scoring.py). Items with captured mass < threshold go to the
                   configured full-sequence fallback (exact_scorer.py) or are flagged.

probe() (LL2) raises RuntimeError on: empty logprobs, no label position, captured mass
below threshold, codes that do not come back as whole tokens, invalid schema output,
an unclosed <think> block. It never degrades silently.

Facts about each server's behaviour are recorded in research/ledger-LOC-local.md.
"""
from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass, field
from typing import Any, Sequence

import httpx

from .. import scoring
from ..prompts import build_messages, label_schema
from ..types import Item, Mode, Prediction, Task

SERVER_KINDS = ("ollama", "lmstudio", "llama-server", "mlx-lm", "generic")


def _field(v: str) -> str:
    """Provenance fields are ':'-separated; Ollama tags (model:tag) would break parsing."""
    return str(v).replace(":", "@").replace(" ", "")


def make_lab_provenance(backend: str, model: str, quant: str, hardware: str) -> str:
    return f"LAB:{_field(backend)}:{_field(model)}:{_field(quant)}:{_field(hardware)}"


def normalise_quant(q: str) -> str:
    """llama.cpp ftype names ('Q4_K - Medium') -> conventional short names ('Q4_K_M')."""
    q = str(q).strip()
    for long, short in ((" - Medium", "_M"), (" - Small", "_S"), (" - Large", "_L")):
        q = q.replace(long, short)
    return q.replace(" ", "")


@dataclass
class Capabilities:
    supports_json_schema: bool = True
    supports_logprobs: bool = True
    max_top_logprobs: int = 20
    logprob_mode: str = "pre_constraint"  # pre_constraint | post_constraint | unknown
    label_scoring: str = "top_logprobs"  # top_logprobs | full_sequence | none
    logprobs_endpoint: str = "chat_completions"  # chat_completions | ollama_native | lmstudio_responses

    @classmethod
    def from_dict(cls, d: dict | None) -> "Capabilities":
        d = dict(d or {})
        unknown = set(d) - set(cls.__dataclass_fields__)
        if unknown:
            raise ValueError(f"unknown capability flags: {sorted(unknown)}")
        c = cls(**d)
        if c.label_scoring not in ("top_logprobs", "full_sequence", "none"):
            raise ValueError(f"label_scoring must be top_logprobs|full_sequence|none, got {c.label_scoring}")
        if c.logprobs_endpoint not in ("chat_completions", "ollama_native", "lmstudio_responses"):
            raise ValueError(f"bad logprobs_endpoint {c.logprobs_endpoint}")
        return c


@dataclass
class ChatResult:
    content: str
    logprobs: list[dict]
    input_tokens: int | None
    output_tokens: int | None
    latency_s: float
    raw_usage: dict = field(default_factory=dict)


class OpenAICompatBackend:
    """DecisionBackend over an OpenAI-compatible local server."""

    def __init__(
        self,
        name: str,
        mode: Mode,
        base_url: str,
        model: str,
        server: str = "generic",
        capabilities: dict | Capabilities | None = None,
        quant: str = "auto",
        hardware: str = "unknown-hw",
        backend_version: str | None = None,
        tokenizer: dict | None = None,
        captured_mass_threshold: float = scoring.CAPTURED_MASS_THRESHOLD,
        max_tokens: dict | None = None,
        timeout_s: float = 120.0,
        extra_body: dict | None = None,
        disable_thinking: bool = True,
        thinking_params: dict | None = None,
        json_logprobs: bool = True,
        provenance_prefix: str = "LAB",
        force_cold_start: bool = False,
        fallback: Any = None,
        probe_items: int = 3,
        api_key: str | None = None,
        client: httpx.Client | None = None,
    ):
        if server not in SERVER_KINDS:
            raise ValueError(f"server must be one of {SERVER_KINDS}")
        if mode not in ("json_schema", "logprob_scoring"):
            raise ValueError(f"OpenAICompatBackend supports json_schema|logprob_scoring, not {mode}")
        self.name = name
        self.mode: Mode = mode
        self.server = server
        self.base_url = base_url.rstrip("/")
        self.root_url = self.base_url.removesuffix("/v1")
        self.model = model
        self.caps = capabilities if isinstance(capabilities, Capabilities) else Capabilities.from_dict(capabilities)
        self.quant = quant
        self.hardware = hardware
        self.backend_version = backend_version
        self.tokenizer_spec = tokenizer or {}
        self.threshold = float(captured_mass_threshold)
        self.max_tokens = {"logprob_scoring": 4, "json_schema": 32, **(max_tokens or {})}
        self.extra_body = dict(extra_body or {})
        self.disable_thinking = disable_thinking
        self.thinking_params = thinking_params
        self.json_logprobs = json_logprobs and self.caps.supports_logprobs
        self.provenance_prefix = provenance_prefix
        self.force_cold_start = force_cold_start
        self.fallback = fallback  # object with score_full_sequence(task, item, labels_order) -> (probs, info)
        self.probe_items = probe_items
        headers = {"Authorization": f"Bearer {api_key or 'local'}"}
        self.client = client or httpx.Client(timeout=timeout_s, headers=headers)
        self._tokenizer = None
        self.probe_info: dict = {}

    # ------------------------------------------------------------------ utils
    @property
    def provenance(self) -> str:
        if self.provenance_prefix == "MOCK":
            return f"MOCK:{self.name}"
        return make_lab_provenance(self.name, self.model, self.quant, self.hardware)

    def _thinking_body(self) -> dict:
        if not self.disable_thinking:
            return {}
        if self.thinking_params is not None:
            return dict(self.thinking_params)
        if self.caps.logprobs_endpoint == "ollama_native":
            return {"think": False}
        # Accepted (ignored when irrelevant) by llama-server and Ollama, verified here.
        return {"reasoning_effort": "none", "chat_template_kwargs": {"enable_thinking": False}}

    def _get_tokenizer(self):
        if self._tokenizer is not None:
            return self._tokenizer
        spec = self.tokenizer_spec
        if spec.get("gguf"):
            self._tokenizer = scoring.GGUFTokenizer(spec["gguf"])
        elif spec.get("hf_tokenizer_json"):
            self._tokenizer = scoring.HFTokenizerJSON(spec["hf_tokenizer_json"])
        elif spec.get("server_tokenize"):
            self._tokenizer = scoring.ServerTokenizer(self.base_url, self.client)
        return self._tokenizer

    # ------------------------------------------------------------- transport
    def _chat(self, messages: list[dict], max_tokens: int, want_logprobs: bool, top_k: int, schema: dict | None) -> ChatResult:
        ep = self.caps.logprobs_endpoint
        t0 = time.perf_counter()
        if ep == "ollama_native":
            body: dict = {
                "model": self.model,
                "messages": messages,
                "stream": False,
                "options": {"temperature": 0, "num_predict": max_tokens},
            }
            if want_logprobs:
                body.update(logprobs=True, top_logprobs=top_k)
            if schema is not None:
                body["format"] = schema
            body.update(self._thinking_body())
            body.update(self.extra_body)
            r = self.client.post(f"{self.root_url}/api/chat", json=body)
            lat = time.perf_counter() - t0
            r.raise_for_status()
            d = r.json()
            return ChatResult(
                content=(d.get("message") or {}).get("content") or "",
                logprobs=scoring.normalise_logprob_content(d.get("logprobs")),
                input_tokens=d.get("prompt_eval_count"),
                output_tokens=d.get("eval_count"),
                latency_s=lat,
                raw_usage={k: d.get(k) for k in ("total_duration", "load_duration", "prompt_eval_duration", "eval_duration", "prompt_eval_cached_count")},
            )
        if ep == "lmstudio_responses":
            # UNTESTED on macOS here. Shape per LM Studio / OpenAI Responses API docs (ledger LOC rows).
            body = {"model": self.model, "input": messages, "max_output_tokens": max_tokens, "temperature": 0}
            if want_logprobs:
                body.update(top_logprobs=top_k, include=["message.output_text.logprobs"])
            if schema is not None:
                body["text"] = {"format": {"type": "json_schema", "name": "choice", "schema": schema, "strict": True}}
            body.update(self.extra_body)
            r = self.client.post(f"{self.base_url}/responses", json=body)
            lat = time.perf_counter() - t0
            r.raise_for_status()
            d = r.json()
            text, lps = "", []
            for out in d.get("output") or []:
                for part in out.get("content") or []:
                    if part.get("type") == "output_text":
                        text += part.get("text", "")
                        lps += scoring.normalise_logprob_content(part.get("logprobs"))
            u = d.get("usage") or {}
            return ChatResult(text, lps, u.get("input_tokens"), u.get("output_tokens"), lat, u)
        body = {"model": self.model, "messages": messages, "max_tokens": max_tokens, "temperature": 0, "seed": 0}
        if want_logprobs:
            body.update(logprobs=True, top_logprobs=top_k)
        if schema is not None:
            body["response_format"] = {"type": "json_schema", "json_schema": {"name": "choice", "strict": True, "schema": schema}}
        body.update(self._thinking_body())
        body.update(self.extra_body)
        r = self.client.post(f"{self.base_url}/chat/completions", json=body)
        lat = time.perf_counter() - t0
        if r.status_code >= 400:
            raise RuntimeError(f"{self.name}: HTTP {r.status_code} from chat/completions: {r.text[:300]}")
        d = r.json()
        ch = (d.get("choices") or [{}])[0]
        u = d.get("usage") or {}
        return ChatResult(
            content=(ch.get("message") or {}).get("content") or "",
            logprobs=scoring.normalise_logprob_content(ch.get("logprobs")),
            input_tokens=u.get("prompt_tokens"),
            output_tokens=u.get("completion_tokens"),
            latency_s=lat,
            raw_usage=u,
        )

    # --------------------------------------------------------------- version
    def detect_version_and_quant(self) -> tuple[str, str]:
        version, quant = self.backend_version or "unknown", self.quant
        try:
            if self.server == "llama-server":
                d = self.client.get(f"{self.root_url}/props").json()
                version = f"llama-server {d.get('build_info', 'unknown')}"
                if quant in ("auto", None):
                    quant = normalise_quant(d.get("model_ftype", "unknown"))
            elif self.server == "ollama":
                version = f"ollama {self.client.get(f'{self.root_url}/api/version').json().get('version', 'unknown')}"
                if quant in ("auto", None):
                    s = self.client.post(f"{self.root_url}/api/show", json={"model": self.model}).json()
                    quant = (s.get("details") or {}).get("quantization_level", "unknown")
            elif self.server == "lmstudio" and quant in ("auto", None):
                d = self.client.get(f"{self.root_url}/api/v0/models/{self.model}").json()
                quant = d.get("quantization", "unknown")
        except Exception as e:  # version detection must not hide in silence either
            version = f"{version} (detect failed: {type(e).__name__})"
        self.backend_version, self.quant = version, quant or "unknown"
        return self.backend_version, self.quant

    def unload_for_cold_start(self) -> None:
        if self.server == "ollama":
            self.client.post(f"{self.root_url}/api/generate", json={"model": self.model, "keep_alive": 0})
            time.sleep(1.0)

    # ----------------------------------------------------------------- core
    def _codes(self, labels_order: Sequence[str]) -> scoring.CodeMap:
        cm = scoring.assign_codes(labels_order, self._get_tokenizer())
        return cm

    def _decide(self, task: Task, item_text: str, labels_order: Sequence[str], codes: scoring.CodeMap | None) -> tuple[ChatResult, dict]:
        if self.mode == "logprob_scoring":
            msgs = build_messages(task, item_text, labels_order, "codes", codes.codes)
            k = min(20, self.caps.max_top_logprobs)
            res = self._chat(msgs, self.max_tokens["logprob_scoring"], True, k, None)
            sr = scoring.score_from_logprobs(res.logprobs, codes.codes, list(labels_order), self.threshold)
            info = {
                "content": res.content,
                "position": sr.position,
                "how": sr.how,
                "topk_mass": sr.topk_mass,
                "captured_mass": sr.captured_mass,
                "fallback_needed": sr.fallback_needed,
                "fallback_reason": sr.fallback_reason,
                "probs": sr.probs,
                "label": sr.label,
                "method": "top_logprobs",
            }
            return res, info
        schema = label_schema(labels_order) if self.caps.supports_json_schema else None
        msgs = build_messages(task, item_text, labels_order, "json")
        res = self._chat(msgs, self.max_tokens["json_schema"], self.json_logprobs, 1, schema)
        label, err = None, None
        try:
            obj = json.loads(scoring.strip_think(res.content).strip().strip("`").removeprefix("json").strip())
            cand = obj.get("label") if isinstance(obj, dict) else None
            if cand in labels_order:
                label = cand
            else:
                err = f"label {cand!r} not in enum"
        except Exception as e:
            err = f"invalid JSON: {type(e).__name__}"
        conf, n_tok = None, 0
        if label is not None and res.logprobs:
            lp, n_tok = scoring.value_span_logprob(res.logprobs, label)
            if lp is not None:
                import math

                conf = math.exp(lp)
        probs = scoring.top1_distribution(label, conf, list(labels_order)) if (label is not None and conf is not None) else None
        info = {"content": res.content, "label": label, "error": err, "label_seq_prob": conf, "label_tokens": n_tok, "probs": probs, "method": "json_schema"}
        return res, info

    # ---------------------------------------------------------------- probe
    def probe(self, task: Task) -> dict:
        """LL2 capability probe. Raises RuntimeError rather than degrading silently."""
        version, quant = self.detect_version_and_quant()
        if self.force_cold_start:
            self.unload_for_cold_start()
        info: dict = {"backend": self.name, "server": self.server, "mode": self.mode, "model": self.model, "backend_version": version, "quant": quant, "capabilities": asdict(self.caps), "provenance": self.provenance}
        if self.mode == "logprob_scoring":
            if not self.caps.supports_logprobs or self.caps.label_scoring == "none":
                raise RuntimeError(f"{self.name}: logprob_scoring requested but config says logprobs unsupported (label_scoring={self.caps.label_scoring})")
            if self.caps.label_scoring == "full_sequence" and self.fallback is None:
                raise RuntimeError(f"{self.name}: label_scoring=full_sequence needs a fallback exact scorer")
        if self.mode == "json_schema" and not self.caps.supports_json_schema:
            raise RuntimeError(f"{self.name}: json_schema mode requested but supports_json_schema=false")

        labels = list(task.labels)
        codes = self._codes(labels) if self.mode == "logprob_scoring" else None
        if codes is not None:
            info["codes"] = codes.codes
            info["codes_verified_with_tokenizer"] = codes.verified
            info["tokenizer"] = codes.tokenizer
            if not codes.usable:
                if self.fallback is None:
                    raise RuntimeError(f"{self.name}: option codes unusable ({codes.problems}) and no full-sequence fallback configured")
                info["codes_problems"] = codes.problems
        # one probe item per distinct label, from the calibration split (never test)
        seen, probe_items = set(), []
        for it in task.split("calibration"):
            if it.label not in seen:
                seen.add(it.label)
                probe_items.append(it)
            if len(probe_items) >= self.probe_items:
                break
        if not probe_items:
            raise RuntimeError("probe needs calibration items")
        lat, masses, tops = [], [], []
        for it in probe_items:
            res, d = self._decide(task, it.text, labels, codes)
            lat.append(res.latency_s)
            if self.mode == "logprob_scoring" and self.caps.label_scoring == "top_logprobs":
                if not res.logprobs:
                    raise RuntimeError(f"{self.name}: server returned EMPTY logprobs (silent-failure case); content={res.content!r}")
                if not any(e.get("top_logprobs") for e in res.logprobs):
                    raise RuntimeError(f"{self.name}: logprobs present but top_logprobs empty; cannot score options")
                if d["position"] is None:
                    raise RuntimeError(f"{self.name}: no label position in output {res.content!r} ({d['how']}); disable thinking or raise max_tokens")
                masses.append(d["captured_mass"])
                pos = d["position"]
                top_tok = res.logprobs[pos]["top_logprobs"][0]["token"] if res.logprobs[pos]["top_logprobs"] else ""
                tops.append(top_tok)
            if self.mode == "json_schema":
                if d["label"] is None:
                    raise RuntimeError(f"{self.name}: invalid schema output on probe: {res.content!r} ({d['error']})")
                if self.json_logprobs and not res.logprobs:
                    raise RuntimeError(f"{self.name}: json_logprobs requested but server returned empty logprobs")
        info["cold_latency_s"] = lat[0]
        info["probe_latencies_s"] = lat
        if masses:
            mean_mass = sum(masses) / len(masses)
            info["probe_captured_mass"] = masses
            if mean_mass < self.threshold:
                raise RuntimeError(f"{self.name}: captured mass at label position {mean_mass:.3f} < {self.threshold} on probe items {masses}")
            code_norms = {scoring.normalize_token(c) for c in codes.codes.values()}
            if not all(scoring.normalize_token(t) in code_norms for t in tops):
                raise RuntimeError(f"{self.name}: top token at label position is not an option code: {tops}")
            info["probe_top_tokens"] = tops
        self.probe_info = info
        return info

    # -------------------------------------------------------------- predict
    def predict(self, task: Task, items: Sequence[Item], labels_order: Sequence[str] | None = None) -> list[Prediction]:
        labels_order = list(labels_order or task.labels)
        codes = self._codes(labels_order) if self.mode == "logprob_scoring" else None
        preds: list[Prediction] = []
        for it in items:
            if self.mode == "logprob_scoring" and self.caps.label_scoring == "full_sequence":
                t0 = time.perf_counter()
                probs, finfo = self.fallback.score_full_sequence(task, it, labels_order)
                lat = time.perf_counter() - t0
                label = max(labels_order, key=lambda l: probs[l])
                preds.append(Prediction(it.id, label, {l: probs[l] for l in task.labels}, lat, finfo.get("input_tokens"), 0, self.provenance, False, None, {"method": "full_sequence(exact)", **finfo}))
                continue
            res, d = self._decide(task, it.text, labels_order, codes)
            lat = res.latency_s
            probs, label, captured = d.get("probs"), d.get("label"), d.get("captured_mass")
            raw = {k: v for k, v in d.items() if k not in ("probs",)}
            if self.mode == "logprob_scoring" and d.get("fallback_needed"):
                if self.fallback is not None:
                    t0 = time.perf_counter()
                    fprobs, finfo = self.fallback.score_full_sequence(task, it, labels_order)
                    lat += time.perf_counter() - t0
                    probs = fprobs
                    label = max(labels_order, key=lambda l: probs[l])
                    raw.update(method="full_sequence(exact) fallback", fallback_info=finfo)
                else:
                    raw["method"] = "top_logprobs (FLAGGED: below threshold, no fallback configured)"
            if probs is not None:
                probs = {l: float(probs[l]) for l in task.labels}
            preds.append(
                Prediction(
                    item_id=it.id,
                    label=label,
                    probs=probs,
                    latency_s=lat,
                    input_tokens=res.input_tokens,
                    output_tokens=res.output_tokens,
                    provenance=self.provenance,
                    cold=False,
                    captured_mass=captured,
                    raw=raw,
                )
            )
        return preds


def from_config(cfg: dict, mode: str, hardware: str, fallback: Any = None) -> OpenAICompatBackend:
    keys = {
        "base_url", "model", "server", "capabilities", "quant", "backend_version", "tokenizer",
        "captured_mass_threshold", "max_tokens", "timeout_s", "extra_body", "disable_thinking",
        "thinking_params", "json_logprobs", "provenance_prefix", "force_cold_start", "probe_items", "api_key",
    }
    kwargs = {k: v for k, v in cfg.items() if k in keys}
    return OpenAICompatBackend(name=cfg["name"], mode=mode, hardware=cfg.get("hardware", hardware), fallback=fallback, **kwargs)
