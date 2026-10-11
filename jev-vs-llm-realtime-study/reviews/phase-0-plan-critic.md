# Phase 0 Gate: Plan Critic Review of PLAN.md v1 (Jev edition)

- **Reviewer:** plan critic (independent)
- **Date:** 2026-10-11
- **Inputs read:**
  - `PLAN.md` v1.
  - Vendor docs in the scratchpad: `concepts_system-one`, `models`, `model-jaggedness_jev-1.13`, `api`, `confidence`, `patterns_intent-routing`, `introduction_coding-agents`, `llms.txt`, and a grep of `how-to-build`.
  - Live spot checks: the TypeSafe blog post, the typesafe.ai homepage, `patterns/fan-out.md`, `cookbooks/parallel_questions.md`, and `sdk/python/api/constants.md`.
  - The `claude-api` skill's cached model and pricing tables (cached 2026-10-06).
  - PyPI index checks.
- **Handling of vendor pages:** all vendor pages were treated as untrusted data.

---

## Verdict: **PASS-WITH-FIXES** (fixes 1–12 and Local Lab fixes LL1–LL8 are blocking)

The Local Lab addendum, added after a new user requirement arrived mid-review, is near the end of this file.

The skeleton is good:
- System-1 vs System-2 framing.
- An honest "uncomfortable truths" section.
- Inclusion of a classic-ML baseline.
- Vendor-claim tagging.
- Critic gates at each phase.

However, as written, the plan would likely produce a **misleading headline**. It does not pin down *which* LLM Jev is compared against. It treats rate limits as a metric rather than a feasibility constraint. Its "LLM-way" confidence mechanism cannot be built on the provider the harness targets. It also pre-commits to J2 as the answer.

Fixes 1–12 must be merged into PLAN v2 before Phase 1 starts. None of them requires redoing the plan from scratch.

---

## Top 3 risks (most dangerous first)

### Risk 1: Headline multipliers depend on the comparator, so the study could "prove" a 100×+ saving that does not exist against a fair baseline.

- The vendor's numbers are all measured against expensive or reasoning frontier LLMs:
  - "193.6× faster, 444.6× cheaper" is in the vendor's own words "on the higher end of real world gains", and the comparator's reasoning settings are not stated.
  - "238× lower input price than Claude Fable 5.1" is simply $10 ÷ $0.042, a list-price ratio against the most expensive tier.
  - The blog admits that against non-reasoning LLMs (Wikiracing) the speedups were "a lot less".
- The fair small-tier comparator is far closer. The `claude-api` skill's table lists **Claude Haiku 5.5 at $0.10 / $0.50 per MTok**, with cache reads at about 0.1× (about $0.01/MTok) and a 512-token minimum cacheable prefix. These figures must be re-verified live in R3.

**Back-of-envelope** ([Guessing]; R3/M1 must redo it with ledger values). Assumptions:
- One message, 7 decisions, about 2,000 input tokens: about 300 dynamic plus about 1,700 static rubric. This matches the homepage example's implied size: $0.000081 ÷ $0.042/MTok ≈ 1,929 tokens.
- Haiku tokenizer counts about 1.3× more tokens for the same text.

| Path | $ per message | Ratio vs Jev |
|---|---|---|
| Jev J1 (one fan-out call) | 2,000 × $0.042/M ≈ **$0.000084** | 1× |
| Haiku-5.5-class L2, one call, thinking off, rubric cached, 60 output tokens | 2,210 cached × $0.01 + 390 × $0.10 + 60 × $0.50 (per M) ≈ **$0.000091** | ≈ **1.1×** (near parity) |
| Same, no caching | ≈ $0.00029 | ≈ 3.5× |
| L1: Fable 5.1, 7 calls with reasoning (about 500 output tokens each) | ≈ $0.315 | ≈ 3,750× |
| Generation (Sonnet 5.5-class reply, partly cached, 250 output tokens) | ≈ **$0.005** | decisions are only **about 1–3% of the per-message bill** |

**Implication:** price is *not* a strong differentiator against a well-built small-LLM baseline. The total bill barely moves. The differentiators that remain to test are:
- critical-path latency, including tail latency;
- native full probability distributions and calibration;
- simplicity of the typed API;
- capacity and operational risk.

The plan currently names "latency, price, and calibrated confidence" and frames the study as Jev vs L1/L2. That invites a 100×-style headline.

### Risk 2: J1/J2 cannot serve the stated scale, and the plan treats this as a metric instead of a design-gating constraint.

- Documented limits are **80 req/s and 100K tokens/s**. They "can change without notice", and higher limits require custom or enterprise plans.
- The plan's peak is **2,000 msg/s**. At about 2,000 tokens per message:
  - 4M tokens/s, which is **about 40× over** the token limit;
  - **25× over** the request limit.
- At default limits, Jev sustains at most about 50 msg/s, because tokens are the binding limit. With a 3.5× peak factor, that is only about 1.2M msgs/day.
- Additional facts that compound the risk:
  - Jev is in early access with a waitlist, per the blog.
  - Its service is "currently based" on the West Coast.
  - No SLA is published.
  - The SDK defaults to a 10 s per-operation timeout and automatic retries with backoff on 429/529. Left unchanged, those retries will blow a 300 ms p95 budget.
- Any J-architecture without an explicit enterprise-limit assumption, a capacity-headroom ratio, a per-call deadline and a non-Jev fallback is not a valid design.

### Risk 3: The quality and calibration comparison could be reported with false confidence.

