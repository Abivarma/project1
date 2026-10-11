"""Prompt construction shared by the server adapter and the in-process exact scorer.

Both modes see the same instructions, the same option descriptions and the same option
order; only the answer format differs:
  - codes (logprob scoring): options are listed as "A) label: description" and the model
    answers with the letter. The letter's next-token distribution is the option
    distribution ("Jev-style decision primitive (emulation)").
  - json (the LLM way): options are listed as "- label: description" and the model
    returns {"label": "<label>"} under a JSON schema whose enum is the label set.
The options sit in the system message and the customer text comes last, so servers
with prefix caching (llama-server cache_prompt, Ollama, LM Studio, mlx-lm) only have to
process the short per-item suffix.
"""
from __future__ import annotations

from typing import Mapping, Sequence

from .types import Task

JSON_PREFILL = '{"label": "'


def option_block(task: Task, labels_order: Sequence[str], codes: Mapping[str, str] | None) -> str:
    lines = []
    for lab in labels_order:
        desc = task.label_descriptions.get(lab, "")
        if codes is not None:
            lines.append(f"{codes[lab]}) {lab}: {desc}")
        else:
            lines.append(f"- {lab}: {desc}")
    return "\n".join(lines)


def build_messages(
    task: Task,
    text: str,
    labels_order: Sequence[str],
    style: str,
    codes: Mapping[str, str] | None = None,
    system_suffix: str = "",
) -> list[dict]:
    if style == "codes":
        if codes is None:
            raise ValueError("codes style needs a code map")
        tail = "Reply with the letter of the best option only."
        sys_text = f"{task.instructions}\n\nOptions:\n{option_block(task, labels_order, codes)}\n\n{tail}"
    elif style == "json":
        tail = 'Reply with JSON only, in the form {"label": "<option>"}.'
        sys_text = f"{task.instructions}\n\nOptions:\n{option_block(task, labels_order, None)}\n\n{tail}"
    else:
        raise ValueError(f"unknown prompt style {style!r}")
    if system_suffix:
        sys_text = f"{sys_text}\n{system_suffix}"
    return [
        {"role": "system", "content": sys_text},
        {"role": "user", "content": f"Customer message: {text}"},
    ]


def label_schema(labels: Sequence[str]) -> dict:
    return {
        "type": "object",
        "properties": {"label": {"type": "string", "enum": list(labels)}},
        "required": ["label"],
        "additionalProperties": False,
    }
