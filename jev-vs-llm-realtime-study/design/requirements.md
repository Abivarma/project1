# Requirements: real-time support assistant (assumed example)

Status: v1 (lead). Numbers cite rows in the Phase 1 evidence ledger (`research/evidence-ledger.md`).

> **Why this scenario.** The user's actual real-time workload is unknown, so a customer-support assistant stands in for it. It is Jev's *best-case domain*: the vendor's intent-routing pattern uses exactly this example. To balance that, this document also lists the in-scenario work where Jev is a poor fit (§3.3).

## 1. Clarifying questions (ask these first in the interview), with the defaults used here

| # | Question | Why it changes the design | Default used |
|---|---|---|---|
| Q1 | Modality: chat, voice, or agent tool-routing? | Voice adds endpointing, speech-to-text (ASR) and text-to-speech (TTS) to the critical path. Jev is text-only, which forces a cascaded voice pipeline | Chat + voice |
| Q2 | What is the latency SLO, and where does the clock start and stop? | Decides which hops count | See §4 |
| Q3 | Where are the users? | Jev is currently served only from the US West Coast [Likely], so network round trip can consume the budget | Sweep: US-West, US-East, EU, India |
| Q4 | Volume and peak-to-average ratio? | Rate limits and capacity become hard constraints | 1M / 10M / 50M messages/day; peak = 3.5× average |
| Q5 | Languages? | Jev is best in English. Classifiers need per-language labels | English first; Hindi/code-mixed as a slice |
| Q6 | Do labelled examples exist? How many? | Labels let a classifier (C1) or a distilled model (D1) match accuracy, and post-hoc calibration needs labels too | Sweep N = 0, 10, 50, 200 per intent |
| Q7 | How often does the intent taxonomy change? | Retraining cost (C1, D1) vs editing a prompt or rubric (Jev, LLM) | Monthly |
| Q8 | Compliance and data residency (GDPR, India DPDP)? | Third-party processing, retention, zero-data-retention (ZDR) availability | PII must not leave the region unless covered by a DPA |
| Q9 | Is the cost of an error asymmetric (wrong refund vs needless escalation)? | Sets confidence thresholds and whether each decision fails open or closed | Refund/safety decisions fail closed |
| Q10 | Budget per 1,000 messages? | Bounds the generation tier | Parameter |

## 2. Functional requirements

Each inbound user turn passes through these steps. "Decision" steps are System-1 shaped (bounded output); generation is System-2 shaped.

| ID | Step | Output type | On the critical path? |
|---|---|---|---|
| FR1 | Input guardrail: abuse, self-harm, prompt injection, PII present | Noul × 4 | Yes. It can run *in parallel* with speculative generation, and generation is discarded if it fails |
| FR2 | Intent routing (about 15–77 intents plus out-of-scope) | Choice | Yes. It selects the handler |
| FR3 | Urgency / frustration score | Score (0–3) | No. Only used for priority and tone |
| FR4 | Needs a human? | Noul | Yes |
| FR5 | Policy eligibility. The model *extracts* fields (Choice over enumerations); code does the date and amount comparisons | Choice + code | Yes, for the refund and returns intents only |
| FR6 | Next-best action | Choice | Yes |
| FR7 | Generate the reply (streamed text, or speech in voice mode) | Free text | Yes |
| FR8 | Output guardrail: policy, PII leakage, tone. In voice mode, checked per streamed sentence | Noul × 3 | Yes, per sentence |
| FR9 | Log every decision with its probabilities, confidence, model version and provenance, for audit and recalibration | — | No |

Decisions per message is a parameter, 3–15, defaulting to 7 calls' worth of questions.

## 3. Where each part of the workload fits

### 3.1 System-1 shaped: candidates for Jev, a small LLM, or a classifier
FR1, FR2, FR3, FR4, FR6, FR8, plus the extraction half of FR5.

### 3.2 System-2 shaped: needs an LLM
FR7 (generation), multi-hop eligibility reasoning, and explaining a decision to the user.

### 3.3 In-scenario work where Jev is a poor fit (documented jaggedness)

| Case | Why | Mitigation in the Jev design |
|---|---|---|
| Date windows ("bought within 30 days?"), amounts, counting | Jev's own docs flag math and date comparison as unreliable | Extract the parts with a Choice question; compare in code |
| Multi-hop policy ("if gold tier and not refunded in 90 days unless…") | Indirection is a documented failure mode | Split into atomic questions, or send to an LLM |
| Account history longer than 32k tokens | Context limit, plus "context rot" | Retrieve and filter before calling Jev |
| Hindi, code-mixed text, other non-English input | English is the primary language; accuracy is lower elsewhere | Language-ID gate; route to the LLM path |
| Image attachments (damaged-item photos) | Text-only input | Vision LLM caption → Jev, or the LLM path |
| Prompt injection aimed at the guardrail itself | "Adversarial content … can move the answer" | Dedicated injection classifier plus an LLM second check; fail closed |
| Free-text reply | Jev does not generate | An LLM always does FR7 |

