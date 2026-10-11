# Requirements: real-time support assistant (assumed example)

Status: DRAFT (lead). Numeric cells marked `⟨ledger⟩` are filled once the Phase 1 evidence ledger passes its gate.

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
| NFR-3 | Voice time to first audio | **User's last speech frame** → first TTS audio byte at the client. Includes the endpointing wait | p95 ≤ 800 ms. Human turn gaps are about 200 ms, so ≤ 800 ms feels responsive ⟨ledger⟩ |
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

### 5.1 Jev token model (to be verified in R1)
```
tokens_per_call = overhead (~300) + state + Σ question_tokens   (~57 per short question; much more with long option criteria)
```

### 5.2 Jev at default limits (80 req/s, 100K tokens/s)
- With 1 call per message and about 2,000 tokens per call, the token limit binds at about 50 msg/s.
- At 1M/day (peak 40.5 msg/s) the **headroom is about 1.2**, so it is marginal.
- At 10M/day and 50M/day, J1 is **infeasible** without enterprise limits (falsification test P4).

## 6. Per-hop latency budgets (filled in from the ledger and M1's Monte Carlo)

### Chat, decision path (NFR-1)
| Hop | p50 | p95 | Notes |
|---|---|---|---|
| Client → gateway (TLS reused) | — | — | Not counted; the clock starts at the gateway |
| Gateway → decision backend round trip (region-dependent) | ⟨ledger⟩ | ⟨ledger⟩ | India → US-West ≈ ⟨ledger⟩ |
| Backend compute (Jev / small LLM / C1) | ⟨ledger⟩ | ⟨ledger⟩ | Jev publishes no p95, so it is modelled |
| Queueing at peak, plus retry tail | ⟨M1⟩ | ⟨M1⟩ | |
| **Total** | | **≤ 300** | |

### Voice (NFR-3), cascaded pipeline
| Hop | p50 | p95 |
|---|---|---|
| Endpointing / voice-activity-detection hang time | ⟨ledger⟩ | ⟨ledger⟩ |
| Final speech-to-text transcript | ⟨ledger⟩ | ⟨ledger⟩ |
| On-path decisions (parallel) | from the chat path | |
| LLM time to first token | ⟨ledger⟩ | ⟨ledger⟩ |
| First-sentence output guardrail | ⟨ledger⟩ | |
| TTS time to first audio | ⟨ledger⟩ | ⟨ledger⟩ |
| **Total** | | **≤ 800** |

The speech-to-speech alternative (V-S2S) replaces the middle hops with a single model's time to first audio ⟨ledger⟩.
