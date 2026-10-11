# Plan — JEPA vs LLM for Real-Time AI Experiences (Architecture Interview Study)

Status: v1 DRAFT — pending plan-critic validation

## 0. Interpretation & framing (read first)

| Item | Decision | Confidence |
|---|---|---|
| "Jev" | Interpreted as **JEPA** (Joint Embedding Predictive Architecture: I-JEPA, V-JEPA, V-JEPA 2/2.1, VL-JEPA, LLM-JEPA). VL-JEPA explicitly targets real-time streaming with *selective decoding*, matching "realtime experience" + "token benefits". | [Likely] — no repo context; if wrong, the study must be redone |
| Audience | Architecture/system-design interview (Staff/Principal/AI-Lead level) | [Certain] per request |
| Depth | Detailed but simple to explain (user chose "detailed study, simple explainable") | [Certain] |

**Uncomfortable truth to carry through the whole study:** JEPA is *not* a drop-in LLM replacement. It predicts *meaning (embeddings)*, not *words (tokens)*. Anything that must output open-ended language, reasoning chains, code, or tool calls still needs a decoder/LLM. JEPA's value is in perception, streaming understanding, retrieval/classification, and world-model planning — and in *deciding when an expensive decoder is actually needed*.

## 1. The problem we design for (shared requirements for both designs)

**Primary scenario — "Live Video Copilot"**: an always-on assistant over a live camera + mic stream (e.g., smart glasses, factory-floor/retail ops monitoring, live sports/event narration). It must:
1. Continuously understand what is happening (event/activity detection, live captions of *changes*).
2. Answer user questions on demand ("what did I just pick up?", "when did the forklift enter zone B?").
3. Hit real-time NFRs: event-to-insight latency p95 < 1 s for alerts; spoken-answer time-to-first-audio < 800 ms; 24/7 streams.
4. Scale: 1 stream → 10,000 concurrent streams; cost reported per stream-hour and per month.