1. **Vendor accuracy is not ground truth.** The vendor's "accuracy" means agreement with the average of GPT-6 Astra and Fable 5.1. The vendor admits this biases results toward OpenAI and Anthropic.
2. **Jev has no public calibration metrics.** "Calibrated" is asserted without ECE or Brier numbers.
3. **"0% hallucination" is admitted to be "not empirical".**
4. **The LLM-side confidence plan cannot run on Anthropic.** L2 relies on "logprobs for confidence", but the M2 harness targets Anthropic. To the critic's knowledge, the Claude Messages API does not return token logprobs; the skill reference does not mention them anywhere. R2 must verify. As written, LLM-side ECE is undefined.
5. **The live path cannot be run.** There are no API keys, and Jev is behind a waitlist.

Taken together, nothing about relative accuracy or calibration can be *measured* here. If the study is not explicit about that, mock outputs or agent-synthesized labels will leak into numbers that look like findings.

---

## Required fixes (numbered, concrete edits to PLAN.md)

### 1. Add a "comparator ladder" (Section 0, Section 3, M1)

Every Jev ratio (latency, $) must be reported against **each rung**, and no multiplier may appear in STUDY.md without its rung named. The rungs:

- (a) L1: frontier model with reasoning. This is the vendor's comparator and an anti-pattern.
- (b) Frontier model, no reasoning.
- (c) Mid-tier model.
- (d) Small tier with prompt caching and thinking disabled: Claude Haiku 5.5-class, plus the cheapest Gemini and OpenAI tiers.
- (e) L3: a self-hosted small open-weight model.
- (f) C1: a classifier.

Add Haiku 5.5 ($0.10/$0.50, cache read about 0.1×, 512-token cache minimum, tokenizer about 1.3×, thinking on by default) to R3's mandatory list.

### 2. Make capacity a gating constraint (Section 1, Phase 2)

- Replace the single 50M/day point with a **volume sweep** of 1M, 10M and 50M msgs/day.
- Justify the 50M/day figure (50M/day ≈ 579 msg/s average; 2,000 msg/s is a 3.5× peak). Say whether "messages" means user turns.
- `requirements.md` must compute req/s and tokens/s for each architecture at average and peak load, and divide by each vendor's documented limit to get a headroom ratio.
- Each J design must:
  - state the enterprise limit it assumes (marked [Guessing]);
  - set a per-call deadline (e.g., 150–250 ms) and cap retries on the real-time path;
  - define what happens on 429/529 or timeout (fallback to C1 or L2, plus a circuit breaker);
  - state per decision whether a failure fails open or fails closed.

Do the same for LLM rate limits. Note that on the Claude API, cache reads do not count toward input-token limits; verify this.

### 3. Fix the L2 confidence mechanism and the harness provider mismatch

Add a **provider capability matrix** to R2 covering, per provider and per tier:
- structured outputs: name, guarantees, refusal and truncation caveats;
- logprob availability;
- prompt caching price and minimum length;
- regions and inference geography;
- rate-limit tiers;
- data retention and ZDR.

Then do one of the following:
- Run L2 on a provider that exposes logprobs. Single-token option codes with logprobs give a full distribution, which is the closest analogue to Jev.
- Or define LLM confidence as verbalized confidence or k-sample self-consistency, and charge k× cost and latency for it.

The harness must document exactly how LLM-side ECE is computed.

### 4. Add the missing architectures and relabel L1

- **L3: self-hosted small open-weight LLM, in-region.** Uses constrained decoding (vLLM/SGLang-style grammar) and **scores the option tokens** in one forward pass, so it returns a full probability distribution and no free text. This is the technically closest rival to Jev. It is also the residency and privacy answer.
- **L2c: LLM-only confidence cascade.** A small model escalates to a frontier model by confidence. Without it, J2 (a cascade) is compared against L2 (no cascade), which is unfair.
- **C1a and C1b.** Split C1 into C1a, embeddings plus logistic regression or kNN (few labels), and C1b, a fine-tuned encoder. Section 0 mentions both, but the table has only one.
- **H1: Jev as teacher.** Jev or an LLM labels data, a classifier is distilled from those labels for the high-volume "head" intents, and Jev keeps the long tail and cold start. This follows the vendor's own AutoResearch cookbook and is a strong interview answer.
- **Voice LLM-way.** A speech-to-speech realtime model compared against the cascaded ASR → decisions → LLM → TTS pipeline. Jev is text-only, so the Jev-way *forces* the cascaded pipeline.
- **Relabel L1** as "vendor comparator / anti-pattern". Keep it only to reconcile with the vendor's numbers and exclude it from headline comparisons.

### 5. Remove the pre-commitment

Delete "expected recommendation" from J2. Add a **pre-registered hypotheses** section, H1–H6, each with a falsification rule fixed *before* Phase 3. Examples:

- **H1:** From the user's region, Jev's decision-path p95 is ≤ 300 ms while the best API-LLM path is above 300 ms.
- **H2:** Once generation is included, Jev cuts the total per-message bill by less than 5% compared with L2 on a cached small tier.
- **H3:** With at least N labelled examples per intent, C1 matches Jev accuracy within 2 points at lower cost.
- **H4:** J1 cannot serve peak load at default limits.
- **H5:** Jev's advantage is largest at zero labels with a churning taxonomy.
- **H6:** Jevons-style fan-out raises decision spend by k× while the total bill stays dominated by generation.

### 6. Handle the unknown user use case (Section 1)

The user said "I need a good realtime experience" without naming the workload.

- State explicitly that customer support is an **assumed exemplar**.
- Add a "Requirements clarification" subsection listing the 8–10 questions an interviewer expects:
  - modality (chat, voice or agent);
  - latency SLO and where the measurement starts;
  - users' regions;
  - volume and peak;
  - languages;
  - labels available;
  - how often the taxonomy changes;
  - compliance and residency;
  - error-cost asymmetry;
  - budget.
