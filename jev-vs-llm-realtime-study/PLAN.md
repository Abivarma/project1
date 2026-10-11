# Plan v2: Jev (TypeSafe AI "System One") vs LLMs for real-time experiences

Status: **v2.2**. v2.2 applies the Phase 1 fact-check corrections listed in §10. v2.1 applied the six v2 re-check edits. It applies the Phase 0 plan-critic review in `reviews/phase-0-plan-critic.md` (verdict PASS-WITH-FIXES). Each fix's disposition is in §9.

History:
- v0 wrongly read "Jev" as JEPA.
- v1 re-scoped the study to TypeSafe's Jev.
- v2 applies critic fixes 1–12 and LL1–LL8, and adds the user's Local Lab requirement.

## 0. Framing

### What Jev is
Source: vendor docs at docs.typesafe.ai, read 2026-10-11. Tags are verified in Phase 1.
- **Identity:** the first "System One model", `jev-1.13.0`. **Launched 2026-09-15** (early access). Also reachable without the waitlist through OpenRouter, Vercel and MotherDuck. TypeSafe raised $870M at a $7.5B valuation on 2026-10-09. On OpenRouter, Jev serves about 1.03B decision requests a week. Sources: JEV rows; dates corrected by Critic-1.
- **Input:** text only (string / JSON / array).
- **Output:** typed answers with probabilities and a confidence value:
  - **Choice:** up to 255 options; larger sets go through a vendor two-stage process with "occasional slowdown".
  - **Score:** 2–10 rubric levels.
  - **Noul:** the probability that the answer is yes.
- **Cannot:** generate text or code, call tools, or explain.
- **Price:** $0.042 per million input tokens. Question instructions and criteria count as input. Output is reported in `usage` but not billed.
- **Context:** 64k tokens per request; 32k for state plus the longest question.
- **Rate limits:** 100K tokens/s and 80 requests/s, dynamic; enterprise plans get more.
- **Customisation:** no customer fine-tuning.
- **Region:** service "currently based" on the US West Coast [Likely].

### Uncomfortable truths to carry through the study
1. **About four weeks of third-party evidence now exist, and they show quality and calibration depend on the task.** (Corrected after Phase 1; v2 said "vendor-only, launch day".)
   - Strong on bounded verification: ties frontier models on claim verification.
   - Weak elsewhere: last of 12 on LegalBench, last of 17 on a 77-case BANKING77 pilot.
   - Calibration varies by task: ECE about 0.01 to 0.11.
   - The vendor's headline numbers remain vendor-run.
   - "193.6× faster, 444.6× cheaper" is in the vendor's words "the higher end of real-world gains", with no named comparator.
   - "238×" is a list-price ratio ($10 Fable 5.1 ÷ $0.042).
   - The homepage example implies about 75× faster and 171× cheaper.
   - "0% hallucination" is true by construction (outputs are restricted to the defined options), not measured.
   - Vendor "accuracy" means agreement with GPT-6 Astra / Fable 5.1, not ground truth.
   - **"Decision model" is now a product category, not a moat.** Within four weeks of Jev's launch came:
     - OpenAI Decisions API (2026-10-06; gpt-6-luna; $0.10/MTok input only; images; US/EU residency)
     - Cloudflare Clef and Clef-flash (open weights; Clef-flash $0.038)
     - Microsoft-Decision-1 ($0.042)
     - Liquid d1 ($0.04)
2. **Jev is not an LLM replacement.** The real question is which parts of a real-time system are System-1-shaped (bounded decisions) and which are System-2-shaped (generation, reasoning, multimodal).
3. **The headline depends on the comparator** (critic Risk 1).
   - Against a cached small-tier LLM (Claude Haiku 5.5 or GPT-6 Luna, both $0.10/$0.50 with $0.01 cache reads), Jev's verified price per message is 0.92–3.45× lower. That is parity, and GPT-6 Luna cached is slightly cheaper than Jev (ECO rows).
   - Decisions are about 2% of the total bill once generation is included. Against cached Haiku, Jev saves about 0.2% of the bill (R3).
   - Price is therefore a differentiator only against mid and frontier tiers.
   - The candidate differentiators are critical-path latency, native calibrated distributions with no labels needed, API simplicity, and capacity/operational risk.