**Contrast scenario — "Real-time text/voice chat assistant"** (LLM's home turf) — used to show where JEPA does *not* help.

**Brief mention — "Robot/agent control loop"** (V-JEPA 2-AC style world-model planning) — where JEPA's world-model property shines.

## 2. Architectures to compare (fairness rule: no strawmen)

| ID | Name | Description |
|---|---|---|
| L1 | LLM-way, API | Frontier real-time multimodal API (e.g., Gemini Live / OpenAI Realtime) streaming frames+audio; per-token billing |
| L2 | LLM-way, self-hosted | Small open VLM (e.g., Qwen-VL class) with **uniform** periodic decoding on own GPUs |
| L2+ | LLM-way, optimized | L2 + cheap change detector (CLIP/SigLIP embedding delta) gating calls — the *fair* LLM baseline, since selective triggering is not exclusive to JEPA |
| J1 | JEPA-way | VL-JEPA-style: V-JEPA encoder → predictor emits semantic embeddings continuously → **selective decoding** to text only on semantic change; retrieval/classification done in embedding space with zero decoding |
| H1 | Hybrid (expected recommendation) | JEPA always-on perception + embedding memory; LLM invoked on demand for reasoning, dialogue, tool use |

## 3. Phases, owners (agents), outputs, and validation gates

Every phase ends with a **Critic agent gate**: verdict `PASS` / `PASS-WITH-FIXES` / `FAIL`, written to `reviews/phase-N-critic.md`. Fixes are applied before the next phase starts. A FAIL repeats the phase.

### Phase 0 — Plan & plan validation
- Owner: lead (me). Critic: plan-critic agent.
- Output: this file (v2 after fixes), `reviews/phase-0-plan-critic.md`.
- Gate: plan covers fairness, evidence standards, measurable outputs, interview usefulness.

### Phase 1 — Evidence gathering (3 research agents in parallel)
- R1 **JEPA evidence**: I-JEPA, V-JEPA, V-JEPA 2 (+AC), V-JEPA 2.1, VL-JEPA, LLM-JEPA; param counts, benchmarks, selective-decoding numbers (decoding ops reduction, Hz, quality retained), latency/planning-time claims, code/weights availability & licenses, 2026 updates (AMI Labs etc.).
- R2 **LLM real-time evidence**: real-time multimodal APIs (latency: TTFT, time-to-first-audio, tokens/s), streaming video LLMs (e.g., VideoLLM-online and successors), vision-token cost per frame/second (e.g., Gemini video tokens/s), context/session limits for long streams.
- R3 **Economics evidence**: current (Oct 2026) per-token pricing for real-time/multimodal APIs (input/output/audio/cached), GPU on-demand $/hr (L4, A10G, L40S, H100), self-hosted VLM throughput figures.
- Output: `research/evidence-ledger.md` — every number has: claim ID, value, unit, source URL, source type (paper/official doc/benchmark/blog), date, confidence tag [Certain]/[Likely]/[Guessing].
- Gate (Critic-1, fact-checker): independently re-verifies ≥10 highest-impact claims against primary sources; flags secondary-only claims; checks for cherry-picking and missing counter-evidence (e.g., JEPA limitations, benchmarks where LLMs win).

### Phase 2 — Architecture designs (2 design agents in parallel)
- `design/requirements.md` (lead): shared FRs/NFRs, latency budget, scale targets.
- A1 **LLM-way** (`design/llm-architecture.md`): L1, L2, L2+; component diagram (mermaid), data flow, latency budget breakdown, scaling, failure modes, state/memory for long streams.
- A2 **JEPA-way + Hybrid** (`design/jepa-architecture.md`): J1 and H1; same sections; explicit "what JEPA cannot do" boundary.
- Gate (Critic-2, principal-architect persona): fairness (no strawman L-designs), feasibility (can it actually be built today with released weights?), consistency with ledger, missing NFRs (privacy, observability, eval, cold start, multi-tenancy).

### Phase 3 — Quantitative model (1 modeling agent)
- `model/cost_model.py`: parameterized from the ledger; computes per stream-hour and per-month cost + decoding-ops + tokens for L1/L2/L2+/J1/H1; sensitivity analysis (scene-change rate, question rate, GPU price, utilization).
- `model/selective_decoding_sim.py`: synthetic stream with scripted events; implements uniform vs change-gated decoding; reports decode calls, event recall, detection latency. **Labelled as a mechanism demo, not an accuracy benchmark.**
- `model/test_cost_model.py`: unit tests for the arithmetic (pytest).
- Charts → `model/outputs/*.png`, tables → `model/outputs/*.csv`.
- Gate (Critic-3, quant reviewer): re-runs code, checks units, hand-verifies ≥3 numbers, checks every parameter traces to a ledger ID or is tagged [Guessing] with a sensitivity range.

### Phase 4 — Interview-ready study write-up (writer agent)
- `STUDY.md`: 1-page executive summary → concepts in plain English (LLM vs JEPA mental model) → LLM-way design → JEPA-way design → side-by-side numbers (tokens, $, latency, ops) → where each wins (decision matrix) → hybrid recommendation → risks & what would change the recommendation → 45-min interview script (how to whiteboard it) → likely interviewer follow-ups with strong answers → glossary → sources.
- Gate (Critic-4, interview panel: hiring manager + principal architect + skeptic): clarity, accuracy vs ledger, overclaims, can it be explained in 2 minutes, what a top candidate would add.

### Phase 5 — Final integration & validation
- Final consistency critic: every number in STUDY.md matches ledger/model outputs; links resolve; tests pass; no unsupported claims.
- `README.md` index; commit and push to `ccr-b41820fd-rls3og`.
- Publish an HTML view (charts + tables) as a private Artifact for easy reading on phone.

## 4. Evidence standards
- Source hierarchy: peer-reviewed / arXiv primary papers & official docs > official pricing pages > benchmarks > reputable press > blogs/community.
- Any number from secondary sources only → max [Likely]; derived/assumed numbers → [Guessing] + sensitivity range.
- Counter-evidence required: for each major claim ("JEPA is cheaper", "LLM is faster"), the ledger records evidence against it too.

## 5. Risks to the study itself
| Risk | Mitigation |
|---|---|
| "Jev" ≠ JEPA | Stated up front; user can redirect after the plan |
| No public JEPA serving API → cost comparison is API-$ vs GPU-$ (apples/oranges) | Normalize everything to $/stream-hour; include self-hosted LLM (L2/L2+) so like-for-like exists |
| Paper numbers (e.g., VL-JEPA decoding reduction) measured on one dataset | Present as "reported on X", sensitivity analysis on gating ratio |
| Pricing changes fast; my knowledge cutoff precedes today (2026-10-11) | R3 fetches live pricing pages; dates recorded |
| Can't run real JEPA/VLM (no GPU here) | Simulation demonstrates mechanism only; clearly labelled |
