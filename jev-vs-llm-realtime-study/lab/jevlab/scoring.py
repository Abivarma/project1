"""Tokenizer-aware option scoring (LL3). Owner: LAB-A.

The "Jev-style decision primitive (emulation)" turns an LLM's next-token distribution
into a probability distribution over a closed set of options. Doing that naively is
wrong in several ways (critic review, "Tokenization pitfalls"); this module handles them:

1. Shared first tokens. Option *names* such as bill_balance / bill_due share a first
   token, so we never read option names off one position. Each option gets a
   single-token CODE ("A", "B", ...). Codes are verified against the loaded model's
   tokenizer at run start (`assign_codes`). If verification is impossible or fails,
   or there are more options than single-token codes, scoring falls back to
   full-sequence scoring (exact_scorer.py).
2. Leading-space / case variants. "A", " A", "a", "\\nA", "A)" are different tokens. We
   sum probability mass over every variant whose *normalised* text equals the code
   (`normalize_token`).
3. Label position. The label is often not the first generated token (whitespace, a
   JSON prefix like {"label": ", "Answer:", a quote). `find_label_position` locates
   the token that covers the first character of the answer value using character
   offsets over the generated tokens.
4. Thinking. A `<think>...</think>` block is skipped. An unclosed think block means
   no label was produced: the caller must disable thinking (probe raises).
5. Top-k truncation. Servers return at most ~20 top logprobs. We report
   `captured_mass` = probability mass on option codes visible at the label position.
   Below the threshold (default 0.9) the result is flagged `fallback_needed` and the
   caller routes the item to full-sequence scoring, or records the flag. Never silent.

Pure python + numpy; no network. Tokenizer adapters are optional imports.
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from typing import Any, Mapping, Protocol, Sequence

import numpy as np

DEFAULT_CODE_CANDIDATES: tuple[str, ...] = tuple("ABCDEFGHIJKLMNOPQRSTUVWXYZ")
CAPTURED_MASS_THRESHOLD = 0.9
JSON_KEYS = ("label", "answer", "choice", "option", "intent", "code")

_STRIP_CHARS = "()[]{}.:,;\"'*`<>"


# ---------------------------------------------------------------------------
# Tokenizers
# ---------------------------------------------------------------------------
class Tokenizer(Protocol):
    name: str

    def encode(self, text: str) -> list[int]: ...


class HFTokenizerJSON:
    """tokenizer.json via the `tokenizers` library (no remote code)."""

    def __init__(self, path: str):
        from tokenizers import Tokenizer as _T

        self._tok = _T.from_file(path)
        self.name = f"hf-tokenizers:{path}"

    def encode(self, text: str) -> list[int]:
        return self._tok.encode(text, add_special_tokens=False).ids


class GGUFTokenizer:
    """The GGUF's own tokenizer via llama-cpp-python (vocab_only: weights not loaded)."""

    def __init__(self, gguf_path: str):
        from llama_cpp import Llama

        self._llm = Llama(model_path=gguf_path, vocab_only=True, verbose=False)
        self.name = f"gguf:{gguf_path}"

    def encode(self, text: str) -> list[int]:
        return self._llm.tokenize(text.encode("utf-8"), add_bos=False, special=False)


class GGUFTokenizerFromLlama:
    """Wrap an already-loaded llama_cpp.Llama (used by the exact scorer)."""

    def __init__(self, llm: Any):
        self._llm = llm
        self.name = f"gguf:{getattr(llm, 'model_path', 'loaded')}"

    def encode(self, text: str) -> list[int]:
        return self._llm.tokenize(text.encode("utf-8"), add_bos=False, special=False)


class ServerTokenizer:
    """llama-server POST /tokenize (Ollama has no tokenize endpoint as of 0.40.x)."""

    def __init__(self, base_url: str, client: Any = None):
        import httpx

        self._url = base_url.rstrip("/").removesuffix("/v1") + "/tokenize"
        self._client = client or httpx.Client(timeout=30)
        self.name = f"server-tokenize:{self._url}"

    def encode(self, text: str) -> list[int]:
        r = self._client.post(self._url, json={"content": text, "add_special": False})
        r.raise_for_status()
        toks = r.json()["tokens"]
        return [t["id"] if isinstance(t, dict) else int(t) for t in toks]