## 4. Non-functional requirements (each SLO states where the clock starts and stops)

| ID | Requirement | Start → stop | Target |
|---|---|---|---|
| NFR-1 | Decision-path latency | Message accepted at our regional API gateway → all *on-path* decisions (FR1, FR2, FR4, FR6) available to the orchestrator | p95 ≤ 300 ms, p99 ≤ 600 ms |
| NFR-2 | Chat time to first token | Gateway accept → first reply token sent to the client | p95 ≤ 1.0 s |
| NFR-3 | Voice time to first audio | **User's last speech frame** → first TTS audio byte at the client. Includes the endpointing wait | p95 ≤ 800 ms. Human turn gaps are about 200 ms (LLM-068/069), so ≤ 800 ms feels responsive |
| NFR-4 | Output-guardrail cost per sentence | Sentence complete → sentence released to TTS or the client | p95 ≤ 150 ms |
| NFR-5 | Availability of the decision service | — | 99.9%. On vendor failure, degrade to a fallback backend; never block the user indefinitely |
| NFR-6 | Per-call deadline on the real-time path | — | 250 ms per decision call; at most 1 retry, and only if it fits the deadline; hedged requests allowed |
| NFR-7 | Quality | Held-out golden set | Intent macro-F1 ≥ target. Safety-class recall ≥ 0.98. Automated decisions ≥ 97% accurate at ≥ 70% automation, measured on the risk–coverage curve |
| NFR-8 | Calibration | Golden set | ECE ≤ 0.05 (equal-mass bins, stated) before thresholds go live. Recalibrate on every model-version change |
| NFR-9 | Cost | — | Report $ per 1,000 messages, split into decisions, generation, human review and infrastructure |
| NFR-10 | Residency and retention | — | Per region; no PII to a processor without a DPA. Zero data retention where required |
| NFR-11 | Security | — | Injection-robustness slice passes; no secrets in state; least-privilege routing |
| NFR-12 | Observability | — | Per-decision log: probabilities, confidence, model version, latency, tokens, cost. Drift dashboards on confidence distributions |

### 4.1 Fail-open or fail-closed, per decision

| Decision | If the backend times out or errors |
|---|---|
| FR1 input guardrail | **Fail closed** for injection and self-harm (route to a safe template or a human). Fail open for PII detection (redact downstream) |
| FR2 intent | Fall back to C1, then to the generic LLM handler |
| FR3 urgency | Fail open (default priority) |
| FR4 needs a human | **Fail closed** (offer a human) |
| FR5 eligibility | **Fail closed** (no automatic refund) |
| FR6 next-best action | Fail open (default action) |
| FR8 output guardrail | **Fail closed** (hold the sentence and use a safe fallback phrase) |

## 5. Capacity: back-of-envelope formulas (values filled in by M1)

```
avg_msg_per_s  = V / 86,400
peak_msg_per_s = 3.5 × avg_msg_per_s
req_per_s(arch)    = peak_msg_per_s × calls_per_msg(arch)
tokens_per_s(arch) = peak_msg_per_s × input_tokens_per_msg(arch)
headroom(arch, limit) = vendor_limit / demand        (must be ≥ 1.5 to absorb bursts)
```

| Volume V | Average msg/s | Peak msg/s (3.5×) |
|---|---|---|
| 1M/day | 11.6 | 40.5 |
| 10M/day | 115.7 | 405 |
| 50M/day | 578.7 | 2,025 |

### 5.1 Jev token model (Critic-1 re-derivation)
```
tokens_per_call = overhead (about 250–300) + state + Σ question_tokens
question_tokens ≈ 57 (short Noul) … 75–95 net (support rubric Choice); a 77-option Choice ≈ 1,670 (JEV-051)
```

### 5.2 Headroom at default or published limits (peak, one batched decision call per message, about 2,000 input tokens)
| Volume | Peak msg/s | Jev at 80 req/s and 100K tok/s (token-bound, about 50 msg/s) | Haiku 5.5 at Scale tier, 10K RPM (about 167 req/s); cache reads not counted in ITPM | GPT-6 Luna at Grow tier, 30K RPM (500 req/s); cached tokens *do* count in TPM |
|---|---|---|---|---|
| 1M/day | 40.5 | **1.2×** (marginal) | 4.1× | 12× |
| 10M/day | 405 | **0.12×** (infeasible) | 0.41× (infeasible) | 1.2× (marginal) |
| 50M/day | 2,025 | **0.025×** (infeasible) | 0.08× (infeasible) | 0.25× (infeasible) |

Sources: JEV-005, JEV-006, LLM-029, LLM-084, R2 capability matrix. Takeaway: **at 10M+/day every hosted option needs negotiated limits.** Only self-hosted options (L3, C1, open-weight decision models) scale under our own control.