4. **Capacity may be the binding constraint** (critic Risk 2). At default limits Jev sustains roughly 50 messages/s (token-bound). The SDK defaults (10 s timeout, automatic retries) would break a real-time SLO unless they are overridden.
5. **Quality and calibration cannot be measured live here.** There are no API keys and Jev has a waitlist. The only first-party measured numbers in the study will come from the Local Lab and the C1 classifier, run on public data and labelled as such.
6. **Two loose phrases need correcting:**
   - "Type-safe" is not unique. LLM structured outputs also guarantee schema validity, with caveats: refusals, `max_tokens` truncation, unsupported schema features. The real risk on either side is a *wrong valid option*.
   - The name honours W. S. Jevons. The vendor's stated bet is that cheaper decisions bring a demand rebound, so total spend can rise.

## 1. Problem and requirements

### Assumed exemplar
The user's actual real-time workload is **unknown**. The primary scenario below is an assumed exemplar, and it is Jev's showcased home turf (the vendor's intent-routing doc uses customer-service routing). It is balanced by modelling Jev's losses inside it.

### Clarification questions
These go into the study's interview script and `requirements.md`:
- Modality: chat, voice, or agent?
- What is the latency SLO, and where does the clock start and stop?
- Which regions are the users in?
- What is the volume and the peak?
- Which languages?
- Are labels available?
- How often does the taxonomy (the set of intents) change?
- Compliance and data residency (EU, India DPDP)?
- Is the cost of errors asymmetric?
- What is the budget?

### Defaults when the answers are unknown
- **Volumes:** a sweep over 1M, 10M and 50M messages/day, where a message is one user turn. 50M/day is about 579 msg/s on average, and the assumed peak is 3.5× that, about 2,000 msg/s.
- **Regions:** US-West, US-East, EU and India. The user has been asked for their region.
  - From India, the datacenter-backbone round trip to US-West is 194–240 ms at P50; tail and last-mile latency are not captured. Jev processes data only in the US (us-west-2).
- **Parameter card:** a "bring your own workload" card in M1 lets the user plug in their own numbers.

### Primary scenario P: real-time customer-support assistant (chat and voice)
Decision points per message (3–15, default 7):
1. Input guardrail.
2. Intent routing (Banking77-like).
3. Urgency/frustration score.
4. Needs-human check.
5. Policy check, split so the model extracts fields and code does the comparison.
6. Next-best action.
7. Output guardrail, run per streamed sentence for voice.

Then the system generates a reply (System 2).

**In-scenario Jev losses to model:**
- Date and amount eligibility.
- Multi-hop reasoning.
- Account history longer than 32k tokens.
- Non-English or code-mixed text.
- Image attachments.
- Prompt injection aimed at the guardrail itself.

### Secondary scenarios
| ID | Scenario | Why included |
|---|---|---|
| S2 | High-volume moderation/guardrails | Pure System-1 work. C1 is the strongest rival. |
| S4′ | Tool/skill routing inside an LLM agent loop | Vendor cookbook: 182 skills. |
| S5 | Voice turn-taking / endpointing decision | Latency-critical. |
| S6 | Real-time speech-to-speech conversation, or multi-hop eligibility over long history | **The LLM wins** here. |
| Boundary | Numeric, date and counting tasks | A **"Jev boundary checklist"**, not a scenario. |
| Sanity | Doom demo | One-line check: about $7/h at 10 queries/s implies about 4.6K tokens/query. |

## 2. Architectures: the comparator ladder (no strawmen; every ratio names its rung)

| ID | Family | Decisions | Generation | Rung / note |
|---|---|---|---|---|
| L1 | LLM | Frontier model with reasoning, one call per decision | Frontier | **Vendor comparator / anti-pattern**. Used only to reconcile with the vendor's numbers; never a headline |
| L1b | LLM | Frontier model at its **lowest effort**, batched | Frontier | Rung b. "No reasoning" cannot be built: Opus 5.5, Fable 5.1, GPT-6 Astra and GPT-6.1 Sol reject disabling it (LLM-027) |
| L2d | Decision API | Hosted decision-model API: OpenAI Decisions (gpt-6-luna), Clef-flash, Microsoft-Decision-1, Liquid d1 | Mid | **New rung after Phase 1.** Jev's direct peers
| L2m | LLM | Mid-tier, batched structured output | Mid | Rung c |
| L2 | LLM | Small tier (Haiku 5.5 class and the cheapest OpenAI/Gemini tiers), batched, rubric cached, thinking off | Mid, streamed | Rung d: **the fair API-LLM baseline** |
| L2c | LLM | L2 with confidence escalation to frontier (confidence = logprobs where the provider has them, otherwise k-sample self-consistency at k× cost) | Mid | Cascade peer to J2 |
| L3 | Neutral | Self-hosted small open-weight LLM, option scoring in one forward pass, full distribution, in-region | Mid | Rung e: closest technical rival. **Production numbers come from the ledger; Local Lab results are illustrative only** |
| C1a | Neutral | TF-IDF/embeddings + logistic regression (few labels) | Mid | Rung f. **Measured here on CPU** |
| C1b | Neutral | Fine-tuned small encoder | Mid | Rung f. Estimated from the literature |
| J1 | Jev | Jev, one fan-out request | Mid | — |
| J2 | Jev | Jev with confidence-gated escalation to an LLM or a human; numbers and dates handled in code | Mid | Cascade |
| D1 | Neutral | Jev (or an LLM) labels data; a distilled classifier serves the high-volume intents; Jev keeps the long tail and cold start | Mid | The "teacher" pattern |
| V-S2S | LLM | Speech-to-speech real-time model | — | Voice, LLM way |
| V-casc | Jev | ASR → decisions (Jev/L2/C1) → LLM → TTS | — | Voice, forced for Jev because it is text-only |

**Design idea to evaluate:** a **Decision Service port**, i.e. a typed Choice/Score/Noul interface with swappable backends (Jev, L2, L3, C1). It is the build-vs-buy hedge for a four-week-old vendor in a category that is commoditising fast.

## 3. Pre-registered hypotheses
Each hypothesis has a falsification rule fixed before Phase 3. No recommendation is pre-committed.

| ID | Hypothesis | Falsified if |
|---|---|---|
| P1 | From US-West, Jev's decision-path p95 is ≤ 300 ms while the best API-LLM decision path (L2) is > 300 ms. **Modelled, not measured:** Jev publishes no p95, so the model reports the threshold at which the verdict flips | Modelled L2 p95 is ≤ 300 ms, or Jev p95 is > 300 ms, using ledger latency distributions |
| P1-IN | From India, neither Jev nor a US-hosted API LLM meets a 300 ms decision p95. Only an in-region option does: an India-region API LLM (Vertex asia-south1 gemini-3.5-flash / 2.5-flash; Azure South India gpt-4.1-mini / gpt-4o), a self-hosted open-weight decision model in Mumbai (Clef-flash, or the Qwen base of Microsoft-Decision-1), L3, or C1 | Jev p95 from India is ≤ 300 ms, or no in-region option meets it |
| P2 | Including generation, J1 cuts the total per-message bill by < 5% compared with L2 (cached small tier) | The modelled saving is ≥ 5% at default parameters |
| P3 | With N labelled examples per intent, C1a matches the best zero-shot decision model within 2 accuracy points at lower cost and latency. N is swept over {0, 10, 50, 200}. The zero-shot reference is the lab's zero-shot scorer, measured on the same split; vendor or literature Jev numbers are context only | C1a at N=50 is more than 2 points below the lab zero-shot scorer on the held-out test split (bootstrap 95% CI) |
| P4 | J1 cannot serve 2,000 msg/s peak at default rate limits | Headroom ratio is ≥ 1 |
| P5 | Jev's advantage is largest at zero labels with a churning taxonomy | In the M1 crossover model, Jev's cost per correct automated decision relative to C1a/D1 does **not** fall as labels increase (N = 0 to 200) and as taxonomy churn falls (monthly to never) |
| P6 | Jevons-style speculative fan-out raises decision spend k×, while the total bill stays dominated by generation | Decisions exceed 25% of the bill at k ≤ 5 |

## 4. Metrics
- **Latency:**
  - Every SLO states where the clock starts and stops. Voice starts at end-of-speech and includes endpointing.
  - Network round-trip time by region, TLS/connection reuse, and queueing.
  - p50/p95/p99, including 429/529 retries.
  - Hedged requests, and cold start for self-hosted models.
  - Latency vs state size.
  - Critical path vs off-path: run the guardrail in parallel with speculative generation.
- **Tokens and charges:**
  - State tokens and question tokens kept separate. A Jev request is modelled as fixed overhead (about 250–300 tokens) + state + per-question tokens. Per-question tokens are about 57 for short questions (GDPR cookbook) and about 75–95 net for support rubrics. A 77-option Choice is about 1,670 tokens. These are Critic-1 re-derivations.
  - LLM caching modelled; Jev gets no cache discount.
  - Thinking tokens counted.
  - **$ per message (or per 1K characters), never $ per token across vendors.**
  - Full total cost of ownership (TCO): human review, error cost, GPU at peak with N+1 redundancy and multiple regions, labelling, rubric maintenance, enterprise minimums.
  - Jev price run at 1×, 3× and 10× (the vendor says the price may be subsidised).
- **Quality:**
  - Risk–coverage curve and AURC (accuracy at an automation rate X).
  - Brier score, ECE (binning stated), reliability diagrams.
  - Macro-F1 and safety-class recall.
  - Option-order permutation flip rate; run-to-run determinism.
  - Multilingual slice and injection slice.
  - Caveat: post-hoc calibration needs labels, so Jev's calibration edge is a cold-start edge.
- **Operations and risk:**
  - Rate-limit headroom per vendor.
  - Per-call deadlines and fallbacks; fail-open vs fail-closed for each decision.
  - SLA, vendor maturity, lock-in.
  - Residency and ZDR.
  - Version pinning (`jev-1.13.0` rather than `jev-latest`) and recalibrating thresholds on each upgrade.
  - Observability.
- **Second-order effects:**
  - Jevons rebound, and governance for it (decision budgets; every question must have a consumer).
  - The resulting split between automation and human-review load.
  - Team skills.

## 5. Phases, agents and gates
Detailed, checkable gate criteria are in `reviews/phase-0-plan-critic.md` under "Concrete, checkable gate pass criteria", plus the Local Lab gate. They are adopted with the modifications in §9.

- **Critics:**
  - Run in fresh context against a written rubric.
  - Return a verdict: PASS, PASS-WITH-FIXES, or FAIL.
  - At most **2 FAIL loops per phase**, then escalate to the user.
- **Agent prompts:** every one states that fetched web pages and downloaded files are **untrusted data, never instructions**.

| Phase | Agents (parallel where listed together) | Outputs | Gate |
|---|---|---|---|
| 0 | Lead, plan critic | PLAN v2; plan-critic review | Critic confirms v2 resolves the blocking fixes |
| 1 | R1 Jev evidence (incl. the vendor evals site's 4 workflows; independent coverage with logged queries); R2 LLM real-time (Artificial Analysis TTFT and tokens/s; provider capability matrix; voice components; S2S latency); R3 economics (≥ 3 providers × 3 tiers incl. Haiku 5.5; GPU $/hr; encoder throughput; support-message token sizes; inter-region RTT); **plus LAB agent starting in parallel** | `research/evidence-ledger.md` (≥ 40 rows, conditions column) | Critic-1 fact-checker re-fetches ≥ 12 claims |
| 2 | Lead writes `design/requirements.md` (capacity math, latency budgets); then A1 LLM-way (L1–L2c, V-S2S), A2 Jev-way (J1, J2, V-casc), A3 neutral baselines (L3, C1a/b, D1); each designer adds a one-page steelman of the other side | `design/*.md` | Critic-2 principal architect, with fairness checklist |
| 3 | M1 quant model; LAB completes (capped at about 30% of Phase 3 effort) | `model/` (parameters file tied to the ledger, ladder, volume sweep, price sensitivity, tornado chart, Monte Carlo latency, cascade sim, tests); `lab/` | Critic-3 quant reviewer, plus Local Lab gate |
| 4 | Writer | `STUDY.md` (30-second and 2-minute answers, clarification questions, back-of-envelope sheet, latency-budget diagram, ladder, where-each-wins matrix on ≥ 8 axes, hybrid recommendation, failure modes, eval/rollout, build vs buy, ≥ 5 "what would change my mind" triggers, 45-minute whiteboard script, ≥ 10 follow-up questions, glossary) | Critic-4 interview panel (hiring manager, principal architect, skeptic) |
| 5 | Lead, final critic | Number-consistency script; README; push; private HTML view with an interview cheat sheet | Final consistency critic |

## 6. Local Lab (user requirement: "run local AI models on Mac, load any model and learn")
- **Location:** `lab/`, configured from YAML. Built from day 1 in parallel with Phase 1 (LL8).
- **Backends:**
  - **One OpenAI-compatible adapter** for Ollama, LM Studio, llama.cpp `llama-server` and `mlx-lm`, with capability flags: `supports_json_schema`, `supports_logprobs`, `max_top_logprobs`, `logprob_mode`, `label_scoring` (LL1).
  - An in-process **exact scorer** on CPU, used as a reference.
  - The **Jev SDK** and **Claude SDK** backends, tested against a local stub server that replays the documented responses.
- **Modes for the same task:**
  - (a) **LLM way:** JSON-schema generation.
  - (b) **"Jev-style decision primitive (emulation)":** option probabilities from logprobs, then temperature scaling. It is never called "local Jev".
  - (c) Real Jev, when the user has a key.
- **Engineering rules:**
  - A startup **capability probe** that fails loudly (LL2).
  - A tokenizer-aware scorer: single-token codes, variant merging, label-position search, thinking disabled, full-sequence fallback (LL3).
  - A train/calibration/test split with bootstrap confidence intervals (LL4).
  - `LAB:` and `MOCK` provenance tags, with a leakage test (LL5).
  - Model files: GGUF/safetensors only, no `trust_remote_code`, pinned revisions (LL6).
- **Data:** public **Banking77** (CC-BY-4.0) and **CLINC150** (out-of-scope class). Smoke runs use a 10–20-intent subset with a ≤ 1B model on Linux CPU, via Ollama or llama.cpp.
- **`LEARNING.md`:**
  - A table of Mac RAM tiers vs model size.
  - Install commands for each backend.
  - A **verified-on matrix**: Linux CPU paths that were executed here vs macOS paths that are **untested**.
  - At least 6 exercises.
  - Troubleshooting.
- **C1a** (TF-IDF/embeddings + logistic regression) is measured on the same split. Together with the lab runs, these are the **only first-party measured numbers** in the study.

## 7. Evidence standards
- **Source order:** official docs and pricing pages; then independent benchmarks such as Artificial Analysis, with date and probe location; then papers; then press; then vendor marketing; then community posts.
- **Ledger columns:** ID, claim, value, unit, **conditions**, URL, type, access date, VENDOR flag, confidence, counter-evidence.
- **Confidence caps:** VENDOR performance rows are at most [Likely]. Marketing rows are at most [Guessing].
- **URLs:** every URL must actually have been fetched. Failed fetches are logged.

## 8. Risks to the study
| Risk | Mitigation |
|---|---|
| No API keys; Jev waitlist | Published data plus the parametric model. The lab and C1 measure what can be measured. The live path is clearly marked *untested* |
| Comparator-driven misleading headline | Comparator ladder; overclaim grep in the Phase 4 gate |
| Scope creep (13 architectures plus the lab) | Group architectures by family in the design docs, with per-architecture delta tables; lab timeboxed |
| Lab numbers leaking into production claims | Provenance tags plus a leakage test |
| Pricing and models move fast | Live pricing pages, dated |

## 9. Disposition of the Phase 0 critic fixes
| Fix | Disposition |
|---|---|
| 1 Comparator ladder | **Accepted** (§2, §0.3) |
| 2 Capacity as a gating constraint | **Accepted** (§1 volume sweep, P4, Phase 2 requirements) |
| 3 Capability matrix; LLM confidence method | **Accepted.** L2c uses logprobs where available, else self-consistency at k× cost. The Local Lab gives a real logprob path |
| 4 Missing architectures | **Accepted.** Hypotheses are renamed P1–P6, and the critic's "H1 Jev-as-teacher" is renamed **D1** to avoid an ID clash. Voice is split into V-S2S and V-casc |
| 5 Pre-registered hypotheses | **Accepted** (§3) |
| 6 Unknown use case | **Accepted.** The user is asked once (non-blocking); defaults apply |
| 7 Rework secondary scenarios | **Accepted** |
| 8 Latency completeness | **Accepted.** India region added |
| 9 Token and charge model | **Accepted** |
| 10 Quality metrics | **Accepted** |
| 11 Harness de-risking | **Accepted**, merged into the Local Lab (§6) |
| 12 Process | **Accepted.** C1/L3/D1 move to a neutral A3; task list updated |
| Phase 2 gate "full diagram per architecture" | **Modified.** At least 4 family diagrams: LLM-text, Jev-text, neutral, and voice (V-S2S and V-casc together). Per-architecture delta tables still mark the critical path, per-hop latency, token flow, fallback and deadline. Reason: 13 diagrams would be scope creep with little interview value |
| C1b measured | **Modified.** C1b (fine-tuned encoder) is estimated from the literature, not trained here, tagged at most [Likely] with its conditions. P3 rests on the measured C1a. Reason: CPU time budget |
| LL1–LL8 | **Accepted** |
| v2 re-check R1–R6 | **Accepted** (P1 marked modelled with its flip threshold; India-region LLM added to P1-IN; P3/P5 given concrete rules; L3 lab results illustrative only; Jev token overhead modelled; user-location guess removed) |

## 10. Phase 1 findings that changed the plan (v2.2)
Source: `reviews/phase-1-factcheck-critic.md`, "Lead-level corrections" and "Top findings".

**Dates and evidence**
- Jev launched 2026-09-15, not 2026-10-11. The blog's date is a site-deploy stamp.
- The "launch-day, vendor-only" framing is replaced by "4 weeks of third-party evidence; task-dependent".

**Comparator ladder**
- New rung **L2d** for hosted decision-model APIs, Jev's direct peers.
- L1b renamed "frontier at lowest effort", because reasoning cannot be disabled on frontier models.

**Price, capacity and confidence**
- Small-tier LLMs are at price parity with Jev.
- Capacity binds on both sides: Jev's default limits, and Haiku 5.5's Scale tier at 10K RPM.
- Claude has no logprobs [Certain]. LLM confidence on Claude is verbalized or k-sampled.

**Residency**
- India in-region options are limited to Vertex asia-south1, Azure South India Standard, and self-hosted open-weight models.

**Robustness**
- JevOut: natural context additions flip 61–73% of correct decisions.
- Cisco: a fine-tuned 1B encoder beats Jev at strict false-positive rates on safety.
- Consequence: guardrails must never rest on a single decision model.

**Pattern D1**
- The vendor's AutoResearch cookbook is *not* distillation (Jev stays in the serving path). D1 is our own pattern and has no vendor precedent.

**Superseded**
- phase-0-plan-critic Risk 3.2 ("no public calibration metrics") no longer holds.