- Make M1 parametric through a "bring your own workload" parameter card.
- Optionally ask the user one question at the end of Phase 0 (use case and region). This is non-blocking: proceed with defaults if there is no answer.
- **Remove the claim** that the scenario is "fair to both sides". It is the vendor's showcased pattern: the intent-routing doc's example is literally customer-service routing, and there is a guardrails cookbook. Balance it by modelling **Jev's losses inside the primary scenario**:
  - policy eligibility involving dates and amounts;
  - multi-hop reasoning;
  - account history longer than the 32k state limit;
  - non-English and code-mixed text (the vendor says English is best);
  - image attachments;
  - prompt injection against Jev-as-guardrail (the vendor says adversarial content "can move the answer").

### 7. Rework the secondary scenarios

- **Keep S2 (moderation),** with C1 as the strongest rival.
- **Convert S3 into a "Jev boundary checklist".** Numeric and date tasks are a documented non-use, not a scenario.
- **Replace S4 (Doom).** The vendor admits "a non-AI doom bot could play better", and about 100 ms per decision cannot do frame-level control. Use instead one or both of:
  - **S4′:** tool/skill routing inside an LLM agent loop (vendor cookbook: 182 skills);
  - **S5:** a voice turn-taking, barge-in or endpointing decision, which is latency-critical and System-1-shaped.
- **Add one scenario where the LLM clearly wins:** a real-time speech-to-speech conversation, or multi-hop eligibility reasoning over long history.
- Keep Doom as a one-line sanity check: about $7/h at 10 q/s implies about 4.6K tokens per query.

### 8. Make the latency model complete (Section 3)