### 5.3 Real-time client settings (all hosted backends)
- Per-call deadline: 250 ms.
- Retries: at most 1, and only within the deadline.
- Hedged second request: after p90 latency.
- Circuit breaker: on 429/529/timeouts, with fallback per §4.1.
- The Jev SDK defaults (10 s timeout, 2 retries, 30 s budget) **must be overridden** (JEV rows, Critic-1 finding 9).

## 6. Per-hop latency budgets (ledger values; the Monte Carlo in M1 turns these into p95)

> **Gap:** no p95 or p99 has been published for Jev or for any LLM decision path (evidence ledger, "Known gaps"). Every p95 below is *modelled*, and M1 reports the threshold at which each verdict flips.

### 6.1 Network round trip from our regional gateway to the decision backend (P50, datacenter backbone)
| Gateway region | To a Jev endpoint (us-west-2 only) | To an in-region backend | Source |
|---|---|---|---|
| US-West | about 1–9 ms | about 1–9 ms | ECO-073 |
| US-East | 70–71 ms | about 1–2 ms | ECO-069, ECO-072 |
| EU (Frankfurt / Ireland / NL) | 126–154 ms | about 2 ms | ECO-068, ECO-072 |
| India (Mumbai / Pune) | **211–240 ms** | about 1–2 ms (only if an in-region option exists; see P1-IN) | ECO-066, ECO-071 |

### 6.2 Decision compute and service time (median; where each figure was measured from)
| Backend | Median | Conditions | Source |
|---|---|---|---|
| Jev (independent tests) | 0.10–0.39 s | Probe location mostly unstated, so the figure likely *includes* some network round trip. Barely changes from 1 to 64 questions | JEV-028, JEV-030, JEV-031 |
| Small LLM, thinking off (proxy) | TTFT 0.48–0.83 s, **plus** about 20–60 output tokens at 87–126 tok/s, which adds roughly 0.2–0.7 s | Artificial Analysis at 10k input from us-central1. Our approx. 2k input would have a lower TTFT. Haiku 5.5 thinking-off has not been benchmarked | LLM-006, LLM-007, LLM-011, LLM-015 |
| Small LLM, thinking left at its default | **9.7–13.4 s** to the first answer token | Haiku 5.5 at low and medium effort | LLM-003, LLM-004 |
| Hosted decision API (OpenAI Decisions) | 0.31 s | Same harness as Jev's 0.39 s on BANKING77 | Critic-1 V-table, JEV-087 |
| C1a classifier, in-process | about 1.5 ms (TF-IDF) / 0.25 ms (model2vec) | Measured here on CPU [LAB, illustrative] | lab/results/c1_sweep.csv |

### 6.3 Chat decision path (NFR-1: p95 ≤ 300 ms from gateway accept)
| Path | Rough median | Verdict before Monte Carlo |
|---|---|---|
| Jev, gateway in US-West | 0.10–0.39 s | **Borderline.** Fits at the low end of the medians; p95 is unknown |
| Jev, gateway in India | 0.21–0.24 s round trip + 0.10–0.39 s | **Fails** (P1-IN) |
| Small LLM API, thinking off | ≥ 0.5–1.2 s | **Fails** at p95 |
| C1a / L3 in-region | ≤ 0.05 s | **Passes** |

### 6.4 Voice (NFR-3: p95 ≤ 800 ms from the user's last speech frame)
| Hop | Typical | Source |
|---|---|---|
| End-of-turn detection | about 260 ms (Deepgram Flux); 128–512 ms minimum silence (AssemblyAI) | LLM-056, LLM-057 [vendor] |
| Final transcript | about 307 ms median | LLM-058 [vendor] |
| On-path decisions | Run in parallel with LLM generation, so off the critical path *if* generation is speculative | §2 FR1 |
| LLM time to first token (small tier, thinking off) | 0.48–0.83 s at 10k input | LLM-007, LLM-011 |
| First-sentence output guardrail (FR8) | Jev about 0.10 s in-region vs small LLM ≥ 0.5 s | as in 6.2 |
| TTS time to first audio | 128–197 ms median, measured | LLM-060 |
| **Cascaded total** | about 0.26 + 0.5–0.8 + 0.1 + 0.13–0.2 ≈ **1.0–1.4 s median** | **Over budget.** Needs eager end-of-turn detection and speculative generation |
| **Speech-to-speech model (V-S2S)** | about 0.8 s turn-taking (GPT-Live-1, press-reported) | LLM-063, LLM-064 |

**Takeaway for the interview:** in voice, *decisions are not the bottleneck*; endpointing and LLM time to first token are. Jev's speed matters most for the **per-sentence output guardrail** (FR8, a 150 ms budget) and for **many decisions on one state** (fan-out). Humans leave a gap of about 200 ms between turns (LLM-068 [downgraded: excerpt-sourced], LLM-069).
