# Plan — Jev (TypeSafe AI "System One") vs LLMs for Real-Time Experiences

Status: v1 DRAFT (Jev edition), pending plan-critic validation
Supersedes: v0, which wrongly read "Jev" as JEPA. The user corrected this: Jev = TypeSafe AI's System One model.

## 0. Framing (read first)

**What Jev is** [Certain — vendor docs, docs.typesafe.ai, read 2026-10-11]
- TypeSafe AI's first "System One model" (`jev-1.13.0`), announced **2026-10-11**, early access.
- **Input:** text only (string / JSON / array).
- **Output:** typed decisions with probabilities, through three primitives: **Choice** (one of ≤255 options), **Score** (rubric levels), and **Noul** (probability of yes). No text generation, no code, no tool calls.
- **Price:** $0.042 per million input tokens. Output is free.
- **Context:** 64k tokens per request (32k for state plus the longest question).
- **Rate limits:** 100K tokens/s and 80 requests/s, adjusted dynamically.
- **Training:** RLCD (RL for Calibrated Decisions). No customer fine-tuning.

**Uncomfortable truths to carry through the whole study**
1. **Evidence is almost entirely vendor self-reported and launched today.** Examples: "193.6× faster, 444.6× cheaper", "70–500 ms", "zero hallucinations". No independent benchmark exists yet. Every Jev performance claim is capped at [Likely], or at [Guessing] where it is marketing.
2. **Jev is not an LLM replacement.** It cannot write replies, explain, plan multi-step, call tools, or take images or audio. The vendor's own docs say so. The real question is *which parts of a real-time system are System-1-shaped (fast, bounded decisions) versus System-2-shaped (generation, reasoning)*.
3. **"Type-safe / can't hallucinate" is weaker than it sounds.** LLM structured outputs (constrained decoding) also guarantee schema validity. Jev can still pick the *wrong* valid option; calibration helps only in aggregate (the vendor admits this). Its real differentiators to test are **latency, price, and calibrated confidence**.
4. **The incumbent for System-1 tasks is not only an LLM.** A fine-tuned small classifier (encoder model, or embeddings + logistic regression) is often faster and cheaper still, but needs labelled data and retraining. A fair study must include it.
5. **Jevons paradox (the name's origin):** if decisions get cheaper, teams make many more of them (speculative fan-out), so total spend and risk can rise. This is a second-order effect to analyse.

## 1. The problem we design for

**Primary scenario: "Real-time AI customer-support assistant" (chat + voice)** for a large consumer company.
- Every inbound message passes through **decision points**:
  1. Input guardrail (abuse, prompt injection, PII present).
  2. Intent routing (about 20 intents).
  3. Urgency / frustration score.
  4. "Needs human?" check.
  5. Policy-eligibility checks.
  6. Next-best-action choice.
  7. Output guardrail on the generated reply.
- Then **generation**: a natural-language reply (System 2).
- Real-time NFRs (requirements to be finalised in Phase 2):
  - Decision path p95 ≤ 300 ms.
  - Chat time-to-first-token ≤ 1 s.
  - Voice time-to-first-audio ≤ 800 ms.
- Scale: 50M messages/day, peak 2,000 msg/s (to be validated as plausible).
- Why this scenario: it contains *both* System-1 and System-2 work. It is a classic system-design interview prompt, and the vendor's own intent-routing pattern targets it, so the comparison is fair to both sides.

**Secondary scenarios** (short, to sharpen "where each wins"):
- **S2: High-volume real-time moderation / guardrails** (pure System-1, large token volume). This is where price per token dominates, and where a fine-tuned classifier is the strongest rival.
- **S3: Numeric / temporal decisions** (fraud thresholds, date windows, counting). Jev's documented weakness, so the work stays in code or an LLM.
- **S4: Real-time game / agent action selection** (vendor's Doom demo, 10 queries/s). Shows the per-decision latency budget.

## 2. Architectures compared (fairness rule: no strawmen)

| ID | Name | Decisions handled by | Generation handled by |
|---|---|---|---|
| **L1** | LLM-way, naive | Frontier LLM, one call per decision, JSON structured output | Frontier LLM |
| **L2** | LLM-way, optimised (the *fair* LLM baseline) | Small fast LLM, all decisions batched into one structured-output call, prompt caching, no reasoning tokens, logprobs for confidence | Mid-tier LLM, streaming |
| **C1** | Classic-ML baseline | Fine-tuned small encoder classifiers (self-hosted) | Mid-tier LLM |
| **J1** | Jev-way | Jev, all decisions as one fan-out request over shared state | Mid-tier LLM (Jev cannot generate) |
| **J2** | Jev-way with confidence-gated cascade (expected recommendation, to be proven) | Jev first; low-confidence decisions escalate to an LLM (System 2) or a human; numeric/date logic stays in code | Mid-tier LLM |

## 3. Metrics (what "detailed study" means)
- **Latency:** per-decision p50/p95, end-to-end decision path, chat TTFT, voice time-to-first-audio; network RTT and region effects (Jev is US West Coast only today).
- **Tokens:** input tokens per message, output tokens (LLM JSON plus any reasoning tokens; Jev output is free), cached vs uncached, and how fan-out changes token counts.
- **Charges:** $ per decision, per 1M messages, per month at scale. Show the split between decisions and generation (the punchline is likely that generation dominates the cost, which bounds Jev's total-bill savings).
- **Quality:** accuracy, calibration (ECE), consistency, schema-validity rate, known failure modes (literal reading, math, dates, indirection, context rot, prompt injection, option-order bias).
- **Operations and risk:** rate limits vs peak load, SLA, vendor maturity, lock-in, data residency/ZDR, version pinning and threshold drift, observability, eval strategy, rollout.
- **Second-order effects:** Jevons-paradox spend, automation rate vs human-review load, team skills.

## 4. Phases, agents, outputs, gates

Every phase ends with a **critic agent gate** that writes `reviews/phase-N-*.md` with verdict `PASS` / `PASS-WITH-FIXES` / `FAIL` and checkable findings. Fixes are applied before the next phase. A FAIL repeats the phase.

### Phase 0: Plan and plan validation
- **Owner:** lead. **Critic:** plan critic.
- **Output:** this file at v2, plus `reviews/phase-0-plan-critic.md`.

### Phase 1: Evidence (3 research agents in parallel)
- **R1, Jev evidence:** the vendor blog, homepage, all relevant docs (models, API, confidence, patterns, jaggedness, parallel-questions cookbook, SDK), and the "Lies, Damned Lies, and Benchmarks" post. Also any independent coverage, reviews, Hacker News/X discussion, or third-party tests (expect very little on launch day), plus company facts (founder, funding).
- **R2, LLM real-time evidence:** current (Oct 2026) model latency (TTFT, output tokens/s) from independent benchmarks such as Artificial Analysis; real-time voice APIs; structured-output guarantees (constrained decoding); logprob availability; LLM calibration literature (RLHF overconfidence).
- **R3, Economics evidence:**
  - Current LLM prices: input, output, and cached tokens, for frontier, mid, and small tiers across Anthropic, OpenAI, and Google.
  - Classifier self-hosting costs: GPU $/hr and encoder throughput.
  - Typical token sizes for support messages and system prompts.
- **Output:** `research/evidence-ledger.md`. Each claim gets an ID, value, unit, source URL, source type, date, a vendor-claim flag, and a confidence tag.
- **Gate (Critic-1, fact-checker):** independently re-verify the 10+ highest-impact claims. Flag vendor-only claims. Require counter-evidence for each headline claim.

### Phase 2: Architecture (2 design agents in parallel)
- **Lead first writes `design/requirements.md`:** FRs, NFRs, latency budget, capacity estimate (back-of-envelope).
- **A1, LLM-way (`design/llm-architecture.md`):** L1 and L2.
- **A2, Jev-way (`design/jev-architecture.md`):** J1 and J2, plus C1 as the baseline.
- **Each design includes:** a mermaid diagram, data flow, per-hop latency budget, token flow, scaling against rate limits, failure modes and fallbacks, observability, eval and rollout plan, security (prompt injection).
- **Gate (Critic-2, principal-architect persona):** fairness, feasibility today, consistency with the ledger, missing NFRs.

### Phase 3: Quantitative model and "do it both ways" code (2 agents in parallel)
- **M1:** `model/cost_model.py` (tokens and $ per scenario × architecture, plus sensitivity analysis), `model/latency_model.py` (Monte Carlo latency budget from ledger distributions), `model/cascade_sim.py` (synthetic calibrated-confidence cascade showing the trade-off between threshold, automation rate, accuracy, and cost), pytest tests, and charts/CSVs in `model/outputs/`.
- **M2:** `harness/`, the same decision task implemented *the LLM way* (Anthropic structured outputs) and *the Jev way* (TypeSafe SDK). It shares a small labelled dataset and an evaluator (accuracy, ECE, latency, tokens, $). It has a **mock mode tested here**; live mode needs the user's API keys. No keys exist in this environment, so the live path is *untested* and labelled as such.
- **Gate (Critic-3, quant reviewer):** re-run everything, hand-verify at least 3 numbers, check that every parameter traces to a ledger ID or is tagged [Guessing] with a range, and confirm the harness API calls match the docs.

### Phase 4: Interview-ready study (writer agent)
- **`STUDY.md` sections:**
  - A 2-minute answer.
  - Concepts in plain English (System 1 vs System 2).
  - The LLM way, then the Jev way.
  - Side-by-side numbers (tokens, $, latency).
  - Where each wins (a decision matrix).
  - Hybrid recommendation.
  - Risks, and what would change the recommendation.
  - A whiteboard script for a 45-minute interview.
  - Likely follow-ups with strong answers.
  - Glossary and sources.
- **Gate (Critic-4, interview panel):** a hiring manager, a principal architect, and a skeptic check clarity, accuracy against the ledger and model, overclaims, and what a top candidate would add.

### Phase 5: Final integration
- **Final consistency critic:** every number in STUDY.md matches the ledger or model outputs; tests pass; links valid.
- Write `README.md`, then commit and push to `ccr-b41820fd-rls3og`.
- Publish a private HTML view of the study with charts.

## 5. Evidence standards
- **Source hierarchy:** official docs and pricing pages, then independent benchmarks (e.g., Artificial Analysis), then peer-reviewed papers, then reputable press, then vendor marketing and blogs, then community posts.
- **Vendor self-reported performance claims** (Jev or LLM vendors) are tagged `VENDOR` and capped at [Likely].
- **Derived or assumed numbers** are tagged [Guessing] and carry a sensitivity range.
- **Each headline claim records counter-evidence too.**

## 6. Risks to the study
| Risk | Mitigation |
|---|---|
| No API keys, so nothing can be benchmarked live | Published data plus a parametric model; a harness with mock mode the user can run with their own keys |
| Jev launched today; claims unverified; limits change | Vendor flags; date-stamp everything; sensitivity analysis |
| The scenario choice biases the result | Three secondary scenarios, including ones where Jev loses |
| LLM pricing and models move fast (knowledge cutoff before today) | R3 pulls live pricing pages, with dates |