- **SLO boundaries.** Define the start and stop point of every SLO. For voice, is the clock started at end-of-speech or at endpoint detection? VAD endpointing alone can take 300–700 ms of an 800 ms budget.
- **Per-hop components to model:**
  - client-to-vendor RTT by region (the vendor's numbers were run "from our laptops on the West Coast" next to the service);
  - TLS and connection reuse;
  - queueing at peak;
  - p99 and p99.9 latency;
  - 429/529 retries with backoff;
  - hedged requests;
  - cold start and autoscaling for self-hosted C1 and L3.
- **Latency vs state size.** Docs say "most queries about 100 ms". The parallel-questions cookbook measured about 0.21 s per single-question call and 0.27 s batched (13 questions) on an approximately 54K-character state.
- **Critical-path analysis:**
  - decisions on the path vs off the path;
  - the input guardrail running in parallel with speculative generation;
  - the output guardrail per streamed sentence for voice. This is where Jev's speed matters most.

### 9. Fix the token and charge model (Section 3, M1)

- **(a) Question tokens are billed.** Jev bills question `instructions` and `criteria` as input on every call. For short support messages the **rubric dominates**, so the fan-out "state billed once" saving is small. Model state tokens and question tokens separately.
- **(b) Caching asymmetry.** LLM prompt caching gives about 0.1× on the static rubric, and Jev documents no cache discount. Model both.
- **(c) Tokenizer normalization.** Compare **$ per message or per 1K characters**, never $ per token across vendors.
- **(d) Thinking tokens.** Include LLM thinking tokens: Haiku 5.5 has thinking on by default, and it must be disabled or counted.
- **(e) Full TCO:**
  - human-review cost from escalations;
  - expected cost of errors (misroutes, wrong refunds);
  - GPU cost for C1/L3 at peak provisioning plus N+1 redundancy and multiple regions;
  - labelling cost;
  - prompt/rubric maintenance effort;
  - enterprise minimum commitments.
- **(f) Price-change sensitivity.** The vendor says "We can't prove it isn't subsidized." Run M1 at 1×, 3× and 10× Jev's price.

### 10. Fix the quality metrics (Section 3)

- **Primary cascade metric:** selective prediction, meaning the risk–coverage curve and accuracy at automation rate X%, plus AURC.
- **Calibration:** Brier score, reliability diagrams, and ECE with the binning stated.
- **Classification:** macro-F1, and recall on the safety classes.
- **Consistency:**
  - an option-order permutation test for both Jev (documented bias toward the first option) and LLMs (known position bias);
  - run-to-run determinism.
- **Slices:** a multilingual slice, and an injection-robustness slice for the guardrail.
- **State these caveats explicitly:**
  - Post-hoc calibration (temperature, Platt or isotonic scaling) can calibrate C1 and L3 once labels exist, so Jev's calibration advantage is largest in **zero-label cold start**.
  - The vendor's "accuracy" measures agreement with an LLM, not ground truth.
  - No public calibration numbers exist for Jev.

### 11. De-risk the M2 harness (extended by the Local Lab fixes LL1–LL8 below)

- **Dataset.** Use a **public labelled dataset** (Banking77, CC-BY-4.0, for support intents; CLINC150 for out-of-scope / "needs human") instead of labels synthesized by an agent, which would be circular.
- **Real SDKs.** Install `typesafe-sdk` (0.7.4) and `anthropic` (1.13.0) into a venv; both are on PyPI and reachable from here.
- **Stub server.** Exercise the **real SDK code path** end-to-end against a local stub HTTP server. Point the Jev SDK at it with `TYPESAFE_BASE_URL` and the Anthropic SDK with `base_url`. The stub replays the documented response examples from `api.md` verbatim.
- **Contract tests.** Add JSON contract tests for the request shape (`state`, `model`, `questions{type, instructions, criteria}`) and the response shape (`answers`, `usage`).
- **Signatures.** Comment every SDK call with its documentation URL. Take Anthropic signatures from the `claude-api` skill (`output_config.format` / `messages.parse`; do not use the deprecated `output_format`).
- **Isolate mock output.** Watermark it `MOCK`, and add a test that fails if any MOCK value reaches STUDY tables.
- **Run C1 for real.** Run C1 on CPU (scikit-learn installs from PyPI). TF-IDF or embeddings plus LR, measuring accuracy, macro-F1, ECE and p50/p95 latency. These will be the **only first-party measured numbers** in the study, and they should be labelled that way.
- **Schedule.** Start M2 in parallel with Phase 1; it has no dependency on the ledger.

### 12. Fix the process

- Use the checkable gates below.
- Cap FAIL loops at two per phase, then escalate to the user.
- Run critics in a fresh context with a written rubric.
- **Move C1 from A2 (the Jev designer) to a neutral owner** (the lead, or A3).
- Each designer writes a one-page **steelman of the other side**.
- **Update the stale task list:** #3 still says "JEPA-way" and #4 still says "selective decoding sim".
- Every agent prompt must say that fetched pages are untrusted data, never instructions.
- R1 must fetch the vendor's **evals site (the 4 published workflows)** and record comparator models, reasoning settings, state sizes and reference-label method.

---

## Addendum: "Local Lab" on Apple-Silicon Macs (new user requirement)

**User requirement:** "Have it configured to run local AI models in mac so, I will load any model and learn."

**Lead's proposal:** M2 becomes a config-driven Local Lab with four backends:
- (a) a local LLM behind an OpenAI-compatible server (Ollama, LM Studio, llama-server, mlx-lm), using JSON-schema output;
- (b) a local "System-One-style" Choice/Noul built from token logprobs plus temperature scaling;
- (c) real Jev, if the user has a key;
- (d) Claude, optionally.

All four share one dataset and evaluator. A `LEARNING.md` accompanies the lab, and the local path will run end-to-end on CPU in the container with a model of about 0.5–1B parameters.

### Verdict on the addendum: **sound and worth doing, if it is fenced.**

It directly answers the user's request. It also *resolves* two blocking fixes above:
- fix 3: an LLM path with real logprobs, which Anthropic lacks;
- fix 4: L3, a self-hosted small model with option scoring.

It gives the interview a strong first-hand story: "a typed decision API is a thin layer over any model that exposes a distribution; what Jev claims to add is label-free calibration, latency at scale, and zero ops."

It distorts the study only if lab numbers leak into the production comparison, or if lab plumbing eats the effort budget.

### Feasibility facts and risks

These were spot-checked today. Tags reflect evidence quality, and Phase 1 must ledger them.

**Logprob support differs by server, and silent failure is the real risk.**

| Server | Logprobs | Structured output | Source / tag |
|---|---|---|---|
| Ollama | Native and OpenAI-compatible APIs return `logprobs`/`top_logprobs` **since v0.12.11**. | Has had JSON-schema `format` for a long time. | Medium article and LangChain docs [Likely] |
| LM Studio | Exposes logprobs on `/v1/responses`, via `include: ["message.output_text.logprobs"]` plus `top_logprobs`. Chat-completions support is unverified. | — | LM Studio blog [Likely] |
| mlx-lm server | Implements logprobs, per its SERVER.md as cited in a third-party issue. | **Unverified.** mlx-vlm documents `json_schema` structured outputs. | [Likely] |
| llama.cpp `llama-server` | Supports OpenAI-style logprobs and grammar/JSON-schema constraints. | Yes | Critic's knowledge; verify. |
| omlx (MLX front-end) | **Silent-failure example:** the GitHub issue says it accepts `logprobs` but returns empty `logprobs.content`. | — | GitHub issue |

The silent-failure case means the harness must **probe capabilities and fail loudly**, never degrade quietly to "no confidence".

**Tokenization pitfalls when scoring options** (the main technical risk):
1. **Shared first tokens.** Options such as `refund_status` and `refund_request` can share the same first token, so first-token probability merges them. Fix: map options to unique **single-token codes**, or score each full option sequence by teacher forcing. Prefer the sum of log-probabilities, and report length-normalized scores as a variant.
2. **Leading-space and case variants.** `"A"`, `" A"` and `"a"` are different tokens. Sum the probability mass over the variants, or constrain the output so only one variant is possible.
3. **The label is often not the first generated token.** With a chat template or JSON mode, the first tokens may be whitespace, `{"intent":"`, a quote, or `<think>`. The harness must locate the label's token position.
4. **Thinking models** (Qwen3-style `<think>`, reasoning channels) must have thinking disabled, or the first-token logprobs are meaningless.
5. **The top-k cap truncates probability mass.** `top_logprobs` is typically capped at about 20. With 20+ intents (Banking77 has 77), some options get no probability. Report the **captured mass** per item, and route to full-sequence scoring when it is below a threshold such as 0.9.
6. **Grammar and logprob interaction.** Depending on the server and its flags, a grammar or JSON-schema mask may return logprobs *before* the constraint or *after* it (renormalized). llama.cpp has a post-sampling-probabilities option. These give different calibration. Record which mode was used, and test it by comparing constrained and unconstrained runs.
7. **Letter-code position bias.** It mirrors Jev's documented option-order bias. Measure it with a permutation test and report the flip rate. Averaging over permutations costs k×.
8. **Quantization changes logits.** Q4_K_M, Q8 and MLX 4-bit give different calibration, so record the quantization level in every result row.
9. **Temperature-scaling leakage.** Fit T on a **calibration split only** and report ECE on a held-out test split, with bootstrap confidence intervals; with few samples per class ECE is noisy. Note that temperature scaling **needs labels**, which is exactly what Jev claims to avoid. Make that the lesson.

**Mac RAM guidance** ([Guessing]; LEARNING.md must state its assumptions):
- Q4 weights take about 0.55–0.6 GB per billion parameters. Add the KV cache (grows with context) and about 1–2 GB of runtime overhead.
- By default Metal can wire only about 65–75% of unified memory. This can be raised with `sysctl iogpu.wired_limit_mb`; flag it as an advanced setting with risk.
- Rough tiers:

| Mac unified memory | Comfortable model size (Q4 unless noted) |
|---|---|
| 8 GB | up to 3–4B |
| 16 GB | 7–9B; 12–14B is tight |
| 24 GB | about 14B |
| 32–36 GB | 27–32B |
| 64 GB | 70B |
| 96–128 GB | 70B at Q8, or large MoE models |

- For decision tasks the learning sweet spot is 1–8B.

**Container limits:** 4 CPU, 15 GB RAM, no GPU, no Mac.
- The **MLX and LM Studio paths cannot be executed here.** They must be labelled "untested on macOS". MLX on Linux CPU may or may not work; verify before claiming anything.
- Ollama and llama.cpp on Linux CPU *can* run here. They exercise the same OpenAI-compatible code path, so they are the right smoke test.
- A model of about 0.5–1B at Q4 is about 0.4–0.8 GB. At 4 vCPU, expect roughly tens of ms to a few hundred ms per short classification prompt. That is fine for a smoke test of N ≈ 200.
- A 0.5B model will be **weak at 77-way intent classification**. Use a 10–20 intent subset plus an out-of-scope class (CLINC150), and present accuracy as **lab-illustrative only**.

**Scope distortion risks:**
1. **Lab numbers are not production numbers.** Mac or CPU latency and tiny-model accuracy are not production numbers, and they are not Jev numbers either.
2. **"$-equivalent" for local inference** (power × time × $/kWh plus amortized hardware) is not comparable to API list prices without utilization assumptions.
3. **Naming.** Calling the emulator "local Jev" would be an overclaim. Use **"Jev-style decision primitive (emulation)"**.
4. **Plumbing creep.** Adapter work can eat the effort budget meant for M1 and STUDY.md.

### Required fixes for the Local Lab (LL1–LL8, blocking)

- **LL1 (one adapter, not four).** Build one OpenAI-compatible adapter for Ollama, LM Studio, llama-server and mlx-lm, configured by per-backend **capability flags**:
  - `supports_json_schema`;
  - `supports_logprobs`;
  - `max_top_logprobs`;
  - `logprob_mode` (pre or post constraint);
  - `label_scoring`: `top_logprobs` | `full_sequence` | `none`.
  
  Add an in-process **exact scorer** (transformers or llama-cpp-python, CPU) for full-sequence option scoring and as a correctness reference. The Jev SDK and Claude backends remain as specified in fix 11 (stub-server tests).
- **LL2 (startup capability probe).** Send a known prompt and assert that non-empty logprobs come back at the label position, that captured mass is at least 0.9, and that the schema is valid. Raise on failure; never degrade silently.
- **LL3 (scorer design).** Use a single-token code per option (verified against the loaded tokenizer when the run starts). Merge variants, find the label position, and disable thinking. Fall back to full-sequence scoring when the top-k cap or shared prefixes make code scoring unreliable.
- **LL4 (calibration protocol).** Use a fixed train/calibration/test split. Report temperature-scaling T, and ECE (equal-mass bins, with the count stated), Brier, a reliability diagram and bootstrap confidence intervals before and after scaling. Report a permutation flip rate. Record quantization and backend version on every row.
- **LL5 (provenance).** Tag every lab result `LAB:<backend>:<model>:<quant>:<hardware>`. A test must fail if `LAB` or `MOCK` values appear in STUDY.md headline tables; they may appear only in a clearly marked "hands-on lab" section.
- **LL6 (model safety).** Load only GGUF or safetensors, with `trust_remote_code=False` and no pickle checkpoints. Pin model repos and revisions in the config. Downloaded model files count as untrusted data.
- **LL7 (LEARNING.md):**
  - the RAM-tier table with assumptions;
  - exact install commands with versions for each backend;
  - a **verified-on matrix** separating what was actually executed in the container (Linux CPU) from what is untested on macOS;
  - at least 6 exercises with expected observations, e.g.:
    - JSON-mode vs logprob-scoring accuracy;
    - calibration before and after temperature scaling;
    - option-order bias;
    - effect of quantization on ECE;
    - latency vs state length;
    - "emulate Jev's Noul/Choice/Score confidence formulas from `confidence.md`";
  - troubleshooting: Ollama `keep_alive` cold starts, thinking models, top-k caps, silent empty logprobs.
- **LL8 (timebox and dependency).** Run the Local Lab in parallel with Phase 1, capped at about 30% of Phase 3 effort. M1 and Phase 4 must not wait on lab polish. Smoke runs use a tiny model only, with no large downloads.

### Gate criteria for the Local Lab (added to the Phase 3 gate)

- [ ] One documented command, e.g. `python -m lab run --config configs/ci-cpu.yaml`, completes end-to-end in the container. It uses a model of 1B or less through Ollama or llama-server on Linux CPU, runs N ≥ 200 labelled items, and finishes within the stated time budget. The run log is committed.
- [ ] The results CSV has, per backend × mode (JSON-schema generation vs logprob scoring):
  - accuracy and macro-F1;
  - ECE (with bins stated) and Brier, before and after temperature scaling;
  - p50/p95 latency, warm and cold reported separately;
  - input and output tokens;
  - $-equivalent with its formula and [Guessing] parameters;
  - captured mass;
  - permutation flip rate.
- [ ] Unit tests built on **fake logprob payloads** cover:
  - leading-space and case variants;
  - multi-token labels;
  - a `<think>` prefix;
  - JSON-wrapped label position;
  - top-k truncation;
  - an empty-logprobs server, which must raise.
- [ ] **Agreement check:** on the same model weights, option probabilities from the server's top-logprobs path match the in-process exact scorer, with an argmax match on at least 95% of items and mean |Δp| ≤ 0.05. Otherwise the difference is explained (e.g., quantization mismatch) and documented.
- [ ] A test asserts that the temperature-scaling fit uses only the calibration split.
- [ ] The `LAB`/`MOCK` leakage test passes, and STUDY.md labels the emulator "Jev-style (emulation)".
- [ ] LEARNING.md has the verified-on matrix, and every untested Mac path is labelled as untested.

---

## Recommended (optional) improvements

1. **Charts.** A comparator-ladder chart (log-scale $ per message and p95 latency per rung). A stacked "where the money goes" bar (decisions vs generation vs human review). A tornado sensitivity chart. A crossover plot of volume and labels against C1 vs Jev.
2. **Decision-service abstraction as the headline architecture idea.** A typed Choice/Score/Noul port with swappable backends (Jev, L2, L3, C1). This is the build-vs-buy hedge against a vendor launched today, and it makes A/B testing and fallback trivial.
3. **Governance for the Jevons effect.** Decision budgets or quotas per feature, cost dashboards, and a rule that every speculative question must have a consumer.
4. **Version pinning and threshold drift.** Pin `jev-1.13.0` rather than `jev-latest`, which moves silently. Recalibrate thresholds on every model upgrade through shadow traffic.
5. **Variable decision count.** Make decisions-per-message a parameter (3–15) instead of a fixed 7.
6. **Measurement provenance.** Record it for every latency number (vendor laptop vs Artificial Analysis probe location vs your own), and do not mix sources without a note.
7. **Residency.** Add data residency for EU and India DPDP. Jev's ZDR is enterprise-only, and Fable 5.1-class models require 30-day retention.
8. **On-device.** Mention on-device or edge models only for VAD/endpointing in voice, in one paragraph.
9. **Deliverable.** A one-page interview cheat sheet in the HTML view: a 30-second answer, a 2-minute answer, and a single latency-budget diagram.

---

## Concrete, checkable gate pass criteria

### Phase 1: Evidence (Critic-1, fact-checker)

- [ ] `research/evidence-ledger.md` has at least 40 rows. Every row has: ID, claim, value, unit, **conditions**, source URL, source type, access date, VENDOR flag, confidence tag, and counter-evidence/caveat. Conditions means comparator model and reasoning setting, region or probe location, state tokens, number of questions, percentile, and sequential vs concurrent.
- [ ] **Mandatory IDs are present:**
  - Jev: price; both rate limits; context limits; Choice/Score limits; "about 100 ms" and "70–500 ms" latency claims with conditions; the parallel-questions datapoint; the homepage example ($0.000081 / 0.114 s vs $0.013880 / 8.566 s); 193.6×/444.6× with "higher end" caveat; the 238× derivation; Doom ~$7/h at 10 q/s; reference-label method; "0% not empirical"; early access/waitlist; West Coast base; no SLA; ZDR enterprise-only; English-best.
  - LLMs: price (input, output, cache read, cache write, tokenizer note) for at least 3 tiers × 3 providers, **including Haiku 5.5**; TTFT p50 and output tok/s from Artificial Analysis, with date and probe location, for each model used; the provider capability matrix (structured outputs, logprobs, caching, regions, limits).
  - Infrastructure and workload: GPU $/hr for at least 2 SKUs; encoder throughput on CPU and GPU; support-message token-size distribution; voice pipeline components (ASR endpointing, TTS TTFA, speech-to-speech latency).
- [ ] The critic independently re-fetches at least 12 named high-impact claims (list them). Zero unresolved mismatches.
- [ ] 100% of VENDOR rows are ≤ [Likely], and marketing rows are ≤ [Guessing]. Every headline vendor claim has a counter-evidence entry.
- [ ] An "Independent coverage of Jev" section exists, with the search queries logged and "none found" stated explicitly if that is the result.
- [ ] No row lacks a URL. No URL is used that the agent did not actually fetch, and fetch failures are logged.

### Phase 2: Architecture (Critic-2, principal architect)

- [ ] `requirements.md` contains:
  - clarification questions and stated assumptions;
  - an FR/NFR table with numeric SLOs **and their measurement start/stop points**;
  - capacity math at 3 volumes (req/s, tokens/s, and headroom ratio against every vendor limit);
  - per-hop latency budgets for chat and voice that sum to the SLO.
- [ ] Each architecture (L1 as reference, L2, L2c, L3, C1a/b, J1, J2, H1, voice S2S) has:
  - a mermaid diagram that the critic has checked for syntax;
  - the critical path marked;
  - a per-hop latency table;
  - a token-flow table (state tokens vs question tokens; cached vs uncached);
  - a failure-mode table with a fallback and fail-open/fail-closed per decision;
  - rate-limit and deadline handling;
  - observability metrics;
  - an evaluation and rollout plan (golden set → shadow → canary → ramp, version pinning, threshold recalibration);
  - a security section (injection into the guardrail itself, PII to a third party).
- [ ] A fairness checklist is signed off item by item:
  - same decisions and rubrics;
  - same region assumptions;
  - caching applied wherever the provider supports it;
  - routing to deterministic handlers credited to **all** router architectures, not to Jev alone;
  - each designer's steelman attached.
- [ ] Every number cites a ledger ID or carries [Guessing] with a range.

### Phase 3: Model and harness (Critic-3, quant reviewer)

- [ ] `pytest` is green from a clean checkout, with one documented command.
- [ ] At least 3 golden-value tests are hand-computed by the critic (e.g., $ per message for J1, L2-cached and L1).
- [ ] All parameters live in one parameters file. An automated test asserts that every parameter has an existing ledger ID or a [Guessing] tag with a min/max range.
- [ ] Outputs include:
  - the comparator-ladder table;
  - the volume sweep;
  - the price-sensitivity run (1×/3×/10×);
  - a tornado chart;
  - a seeded Monte Carlo reporting p50/p95/p99;
  - the cascade sim's risk–coverage curve with a calibration-error sweep (Jev ECE treated as unknown and swept).
- [ ] The harness has:
  - real SDKs installed;
  - stub-server end-to-end tests passing;
  - request/response contract tests matching `api.md`;
  - a documentation URL on each SDK call;
  - a MOCK watermark test.
- [ ] C1 measured on a public dataset, with its results CSV committed and labelled "measured here".

### Phase 4: Study (Critic-4, interview panel)

- [ ] All of these sections are present:
  - 30-second answer;
  - 2-minute answer (300 words or fewer);
  - clarification questions;
  - back-of-envelope sheet;
  - latency-budget diagram;
  - comparator ladder;
  - where-each-wins matrix with at least 8 axes (labels, taxonomy churn, volume, latency budget, output type, modality, language, reasoning depth, state size, numeric content, residency);
  - hybrid recommendation;
  - failure modes;
  - evaluation and rollout;
  - build vs buy;
  - at least 5 measurable "what would change my mind" triggers;
  - 45-minute whiteboard script;
  - at least 10 likely follow-up questions;
  - glossary.
- [ ] Every number has a footnote to a ledger ID or model output.
- [ ] An overclaim grep ("444", "193", "238", "hallucinat", "type-safe", "calibrated", "×") finds the comparator and caveat within the same sentence or table row.
- [ ] Each of the three personas lists at least 5 findings, and each finding is marked resolved or rejected with a reason.

### Phase 5: Integration (final consistency critic)

- [ ] A number-consistency script extracts every tagged number in STUDY.md and the HTML view and compares it with the ledger and model CSVs. Zero mismatches beyond tolerance.
- [ ] `pytest` is green.
- [ ] Links are checked: HTTP 200, or the failure is logged.
- [ ] `README.md` has run instructions and an "untested live path" warning.
- [ ] Commit pushed to `ccr-b41820fd-rls3og` (the current branch is confirmed).
- [ ] The HTML view is published privately and renders charts in light and dark mode.
- [ ] The task list matches the final phases.

---

## Factual errors and overclaims found in PLAN v1

| # | Plan text | Problem | Correction / source |
|---|---|---|---|
| 1 | §1 "the comparison is fair to both sides" | The scenario is the vendor's showcased home turf: the intent-routing doc's example is customer-service routing, and there is an LLM-guardrails cookbook. | Say "Jev's best-case domain; we balance it with in-scenario losses" (fix 6). |
| 2 | §0.3 "Its real differentiators … latency, **price**, and calibrated confidence" | Against small-tier cached LLMs (Haiku 5.5-class at $0.10/$0.50, cache read about $0.01/MTok) the per-decision price gap is about 1–3.5×. Decisions are about 1–3% of total cost. | Price is a differentiator only against mid/frontier tiers (fix 1, Risk 1). |
| 3 | §0.1 "193.6× faster, 444.6× cheaper" (implicitly representative) | The vendor calls these "on the higher end of real world gains", and the comparator's reasoning settings are unstated. The homepage's single example implies **75× faster** (0.114 s vs 8.566 s) and **171× cheaper** ($0.000081 vs $0.013880). "238×" is a list-price ratio against Fable 5.1 ($10 / $0.042). | Never mix the example ratios with the headline ratios. Always name the comparator. |
| 4 | §0.1 "zero hallucinations" (as a claim to test) | The vendor says 0% is "not empirical", i.e. true by construction because output is restricted to valid options. The LLM hallucination figures come from OpenRouter with bias acknowledged. | Record it as definitional and not testable. The real risk is a *wrong valid option*. |
| 5 | §3 "Jev is US West Coast **only**" | The vendor says the service is "currently based" on the West Coast and the evals were run from laptops there. "Only" is an inference. | Tag [Likely]. Also note that the vendor's latency figures exclude cross-region RTT. |
| 6 | §2 L2 "logprobs for confidence" plus M2 "Anthropic structured outputs" | To the critic's knowledge, the Claude Messages API exposes no token logprobs. The two choices are inconsistent. | Fix 3; R2 to verify. |
| 7 | §2 J2 "(expected recommendation, to be proven)" | Pre-commitment, which invites confirmation bias. | Pre-registered hypotheses (fix 5). |
| 8 | §0.3 "LLM structured outputs … also guarantee schema validity" | Mostly right, but needs caveats: `stop_reason: refusal` (Haiku 5.5 safety classifiers have no server-side fallback), `max_tokens` truncation, and unsupported schema features. | Add the caveats. Measure the schema-valid **and** answered rate. |
| 9 | §0 Output primitives | Omits that Score accepts 2–10 levels and Choice allows ≤255 options, with larger cardinalities handled by a vendor two-stage process ("occasional slowdown"). | Add both for completeness. |
| 10 | §1 "Voice time-to-first-audio ≤ 800 ms" | No start point is defined, and the ASR, endpointing and TTS hops are missing. Jev is text-only, so the cascaded pipeline is forced. | Fix 8 and the voice architectures in fix 4. |
| 11 | §1 "Policy-eligibility checks" given to the decision model | Eligibility is usually about dates and amounts, which are documented Jev failure modes (math, dates, indirection). | Split it: Jev extracts the parts (Choice), and code does the comparison. Model this explicitly. |
| 12 | §1 "Input guardrail (… prompt injection …)" given to Jev without caveat | The vendor says state "is not treated as hostile by default" and adversarial content "can move the answer". | The guardrail itself is attackable. Add an injection test slice and a dedicated injection classifier as an alternative. |
| 13 | §0 Price | This is correct, but the vendor says "We can't prove it isn't subsidized". Output tokens are reported in `usage` (about 18–34) but not billed. | Add the price-risk sensitivity (fix 9f). |
| 14 | §0 "Jevons paradox (the name's origin)" | The blog says it is named after William Stanley Jevons and describes the demand-rebound idea, but never uses the phrase "Jevons paradox". | Reword: "named after W. S. Jevons; the vendor's stated bet is demand rebound". |
| 15 | Any later use of the parallel-questions "10.0× faster" | It compares one batched call with **13 sequential** calls (latencies summed). Concurrent separate calls would take about the same wall-clock time. The real win is cost: the 54K-character state is billed once. | Ledger condition: "vs sequential". |
| 16 | Task list #3/#4 | Still references "JEPA-way" and "selective decoding sim" from the superseded v0. | Update the tasks. |
| 17 | §0 "early access" | Correct (blog: early access, with a waitlist). | Add the implication: the user may not be able to get a key soon, so the harness live mode may be blocked. |

Claims in §0 verified as correct: text-only input; three primitives; $0.042/MTok input with free output; 64k request / 32k state-plus-longest-question context; 100K tok/s and 80 req/s, dynamically adjusted; RLCD with no customer fine-tuning; same weights for all accounts; jaggedness list (literal reading, math, dates, indirection, context rot, adversarial content, option order, generation).

---

## v2 re-check (2026-10-11)

**Verdict: PASS-WITH-FIXES.** The remaining edits are small. The lead can apply them directly; no further plan-critic loop is needed, and Phase 1 may start once they are in.

### Blocking fixes: all resolved
| Fix | v2 location | Status |
|---|---|---|
| 1 Comparator ladder | §2 (rungs a–f), §0.3 | Resolved |
| 2 Capacity as a gate | §1 volume sweep, P4, §4 Operations (deadlines, fallbacks, fail-open/fail-closed) | Resolved |
| 3 Capability matrix and LLM confidence method | Phase 1 row for R2; L2c (logprobs, or self-consistency at k× cost) | Resolved |
| 4 Missing architectures | L1b, L2m, L2c, L3, C1a/b, D1, V-S2S, V-casc; L1 relabelled | Resolved |
| 5 Pre-registration | §3, P1–P6 | Resolved; three rules need tightening (R1–R3 below) |
| 6 Unknown use case | §1 (assumed exemplar, clarification questions, defaults, parameter card, losses inside the scenario) | Resolved |
| 7 Secondary scenarios | §1 table | Resolved |
| 8 Latency | §4 | Resolved |
| 9 Tokens and charges | §4 | Resolved; one gap (R5) |
| 10 Quality | §4 | Resolved |
| 11 Harness | §6 (stub-server SDK tests, public data, MOCK/LAB tags, C1a measured) | Resolved |
| 12 Process | §5 (fresh-context critics, at most 2 FAIL loops, untrusted-data rule, neutral A3); task list checked and updated (#3/#4 no longer say JEPA; #7 Local Lab added) | Resolved |
| LL1–LL8 | §6, Phase 1/3 rows | Resolved |

### The two modifications
1. **One diagram per family plus per-architecture delta tables: acceptable, with two conditions.**
   - (a) There must be at least **four** diagrams: LLM-text, Jev-text, neutral, and **voice**. The voice diagram shows V-S2S and V-casc side by side, because their topologies differ structurally from the text paths.
   - (b) Every per-architecture delta table must still mark the **critical path** and include rows for per-hop latency, token flow (state vs question, cached vs uncached), failure/fallback, and deadline/rate-limit handling. The fairness checklist stays per architecture.
2. **C1b estimated from the literature: acceptable.**
   - C1b rows must record their conditions (dataset, model, hardware, label count) and be tagged at most [Likely].
   - P3 must rest on the measured C1a, never on C1b.

### Remaining required edits (small)
- **R1: P1 relies on a Jev p95 that does not exist.** The vendor gives only "about 100 ms for most queries" and "70–500 ms". Label P1's verdict "modelled under assumed distributions", and report the **flip threshold**: the Jev p95 and L2 p95 values at which the verdict reverses.
- **R2: P1-IN is unfair to the LLM side as written.** It compares Jev against *US-hosted* API LLMs only. Add an **in-region hosted API LLM** option, e.g. a cloud provider's India region or inference geography, verified in R3 for each provider. Otherwise the result is true by construction.
- **R3: P3 and P5 have methods but no falsification rules.**
  - **P3:** pre-specify N ∈ {5, 10, 20, 50, all} labels per intent. Make the primary comparator the **lab's best local zero-shot scorer on the same split**, with literature zero-shot numbers as secondary context only (different setups). State the rule: "falsified if C1a at N=20 is more than 2 points below that comparator".
  - **P5:** state a concrete crossover rule, e.g. "falsified if C1a or D1 beats J1 on cost at equal accuracy at ≤ X labels per intent and taxonomy churn ≥ Y%/month". Fix X and Y before Phase 3.
- **R4: Lab results must not stand in for production L3.** §2 calls L3 "also the Local Lab". Add: "L3 production latency and cost come from ledger GPU-serving benchmarks; lab results (Mac or CPU, tiny models) are illustrative only (LL5)."
- **R5: New token-model gap (R1/M1).** Jev's input usage appears to include a **fixed per-request overhead**, possibly a prompt template:
  - The `api.md` examples show **296–318 input tokens** for a state of about 10 words and one short question.
  - The parallel-questions cookbook implies only about 57 tokens per *additional* question. It billed about 11.8K tokens batched vs about 11.15K per single-question call, derived from the dollar figures.
  - The doc examples may be illustrative, so tag this [Likely, derived].
  - Model it as `tokens = overhead_per_request + state + Σ per_question`, with ranges. For short support messages the overhead can rival the message itself, and it affects Jev's position on the comparator ladder.
- **R6: Remove the inference about the user's location.** §1 says "India is flagged as likely for this user [Guessing, from repo commit timezone]". Do not carry a location inference from metadata into STUDY.md or the HTML view. Keep India in the region sweep as "a region of interest", and ask the user.

### Nothing else inconsistent found
Spot-checked and consistent: the v2 §0 facts against the docs; the phase table against the gate criteria; LL8 (start in parallel, ~30% cap); task list #1–#7.
