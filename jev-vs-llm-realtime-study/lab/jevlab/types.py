"""Shared contract for the Local Lab.

Every backend, metric and the runner speak in these types, so lab agents can
build modules in parallel. Change this file only through the lead.

Provenance rule (PLAN §6, LL5): every Prediction carries a provenance string.
  - "LAB:<backend>:<model>:<quant>:<hardware>"  real run on local/self-hosted model
  - "MOCK:<backend>"                            stub server / fake payloads
  - "LIVE:<backend>:<model>"                    real vendor API (Jev, Claude)
Nothing tagged LAB or MOCK may appear in STUDY.md headline tables.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal, Protocol, Sequence

Split = Literal["train", "calibration", "test"]
Mode = Literal["json_schema", "logprob_scoring", "exact_scoring", "vendor", "classifier"]


@dataclass(frozen=True)
class Item:
    """One labelled utterance."""

    id: str
    text: str
    label: str  # one of Task.labels (incl. the out-of-scope label if present)
    split: Split


@dataclass(frozen=True)
class Task:
    """A closed-set decision: pick one label for each item (a 'Choice' question)."""

    name: str  # e.g. "banking77-subset15+oos"
    instructions: str  # the question, as it would be sent to Jev or an LLM
    labels: tuple[str, ...]  # option ids, stable order (permutation tests reorder copies)
    label_descriptions: dict[str, str]  # option id -> short rubric text (Jev 'criteria')
    items: tuple[Item, ...]
    source: str  # dataset name + licence + revision/URL
    seed: int

    def split(self, which: Split) -> list[Item]:
        return [it for it in self.items if it.split == which]


@dataclass
class Prediction:
    item_id: str
    label: str | None  # predicted option id; None = invalid/refused/no answer
    probs: dict[str, float] | None  # full distribution over Task.labels if the backend has one
    latency_s: float  # wall-clock for this item's decision call (amortised if batched)
    input_tokens: int | None
    output_tokens: int | None
    provenance: str  # see module docstring
    cold: bool = False  # first call after model load / connection open
    captured_mass: float | None = None  # prob mass covered by returned top-k logprobs
    raw: dict = field(default_factory=dict)  # backend-specific debug info (not for tables)


class DecisionBackend(Protocol):
    """A backend answers Choice questions over a Task's labels."""

    name: str
    mode: Mode

    def probe(self, task: Task) -> dict:
        """Capability probe (LL2). Must raise RuntimeError loudly if the backend cannot
        deliver what its config claims (e.g. empty logprobs, invalid schema output)."""
        ...

    def predict(self, task: Task, items: Sequence[Item], labels_order: Sequence[str] | None = None) -> list[Prediction]:
        """Predict a label for each item. labels_order permutes option presentation
        (used for the option-order permutation test); default = task.labels."""
        ...


@dataclass
class RunResult:
    """One row of results/*.csv (one backend x mode x calibration state)."""

    run_id: str
    task: str
    backend: str
    mode: Mode
    model: str
    quant: str
    hardware: str
    backend_version: str
    provenance: str
    n_test: int
    accuracy: float
    accuracy_ci95: tuple[float, float]
    macro_f1: float
    ece: float | None
    ece_bins: int | None
    ece_binning: str | None  # "equal-mass"
    brier: float | None
    calibrated: bool  # after temperature scaling?
    temperature: float | None
    p50_latency_s: float
    p95_latency_s: float
    cold_latency_s: float | None
    mean_input_tokens: float | None
    mean_output_tokens: float | None
    usd_per_1k_decisions: float | None  # with formula + [Guessing] params documented in the run log
    mean_captured_mass: float | None
    permutation_flip_rate: float | None
    invalid_rate: float  # label None / schema-invalid / refused
