"""In-process exact option scoring with llama-cpp-python on the SAME GGUF (LL1/LL3).

Owner: LAB-A. This is the agreement reference for the server top-logprob path.

Two scorings (mode "exact_scoring"; the variant is in the backend name):
  codes          Same prompt as the server's logprob_scoring mode. One forward pass; the
                 FULL next-token distribution (no top-k cap) is read at the label
                 position and every vocabulary token whose normalised text equals a code is
                 summed into that option (scoring.normalize_token). Captured mass is exact.
  full_sequence  The JSON-mode prompt, prefilled with '{"label": "', then each option's
                 full text plus the closing quote is teacher-forced and its log-probability
                 summed: log P(label + '"' | prompt). Shared prefixes (bill_balance /
                 bill_due) are handled because every token of every option is scored.
                 Optional length normalisation (mean per token) is reported as a variant.

Safety (LL6): GGUF only (checked by magic bytes), loaded by llama.cpp (no pickle, no
remote code). The chat template from GGUF metadata is rendered in jinja2's
ImmutableSandboxedEnvironment (llama-cpp-python's Jinja2ChatFormatter), because the
template is untrusted data from a downloaded file.
"""
from __future__ import annotations

import time
from pathlib import Path
from typing import Sequence

import numpy as np

from .. import scoring
from ..prompts import JSON_PREFILL, build_messages
from ..types import Item, Mode, Prediction, Task


def _check_gguf(path: str) -> None:
    p = Path(path)
    if p.suffix.lower() != ".gguf":
        raise ValueError(f"exact scorer loads GGUF files only, got {p.name}")
    with p.open("rb") as f:
        if f.read(4) != b"GGUF":
            raise ValueError(f"{p.name} does not start with the GGUF magic bytes")


def _log_softmax(x: np.ndarray) -> np.ndarray:
    x = x.astype(np.float64)
    m = x.max()
    return x - m - np.log(np.exp(x - m).sum())