class DictTokenizer:
    """Test helper: whitespace-preserving toy tokenizer backed by a fixed vocabulary."""

    def __init__(self, vocab: Sequence[str]):
        self.vocab = sorted(set(vocab), key=len, reverse=True)
        self.ids = {t: i for i, t in enumerate(sorted(set(vocab)))}
        self.name = "dict-tokenizer"

    def encode(self, text: str) -> list[int]:
        out, i = [], 0
        while i < len(text):
            for t in self.vocab:
                if text.startswith(t, i):
                    out.append(self.ids[t])
                    i += len(t)
                    break
            else:  # unknown char -> its own pseudo token
                out.append(-ord(text[i]))
                i += 1
        return out


# ---------------------------------------------------------------------------
# Codes
# ---------------------------------------------------------------------------
def normalize_token(tok: str) -> str:
    """Merge leading-space, newline, case and wrapping-punctuation variants of a code."""
    return bpe_to_text(tok).strip().strip(_STRIP_CHARS).strip().upper()


@dataclass
class CodeMap:
    codes: dict[str, str]  # label -> code
    verified: bool  # True when checked against the model's tokenizer
    tokenizer: str | None
    problems: list[str] = field(default_factory=list)

    @property
    def code_to_label(self) -> dict[str, str]:
        return {c: l for l, c in self.codes.items()}

    @property
    def usable(self) -> bool:
        return not self.problems


def assign_codes(
    labels: Sequence[str],
    tokenizer: Tokenizer | None = None,
    candidates: Sequence[str] = DEFAULT_CODE_CANDIDATES,
) -> CodeMap:
    """Assign one single-token code per option, in presentation order.

    With a tokenizer, a candidate is accepted only if both "X" and " X" encode to exactly
    one token, and no two accepted codes collide after normalisation (case variants
    merge, so "A" and "a" can never both be codes). Without a tokenizer the map is
    returned with verified=False; the server probe then checks empirically that the
    codes appear as whole tokens at the label position.
    """
    problems: list[str] = []
    chosen: list[str] = []
    seen_norm: set[str] = set()
    for c in candidates:
        if len(chosen) == len(labels):
            break
        n = normalize_token(c)
        if not n or n in seen_norm:
            continue
        if tokenizer is not None:
            if len(tokenizer.encode(c)) != 1 or len(tokenizer.encode(" " + c)) != 1:
                continue
        seen_norm.add(n)
        chosen.append(c)
    if len(chosen) < len(labels):
        problems.append(
            f"only {len(chosen)} single-token codes available for {len(labels)} options; use full-sequence scoring"
        )
    # shared-prefix check (relevant if a caller passes multi-character codes)
    for a in chosen:
        for b in chosen:
            if a != b and normalize_token(b).startswith(normalize_token(a)):
                problems.append(f"code {a!r} is a prefix of {b!r}")
    codes = {lab: chosen[i] for i, lab in enumerate(labels) if i < len(chosen)}
    return CodeMap(codes=codes, verified=tokenizer is not None, tokenizer=getattr(tokenizer, "name", None), problems=problems)


# ---------------------------------------------------------------------------
# Label position
# ---------------------------------------------------------------------------
_THINK_OPEN = re.compile(r"<think>|<\|channel\|>analysis|<reasoning>", re.I)
_THINK_CLOSE = re.compile(r"</think>|<\|end\|>|</reasoning>", re.I)
_JSON_VALUE = re.compile(r'"(?:' + "|".join(JSON_KEYS) + r')"\s*:\s*"?', re.I)
_PLAIN_PREFIX = re.compile(r"\s*(?:(?:the\s+)?(?:answer|option|choice|label)\s*(?:is)?\s*[:\-]?\s*)?[\s\*\(\[\"'`]*", re.I)


def token_offsets(tokens: Sequence[str]) -> list[tuple[int, int]]:
    out, pos = [], 0
    for t in tokens:
        out.append((pos, pos + len(t)))
        pos += len(t)
    return out


def answer_start(text: str) -> tuple[int | None, str]:
    """Character index where the answer value starts in generated text, and why.

    Returns (None, reason) if no answer can be located (e.g. unclosed think block).
    """
    start = 0
    m_open = _THINK_OPEN.search(text)
    if m_open:
        m_close = _THINK_CLOSE.search(text, m_open.end())
        if not m_close:
            return None, "unclosed_think_block"
        start = m_close.end()
    rest = text[start:]
    stripped = rest.lstrip()
    if stripped.startswith("{") or stripped.startswith("```"):
        m = _JSON_VALUE.search(rest)
        if not m:
            return None, "json_without_label_key"
        return start + m.end(), "json"
    m = _PLAIN_PREFIX.match(rest)
    idx = start + (m.end() if m else 0)
    if idx >= len(text):
        return None, "no_answer_text"
    return idx, "plain" if not m_open else "after_think"


