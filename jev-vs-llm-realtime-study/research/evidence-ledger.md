# Evidence ledger: index and verified summary

Phase 1 output. The ledger is split into three files by owner. This index is the entry point that later phases cite.

| File | Owner | Rows | ID prefix | Scope |
|---|---|---|---|---|
| [ledger-R1-jev.md](ledger-R1-jev.md) | R1 | 104 + new rows from Critic-1 | `JEV-` | Jev and TypeSafe: product facts, vendor claims with conditions, the vendor evals site, independent coverage, competing decision models |
| [ledger-R2-llm.md](ledger-R2-llm.md) | R2 | 84 | `LLM-` | LLM latency (Artificial Analysis), provider capability matrix (structured outputs, logprobs, caching, regions, limits, retention), voice components, calibration and position-bias literature |
| [ledger-R3-econ.md](ledger-R3-econ.md) | R3 | 84 | `ECO-` | Official price sheet (3 providers × 3 tiers plus decision APIs), voice pricing, GPU/CPU $/hour, throughput, workload sizes, inter-region round-trip time, human and labelling costs |
| [../lab/](../lab/) and `research/ledger-LOC-local.md`, if present | LAB-A | — | `LOC-` | Local inference servers: logprob and structured-output support |

**Verification:** [reviews/phase-1-factcheck-critic.md](../reviews/phase-1-factcheck-critic.md). Critic-1 independently re-fetched 61 claims: 47 confirmed, 8 partially confirmed, 3 contradicted, 3 unverifiable. Each ledger ends with a "Corrections log (Critic-1)" section recording the row-level fixes.

## Conventions (all ledgers)
- **Columns:** `ID | Claim | Value | Unit | Conditions | Source URL | Source type | Accessed | VENDOR | Confidence | Counter-evidence / caveat`.
- **VENDOR=Y** marks a vendor's own *performance or marketing* claim. Such rows are capped at [Likely], and marketing rows at [Guessing]. List prices and documented specs are VENDOR=N and may be [Certain].
- **Accessed:** every row was accessed on 2026-10-11, and every URL was actually fetched. Fetch failures are logged in each file's Method section.
- **Model IDs:** always exact (e.g. `gpt-5.6-sol` vs `gpt-6.1-sol`). "Luna", "Sol" and "Terra" on their own are ambiguous.

## Verified findings the study must reflect
Condensed from Critic-1's "Top findings". The cited IDs are the authoritative rows.

1. **Jev is a real product, adopted at scale, and four weeks old.**
   - Launched 2026-09-15.
   - About 1.03B decision requests a week on OpenRouter, roughly 70× the next decision model.
   - $870M Series A at a $7.5B valuation (2026-10-09).
2. **Decision models are a category now.** OpenAI Decisions, Cloudflare Clef and Clef-flash (open weights), Microsoft-Decision-1 and Liquid d1 all launched within four weeks, priced $0.038–0.24 per MTok of input with free output.
3. **Price is at parity at the small tier.**
   - Haiku 5.5 and GPT-6 Luna both list at $0.10 per MTok input, $0.50 output and $0.01 cached input.
   - A cached call making 7 decisions costs $0.000077–0.000091, against Jev's $0.000084.
   - Decisions are about 2% of the per-message bill.
4. **The headline multipliers depend on the comparator.**
   - The vendor's 193.6× / 444.6× are its own "higher end" figures.
   - The homepage example works out to 75× / 171× against GPT-5.6 Terra at default reasoning.
   - Against cheap tiers in practice the gain is about 3–8× cheaper and about 2× faster.
5. **Quality depends on the task.**
   - At the frontier level on bounded verification.
   - Last of 12 on LegalBench, and last of 17 on a 77-case BANKING77 pilot.
   - A fine-tuned 1B encoder beats Jev on safety at strict false-positive rates.
6. **Calibration does not transfer between tasks.** ECE ranges from about 0.01 to 0.11, and thresholds still need labels. Jev's "no labels" advantage applies only at cold start.
7. **Latency: Jev medians are 0.10–0.39 s, flat in question count. No p95 exists for Jev or for any LLM decision path,** so latency must be modelled.
8. **The fair LLM baseline is unmeasured.**
   - Haiku 5.5 thinks by default (9.7–13.4 s to the first answer token on Artificial Analysis).
   - With thinking off, proxy TTFT is 0.48–0.83 s.
   - Frontier models cannot turn reasoning off.
9. **Capacity binds on both sides.**
   - Jev: 80 requests/s and 100K tokens/s (about 50 msg/s).
   - Haiku 5.5 Scale tier: 10K RPM.
   - The Jev SDK's default timeouts break a 300 ms SLO.
10. **Residency.**
    - Jev processes in the US only, with no published SLA.
    - India to US-West round trip is 194–240 ms (P50).
    - In-India processing is limited to Vertex asia-south1, Azure South India Standard, and self-hosted open-weight models.
11. **LLM confidence mechanics.** Claude has no logprobs [Certain]. Logprob-based confidence needs GPT-6 Luna at effort `none` (top-20 cap) or a self-hosted model.
12. **Robustness.**
    - JevOut: natural context additions flip 61–73% of correct decisions, for Jev and other decision models alike.
    - Jev's docs list 9 known failure modes, including bias toward the first option.
    - A guardrail must never rely on one decision model alone.

## Known gaps (state them in the study, do not paper over them)
- No p95/p99 latency for either side.
- No Jev latency measured from India or the EU.
- No independent thinking-off TTFT for Haiku 5.5.
- No latency distribution published for any decision API.
- Jev's per-language accuracy is not established.

## Lead spot-checks (2026-10-11, after Critic-1)
- **openrouter.ai/rankings/decisions** was re-fetched by the lead and **confirmed**: "Usage data through Oct 10, 2026". Weekly requests: Jev 1.13 at 1.03B (+7%); GPT-6 Luna Decisions 14.5M; Perplexity Decider V1.1 27B 9.66M; Clef Flash 8.79M; Clef 6.08M; Mercury Decide 4.9M; Drex v1.5 4.46M; Microsoft-Decision-1 4.16M; d1 3.87M; Kev 4B 2.07M. R2 had logged a 404 for OpenRouter pages; the lead's fetch succeeded. Caveat: this covers OpenRouter traffic only.
- **Cloudflare Clef-flash docs** were re-fetched and **confirmed**:
  - "a fast 9B multimodal decision model", priced at $0.038 per M input tokens, with output not charged;
  - a 24,576-token context, 1–64 questions per request, and up to 4 images;
  - the open-weights status is not stated on the docs page itself: it links a Hugging Face licence page. Treat "open weights" as [Likely] until the licence is read.