class ExactScorer:
    def __init__(
        self,
        gguf: str,
        scoring_kind: str = "codes",
        name: str | None = None,
        model: str | None = None,
        quant: str | None = None,
        hardware: str = "unknown-hw",
        n_ctx: int = 2048,
        n_threads: int | None = None,
        n_gpu_layers: int = 0,
        length_norm: bool = False,
        provenance_prefix: str = "LAB",
    ):
        if scoring_kind not in ("codes", "full_sequence"):
            raise ValueError("scoring_kind must be codes|full_sequence")
        _check_gguf(gguf)
        self.gguf = gguf
        self.scoring_kind = scoring_kind
        self.name = name or f"llamacpp-inproc/{scoring_kind}"
        self.mode: Mode = "exact_scoring"
        self.model = model or Path(gguf).stem
        self.quant = quant or "auto"
        self.hardware = hardware
        self.n_ctx = n_ctx
        self.n_threads = n_threads
        self.n_gpu_layers = n_gpu_layers
        self.length_norm = length_norm
        self.provenance_prefix = provenance_prefix
        self.backend_version = "unloaded"
        self._llm = None
        self._fmt = None
        self._variant_ids: dict[str, list[int]] | None = None
        self._variant_codes: tuple[str, ...] | None = None
        self.probe_info: dict = {}

    @property
    def provenance(self) -> str:
        if self.provenance_prefix == "MOCK":
            return f"MOCK:{self.name}"
        from .openai_compat import make_lab_provenance

        return make_lab_provenance(self.name, self.model, self.quant, self.hardware)

    # ------------------------------------------------------------- loading
    def load(self) -> None:
        if self._llm is not None:
            return
        import llama_cpp
        from llama_cpp import Llama
        from llama_cpp.llama_chat_format import Jinja2ChatFormatter

        kw = dict(model_path=self.gguf, n_ctx=self.n_ctx, logits_all=True, verbose=False, n_gpu_layers=self.n_gpu_layers, seed=0)
        if self.n_threads:
            kw["n_threads"] = self.n_threads
        key = (str(Path(self.gguf).resolve()), self.n_ctx, self.n_threads, self.n_gpu_layers)
        if key not in _MODEL_CACHE:  # codes and full_sequence scorers share one loaded model
            _MODEL_CACHE[key] = Llama(**kw)
        self._llm = _MODEL_CACHE[key]
        md = self._llm.metadata
        tmpl = md.get("tokenizer.chat_template")
        if not tmpl:
            raise RuntimeError("GGUF has no tokenizer.chat_template; cannot reproduce the server's chat prompt")
        vocab = self._llm
        bos = vocab.detokenize([vocab.token_bos()]).decode("utf-8", "ignore") if vocab.token_bos() >= 0 else ""
        eos = vocab.detokenize([vocab.token_eos()]).decode("utf-8", "ignore") if vocab.token_eos() >= 0 else ""
        self._fmt = Jinja2ChatFormatter(template=tmpl, eos_token=eos, bos_token=bos, add_generation_prompt=True)
        if self.quant in ("auto", None):
            ft = md.get("general.file_type")
            self.quant = _FTYPE.get(str(ft), f"ftype{ft}") if ft is not None else "unknown"
        self.backend_version = f"llama-cpp-python {llama_cpp.__version__}"

    def render(self, messages: list[dict], prefill: str = "") -> str:
        self.load()
        return self._fmt(messages=messages).prompt + prefill

    def tokenize(self, text: str) -> list[int]:
        self.load()
        return self._llm.tokenize(text.encode("utf-8"), add_bos=True, special=True)

    # ------------------------------------------------------------ forward
    def _eval_prompt(self, tokens: list[int]) -> None:
        """Evaluate with KV-prefix reuse (the system prompt is shared across items)."""
        llm = self._llm
        n_cached = llm.n_tokens
        L = 0
        cached = llm.input_ids[:n_cached]
        lim = min(n_cached, len(tokens))
        while L < lim and cached[L] == tokens[L]:
            L += 1
        if L >= len(tokens):
            L = len(tokens) - 1  # always recompute the last position's logits
        llm.n_tokens = L
        llm.eval(tokens[L:])

    def _next_logprobs(self, n_prompt: int) -> np.ndarray:
        return _log_softmax(np.asarray(self._llm.scores[n_prompt - 1]))

    def _code_variant_ids(self, codes: Sequence[str]) -> dict[str, list[int]]:
        """Scan the whole vocabulary once: token ids whose normalised text is each code."""
        key = tuple(scoring.normalize_token(c) for c in codes)
        if self._variant_ids is not None and self._variant_codes == key:
            return self._variant_ids
        want = set(key)
        out: dict[str, list[int]] = {k: [] for k in key}
        llm = self._llm
        for tid in range(llm.n_vocab()):
            piece = llm.detokenize([tid]).decode("utf-8", "ignore")
            n = scoring.normalize_token(piece)
            if n in want:
                out[n].append(tid)
        self._variant_ids, self._variant_codes = out, key
        return out

    # ------------------------------------------------------------ scoring
    def score_codes(self, task: Task, item: Item, labels_order: Sequence[str]) -> tuple[dict[str, float], dict]:
        self.load()
        cm = scoring.assign_codes(labels_order, scoring.GGUFTokenizerFromLlama(self._llm))
        if not cm.usable:
            raise RuntimeError(f"codes unusable for this tokenizer: {cm.problems}")
        prompt = self.render(build_messages(task, item.text, labels_order, "codes", cm.codes))
        toks = self.tokenize(prompt)
        self._eval_prompt(toks)
        lp = self._next_logprobs(len(toks))
        var = self._code_variant_ids(list(cm.codes.values()))
        p = np.exp(lp)
        mass = {lab: float(p[var[scoring.normalize_token(code)]].sum()) for lab, code in cm.codes.items()}
        captured = sum(mass.values())
        probs = {l: mass[l] / captured for l in labels_order}
        top_id = int(np.argmax(lp))
        return probs, {"captured_mass": captured, "input_tokens": len(toks), "top_token": self._llm.detokenize([top_id]).decode("utf-8", "ignore"), "codes": cm.codes}

    def score_full_sequence(self, task: Task, item: Item, labels_order: Sequence[str]) -> tuple[dict[str, float], dict]:
        self.load()
        prompt = self.render(build_messages(task, item.text, labels_order, "json"), prefill=JSON_PREFILL)
        ptoks = self.tokenize(prompt)
        self._eval_prompt(ptoks)
        n_p = len(ptoks)
        base = self._next_logprobs(n_p)
        seq_lp, n_tok, boundary_merges = {}, {}, 0
        for lab in labels_order:
            full = self.tokenize(prompt + lab + '"')
            if full[:n_p] == ptoks:
                cont = full[n_p:]
            else:  # tokenizer merged across the prompt/option boundary: score the option on its own
                boundary_merges += 1
                cont = self._llm.tokenize((lab + '"').encode("utf-8"), add_bos=False, special=False)
            total = float(base[cont[0]])
            if len(cont) > 1:
                self._llm.n_tokens = n_p
                self._llm.eval(cont[:-1])
                for j in range(1, len(cont)):
                    total += float(_log_softmax(np.asarray(self._llm.scores[n_p + j - 1]))[cont[j]])
            seq_lp[lab] = total
            n_tok[lab] = len(cont)
        self._llm.n_tokens = n_p  # leave the cache at the shared prompt
        probs = scoring.full_sequence_probs(seq_lp, n_tok, length_norm=self.length_norm)
        return probs, {"input_tokens": n_p, "seq_logprob": seq_lp, "n_tokens": n_tok, "boundary_merges": boundary_merges, "length_norm": self.length_norm}

    # ------------------------------------------------------- DecisionBackend
    def probe(self, task: Task) -> dict:
        t0 = time.perf_counter()
        self.load()
        load_s = time.perf_counter() - t0
        cal = task.split("calibration")
        if not cal:
            raise RuntimeError("probe needs calibration items")
        t1 = time.perf_counter()
        if self.scoring_kind == "codes":
            probs, info = self.score_codes(task, cal[0], list(task.labels))
            if info["captured_mass"] < scoring.CAPTURED_MASS_THRESHOLD:
                raise RuntimeError(f"{self.name}: exact captured mass on codes {info['captured_mass']:.3f} < 0.9 (model is not answering with a code)")
        else:
            probs, info = self.score_full_sequence(task, cal[0], list(task.labels))
        first = time.perf_counter() - t1
        if not np.isclose(sum(probs.values()), 1.0):
            raise RuntimeError("exact scorer produced a non-normalised distribution")
        self.probe_info = {
            "backend": self.name, "mode": self.mode, "model": self.model, "quant": self.quant,
            "backend_version": self.backend_version, "load_s": load_s, "cold_latency_s": load_s + first,
            "provenance": self.provenance, **{k: v for k, v in info.items() if k in ("captured_mass", "top_token", "codes", "boundary_merges")},
        }
        return self.probe_info

    def predict(self, task: Task, items: Sequence[Item], labels_order: Sequence[str] | None = None) -> list[Prediction]:
        labels_order = list(labels_order or task.labels)
        out = []
        for it in items:
            t0 = time.perf_counter()
            if self.scoring_kind == "codes":
                probs, info = self.score_codes(task, it, labels_order)
                captured = info["captured_mass"]
            else:
                probs, info = self.score_full_sequence(task, it, labels_order)
                captured = None
            lat = time.perf_counter() - t0
            label = max(labels_order, key=lambda l: probs[l])
            raw = {k: v for k, v in info.items() if k != "codes"}
            out.append(Prediction(it.id, label, {l: float(probs[l]) for l in task.labels}, lat, info.get("input_tokens"), 0, self.provenance, False, captured, raw))
        return out


_MODEL_CACHE: dict = {}

# llama.cpp general.file_type enum (subset)
_FTYPE = {"0": "F32", "1": "F16", "2": "Q4_0", "3": "Q4_1", "7": "Q8_0", "8": "Q5_0", "9": "Q5_1", "10": "Q2_K", "11": "Q3_K_S", "12": "Q3_K_M", "13": "Q3_K_L", "14": "Q4_K_S", "15": "Q4_K_M", "16": "Q5_K_S", "17": "Q5_K_M", "18": "Q6_K", "32": "BF16"}


def from_config(cfg: dict, hardware: str) -> ExactScorer:
    keys = {"gguf", "model", "quant", "n_ctx", "n_threads", "n_gpu_layers", "length_norm", "provenance_prefix"}
    kw = {k: v for k, v in cfg.items() if k in keys}
    return ExactScorer(scoring_kind=cfg.get("scoring", "codes"), name=cfg.get("name"), hardware=cfg.get("hardware", hardware), **kw)