def find_label_position(tokens: Sequence[str]) -> tuple[int | None, str]:
    """Index of the generated token that covers the first character of the answer."""
    text = "".join(tokens)
    ch, how = answer_start(text)
    if ch is None:
        return None, how
    for i, (a, b) in enumerate(token_offsets(tokens)):
        if a <= ch < b:
            return i, how
    return None, "answer_beyond_generated_tokens"


# ---------------------------------------------------------------------------
# Score a top-logprob list
# ---------------------------------------------------------------------------
@dataclass
class ScoreResult:
    label: str | None
    probs: dict[str, float] | None
    captured_mass: float  # mass on option codes at the label position (0..1)
    topk_mass: float  # total mass of the returned top-k list at that position
    position: int | None
    how: str  # json | plain | after_think | <failure reason>
    method: str = "top_logprobs"
    fallback_needed: bool = False
    fallback_reason: str | None = None


def _logprob_entries(entry: Mapping[str, Any]) -> list[tuple[str, float]]:
    tops = entry.get("top_logprobs") or []
    out = [(t.get("token", ""), float(t["logprob"])) for t in tops if t.get("logprob") is not None]
    if not out and "token" in entry and entry.get("logprob") is not None:
        out = [(entry["token"], float(entry["logprob"]))]
    return out


def code_probs_from_top(
    top: Sequence[tuple[str, float]], codes: Mapping[str, str], labels: Sequence[str]
) -> tuple[dict[str, float] | None, float, float]:
    """Merge variants and turn a top-k list into a distribution over labels.

    Labels whose code is absent from the top-k get a floor of
    min(smallest top-k prob, residual mass / n_missing), then everything is renormalised.
    Returns (probs or None, captured_mass, topk_mass).
    """
    code_to_label = {normalize_token(c): l for l, c in codes.items()}
    mass: dict[str, float] = {}
    topk_mass = 0.0
    min_p = 1.0
    for tok, lp in top:
        p = math.exp(lp)
        topk_mass += p
        min_p = min(min_p, p)
        lab = code_to_label.get(normalize_token(tok))
        if lab is not None:
            mass[lab] = mass.get(lab, 0.0) + p
    captured = float(sum(mass.values()))
    if captured <= 0:
        return None, 0.0, float(topk_mass)
    missing = [l for l in labels if l not in mass]
    if missing:
        residual = max(0.0, 1.0 - topk_mass)
        floor = min(min_p, residual / len(missing)) if top else 0.0
        floor = max(floor, 1e-12)
        for l in missing:
            mass[l] = floor
    z = sum(mass[l] for l in labels)
    return {l: mass[l] / z for l in labels}, captured, float(topk_mass)


def score_from_logprobs(
    content: Sequence[Mapping[str, Any]],
    codes: Mapping[str, str],
    labels: Sequence[str],
    threshold: float = CAPTURED_MASS_THRESHOLD,
    label_position: str = "search",
) -> ScoreResult:
    """Score an OpenAI-style `choices[0].logprobs.content` list (normalised entries).

    Each entry: {"token": str, "logprob": float, "top_logprobs": [{"token", "logprob"}]}.
    label_position="search" locates the answer token from the generated text;
    "first" reads position 0 (for servers whose per-position "token" field is not the
    sampled token, e.g. mlx-lm; use with max_tokens=1 and a prompt that answers at once).
    """
    if not content:
        return ScoreResult(None, None, 0.0, 0.0, None, "empty_logprobs", fallback_needed=True, fallback_reason="empty_logprobs")
    tokens = [e.get("token", "") for e in content]
    pos, how = (0, "first") if label_position == "first" else find_label_position(tokens)
    if pos is None:
        return ScoreResult(None, None, 0.0, 0.0, None, how, fallback_needed=True, fallback_reason=how)
    top = _logprob_entries(content[pos])
    probs, captured, topk_mass = code_probs_from_top(top, codes, labels)
    if probs is None:
        return ScoreResult(None, None, 0.0, topk_mass, pos, how, fallback_needed=True, fallback_reason="no_code_in_topk")
    label = max(labels, key=lambda l: probs[l])
    low = captured < threshold
    return ScoreResult(
        label=label,
        probs=probs,
        captured_mass=captured,
        topk_mass=topk_mass,
        position=pos,
        how=how,
        fallback_needed=low,
        fallback_reason=f"captured_mass {captured:.3f} < {threshold}" if low else None,
    )


# ---------------------------------------------------------------------------
# Sequence-level helpers (JSON mode confidence, full-sequence scoring)
# ---------------------------------------------------------------------------
def strip_think(text: str) -> str:
    m_open = _THINK_OPEN.search(text)
    if not m_open:
        return text
    m_close = _THINK_CLOSE.search(text, m_open.end())
    return text[m_close.end():] if m_close else ""


def value_span_logprob(content: Sequence[Mapping[str, Any]], value: str) -> tuple[float | None, int]:
    """Sum of logprobs of the generated tokens overlapping the JSON value `value`.

    Used for JSON-mode confidence: P(label tokens | prefix) under the logprobs the server
    reports (pre- or post-constraint, see Capabilities.logprob_mode).
    Returns (sum_logprob or None, n_tokens).
    """
    tokens = [e.get("token", "") for e in content]
    text = "".join(tokens)
    ch, _ = answer_start(text)
    if ch is None:
        return None, 0
    k = text.find(value, ch)
    if k < 0:
        return None, 0
    a, b = k, k + len(value)
    total, n = 0.0, 0
    for (s, e), ent in zip(token_offsets(tokens), content):
        if e > a and s < b and ent.get("logprob") is not None:
            total += float(ent["logprob"])
            n += 1
    return (total, n) if n else (None, 0)


def top1_distribution(pred: str, conf: float, labels: Sequence[str]) -> dict[str, float]:
    """Distribution with `conf` on `pred` and the rest spread uniformly (JSON mode)."""
    k = len(labels)
    conf = float(min(max(conf, 1e-9), 1 - 1e-9)) if k > 1 else 1.0
    rest = (1.0 - conf) / (k - 1) if k > 1 else 0.0
    return {l: (conf if l == pred else rest) for l in labels}


def full_sequence_probs(seq_logprobs: Mapping[str, float], n_tokens: Mapping[str, int] | None = None, length_norm: bool = False) -> dict[str, float]:
    """Softmax over per-option sequence log-probabilities (sum, or mean if length_norm)."""
    labs = list(seq_logprobs)
    s = np.array([seq_logprobs[l] / (max(1, n_tokens[l]) if (length_norm and n_tokens) else 1) for l in labs], dtype=float)
    s = s - s.max()
    p = np.exp(s)
    p = p / p.sum()
    return {l: float(v) for l, v in zip(labs, p)}


def bpe_to_text(tok: str) -> str:
    """Raw byte-level-BPE / SentencePiece pieces ('ĠA', '▁A', 'Ċ') -> text (' A', ' A', newline)."""
    return tok.replace("\u0120", " ").replace("\u2581", " ").replace("\u010a", "\n")


def normalise_logprob_content(raw: Any, token_format: str = "text") -> list[dict]:
    """Normalise server-specific logprob payloads to OpenAI chat-completions entries.

    Accepts: OpenAI {"content": [...]}, a bare list (Ollama native /api/chat
    "logprobs"), LM Studio /v1/responses output_text "logprobs" lists, and mlx-lm
    (token_format="bpe_raw": pieces come from convert_ids_to_tokens). Each position's
    top list is sorted by logprob (mlx-lm returns an unsorted argpartition).
    """
    if raw is None:
        return []
    if isinstance(raw, Mapping):
        raw = raw.get("content") or []
    conv = bpe_to_text if token_format == "bpe_raw" else (lambda t: t)
    out = []
    for e in raw:
        if not isinstance(e, Mapping):
            continue
        tops = [t for t in (e.get("top_logprobs") or []) if isinstance(t, Mapping) and t.get("logprob") is not None]
        tops = sorted(tops, key=lambda t: -float(t["logprob"]))
        out.append(
            {
                "token": conv(e.get("token", "") or ""),
                "logprob": e.get("logprob"),
                "top_logprobs": [{"token": conv(t.get("token", "") or ""), "logprob": t.get("logprob")} for t in tops],
            }
        )
    return out
