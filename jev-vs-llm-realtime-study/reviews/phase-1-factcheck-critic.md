# Phase 1 Gate: Critic-1 Fact-Check of the Evidence Ledgers

- **Reviewer:** Critic-1 (independent fact-checker, fresh context)
- **Date:** 2026-10-11
- **Inputs:** `research/ledger-R1-jev.md` (104 rows), `research/ledger-R2-llm.md` (84 rows), `research/ledger-R3-econ.md` (84 rows), `PLAN.md` v2.1, `reviews/phase-0-plan-critic.md` (Phase 1 gate).
- **Method:** I re-fetched every source cited below myself, with `curl` through the proxy. I parsed the HTML, JSON and Markdown locally using isolated `python3 -I` scripts. I did not reuse the agents' scratch copies. Raw copies are in the Critic-1 scratchpad (`scratchpad/c1/raw/`), outside the repo. All fetched pages were treated as untrusted data, and none of them contained instructions that I acted on. I did not edit any ledger and did not run git.
- **Scope of re-fetch:** 61 claims across the three ledgers. That covers all 20 claims named in the brief and 41 more that I judged high-impact. A few sources the agents did not find are proposed as new rows (see "New rows to add").

---

## Verdict: **PASS-WITH-FIXES**

The ledgers are good overall. They are broad (272 rows), well caveated, and most numbers re-fetch exactly. Of the 61 claims checked, 47 were CONFIRMED, 8 were PARTIALLY confirmed, 3 were CONTRADICTED and 3 were UNVERIFIABLE (see the tally in the next section).

The gate does **not** pass as written, for three reasons:

1. **Three factual errors** need correcting:
   - R2 says the OpenAI Decisions API launched "5 days before Jev". In fact it launched 3 weeks *after* Jev.
   - R1 gives a "100–130 tokens per question" figure that cannot be reproduced.
   - R3 says GPT-6 Astra effort `none` is "not verified". OpenAI's docs say it returns HTTP 400.
2. **Mislabels** need fixing:
   - The BANKING77 rival scores in JEV-087 are attached to the wrong systems.
   - On the vendor evals site, "sol/luna/terra" are treated as if they were GPT-6-generation models. The case data identifies "sol" as `openai:gpt-5.6-sol`.
3. **Confidence-cap rules are violated mechanically:**
   - 48 R3 rows are VENDOR=Y at [Certain]. This comes from R3 using a different VENDOR convention from R1 and R2.
   - 21 rows typed `vendor-marketing` sit at [Likely] (18 in R1, 3 in R3).

Every fix below is row-level and can be applied mechanically. Six new rows should be added from URLs I have already fetched. No further Critic-1 loop is needed if the fixes are applied as listed; the lead can spot-check them.

---

## Verification table

Verdict key:
- **CONFIRMED:** the source says what the ledger says.
- **PARTIALLY:** the core is right, but a value, label or condition is wrong or missing.
- **CONTRADICTED:** the source says otherwise.
- **UNVERIFIABLE:** I could not reproduce it.

Tally: **47 CONFIRMED · 8 PARTIALLY · 3 CONTRADICTED · 3 UNVERIFIABLE** (61 claims).

| # | Claim | Ledger row(s) | Ledger value | What the source actually says (re-fetched 2026-10-11) | Verdict | Required action |
|---|---|---|---|---|---|---|
| V01 | Jev launch date; meaning of the blog's "Oct 11, 2026" | JEV-021 (also PLAN §0, LLM-045) | 2026-09-15 | **Sources:**<ul><li>HN item 49717558: created 2026-09-15T19:25:03Z, links the launch post, 1,989 points, 518 comments.</li><li>Wikipedia: released 15 September 2026.</li><li>The Register: published Wed 16 Sep 2026, "on Tuesday".</li><li>TechCrunch (2026-10-09): "September 15 release".</li></ul>**The blog's date:** the launch post shows no visible article date. "Oct 11, 2026" is Framer's site-deploy stamp: the HTML comment `<!-- Published Oct 11, 2026, 5:54 AM UTC -->` plus `data-framer-page-optimized-at="2026-10-11T05:54:44Z"`. The same comment appears on the homepage. | CONFIRMED (R1). PLAN §0 and LLM-045 are wrong | Add the deploy-stamp explanation and the TechCrunch URL to JEV-021. Fix PLAN §0 and LLM-045 (see corrections) |
| V02 | Series A | JEV-078 | $870M at $7.5B, a16z-led, 2026-10-09 | **Sources:**<ul><li>Vendor post: "$870 million at a $7.5B valuation, with Martin Casado joining the board". Led by a16z, with Sequoia and DCVC.</li><li>TechCrunch, 2:41 PM PDT, October 9, 2026: same figures.</li><li>a16z post dated October 9, 2026.</li><li>HN item 50023450 created 2026-10-09T17:02Z.</li></ul> | CONFIRMED | Retype the source (see R1 corrections) |
| V03 | Price and output billing | JEV-003, JEV-004 | $0.042/MTok input; output free | `models.md`: "\$42 / \$0.042" per Btok/Mtok; "Charged per input token. Output tokens are free." OpenRouter lists `typesafe/jev-1.13` at $0.042 in / $0 out. | CONFIRMED | — |
| V04 | Rate limits | JEV-005, JEV-006 | 100K tok/s; 80 req/s; dynamic | `models.md`: "100K tokens per second / 80 requests per second". The warning says limits "can change without notice", and higher limits come on custom/enterprise plans. | CONFIRMED | — |
| V05 | Context limits | JEV-007 | 64k per request; 32k for state plus the longest question | Verbatim in `models.md`. | CONFIRMED | — |
| V06 | Homepage example | JEV-025, JEV-026 | $0.000081 / 0.114 s vs $0.013880 / 8.566 s; 75.1× / 171.4×; about 1,929 tokens | Homepage text: "Cost $0.000081 · Completed in 0.114s · LLMs · Cost $0.013880 · Completed in 8.566s". The arithmetic re-checks: 75.14×, 171.36×, 1,928.6 tokens. | CONFIRMED | — |
| V07 | Comparator and reasoning setting for the example | JEV-025, JEV-041, JEV-092 | GPT-5.6 Terra at default reasoning | **The homepage labels the comparator only "LLMs".** The blog's side-by-side Nuance section says: "We used GPT-5.6 Terra with default reasoning for this example". The Register ties the homepage demo to Terra (0.114 s vs 8.566 s). | CONFIRMED (attribution comes via the blog and the press) | Add to JEV-025: "homepage names no comparator; Terra/default from the blog Nuance section and The Register" |
| V08 | "Higher end" caveat | JEV-033 | Verbatim | Blog: "This is where the claims of 193.6x faster, 444.6x cheaper on our home page comes from, and we expect that these are on the higher end of real world gains." | CONFIRMED | — |
| V09 | 193.6× / 444.6× cannot be reproduced from the evals site | JEV-033, JEV-043 | No single plotted model reproduces either figure | It is true that no **single** comparator reproduces both. However, **each figure fits a different plotted point within Jev's rounding:**<ul><li>Time: Sonnet 5 at 78.1 s ÷ 0.403 s = 193.6×. Jev is displayed as 0.4 s, so any value from 0.35 to 0.45 s is consistent. DS v4 pro (86.5 s) also falls inside that window.</li><li>Cost: Opus 5 at $0.1761 ÷ $0.000396 = 444.6×. Jev is displayed as $0.0004.</li></ul>The vendor text names no comparator. Vals' "average of GPT-6 Astra and Claude Fable 5.1" is Vals' own reading. Astra and Fable are the reference-label models and are not plotted. | PARTIALLY | Reword the JEV-033 and JEV-043 caveats (see R1 corrections) |
| V10 | Evals overview values and comparator identity | JEV-042, JEV-044–047 | Jev 67.8% / $0.0004 / 0.4 s; Sol 74.1%; Luna 66.8%; Terra 67.9% … | All overview values match exactly. **But the case-data files identify "sol" as `openai:gpt-5.6-sol`** (20 occurrences). The "luna" and "terra" labels carry no version; they are most likely the GPT-5.6 generation. Opus is `anthropic:claude-opus-5`, Jev is `typesafe:v13_snowy_elephant`, and LLM costs are `estimated_uncached`. | PARTIALLY | Re-label the comparators in JEV-042/045/046/047 and in R1 takeaways 2 and 4 |
| V11 | Vals: claim verification | JEV-083 | 0.975 at $0.02/1k; ties GPT-6 Astra, GPT-6.1 Sol and GPT-6 Luna (390/400); 1/498 of Astra's cost | Verbatim (Vals AI, Connor Frank, 10/06/2026). GPT-6 Luna matches at $0.08/1k. | CONFIRMED | — |
| V12 | Vals: LegalBench, ECE, error budget | JEV-083 | Last of 12; class-balanced 0.730 vs Terra 0.932; ECE 0.011 / 0.108; 95% coverage at 1.6% error | Verbatim. Jev is "a hair behind Haiku 4.5 (0.732)". | CONFIRMED | — |
| V13 | Vals: latency 0.10 → 0.12 s for 1 → 64 judgments | JEV-028 | Median of 3; batched; sequential sweep; residential connection | Confirmed, but the conditions are incomplete:<ul><li>The probe location is not stated ("one machine on a residential connection").</li><li>The document size is not stated ("one long document").</li><li>The load tests ran 8 Jev requests in flight against 4 per LLM.</li><li>LLM reasoning settings are not stated in the post.</li><li>The 64-judgment cell was added after preregistration.</li><li>The isolated single-call median is 0.10 s, and 0.11 s under load.</li></ul> | PARTIALLY | Add the missing conditions to JEV-028 |
| V14 | openjev-sglang BoolQ | JEV-084 | Accuracy 91.56%; Brier 0.0640; P(yes) ECE 3.53%; n = 3,270 | The report at the pinned commit matches exactly. Jev was called via OpenRouter as `typesafe/jev-1.13-20260917`; cost $0.0595; bootstrap clusters 2,938 passages. **What the project is:** per its README, "A server implementing the TypeSafe/Jev HTTP API with Qwen3.6-35B-A3B on SGLang" (deployed on Modal B200). It is an **API-compatible open re-implementation, not a proxy**. The report compares that re-implementation ("OpenJev", 89.45%, ECE 4.64%) with the **real Jev**, which won. | CONFIRMED | Add the identity and independence note to JEV-084 |
| V15 | openjev MMLU-Pro | JEV-086 | Jev 82.9% (829/1,000); math 87.4% | Verbatim. The report calls itself "a service comparison, not an isolated model ablation". | CONFIRMED | — |
| V16 | S. Anand BANKING77 pilot | JEV-087, JEV-030 | Jev 75.3%, last of 17; confidence 87.4%; ECE 0.138; Brier 0.171; AUROC 0.811; $0.07/1k; 0.39 s. Rivals include "GPT-6 Luna via OpenAI Decisions 77.9%" | Jev's values match (updated 8 October 2026; n = 77, one frozen case per class). **Rival mislabel:**<ul><li>OpenAI Decisions (GPT-6 Luna via `/v1/decisions`): 79.2% (61/77), $0.10/1k, 0.31 s.</li><li>GPT-6 Luna via chat: 77.9% (60/77), $0.06/1k, 1.07 s.</li></ul>**Omitted from the row:** the top two systems, Clef 96.1% and Clef-flash 94.8%. **Method:** chat LLMs gave verbalized 0–100 confidence, while decision models gave the chosen-label probability, so the ECE values are not like-for-like. Reasoning was disabled for GPT-5.6 Luna, GPT-6 Luna, GPT-5.6 Sol and DeepSeek, and set to low for the others. The machine's location is not stated. **Source quality:** a personal GitHub Pages pilot that publishes its cases, raw results and runner. The author calls it "directional". | PARTIALLY | Fix the rival list and add the method note to JEV-087 |
| V17 | JevBench reference row for Jev | JEV-031, JEV-088 | 0.24 s; $0.032/1k; Intelligence 63.6, Calibration 90.6, Capability 77.1; board v1.7.44, 2026-10-10 | Verbatim. Quyet-1.0-Large scores 73.4 / 81.7 at $0.045. The page says it is run "independently of TypeSafe AI" and covers 148 open-weight systems plus 27 API systems. | CONFIRMED | Add "median; probe location not stated" to JEV-031 |
| V18 | Independent Jev latency medians of 0.10–0.39 s, and who measured them | R1 takeaway 3 | 0.10 (Vals), 0.24 (JevBench), 0.39 (Anand) | The values are confirmed. **No probe location is stated in any of the three sources. All are medians, none are p95.** The 0.39 s figure includes the OpenRouter hop and a 77-option prompt of about 1,670 tokens. No source gives a state size except Anand (implied by the 77-option prompt). | PARTIALLY | Add "probe location unstated; medians only" to takeaway 3 |
| V19 | OpenAI Decisions API: what it is | LLM-044 | `/v1/decisions`, public beta, gpt-6-luna only, predicate/choice/score, $0.10/MTok input only, US/EU residency, ZDR/HIPAA, "about 10x faster" | All confirmed in the official guide (`guides/decisions.md`). It says: "You pay only for input tokens: there are no cache-read, cache-write, or output-token charges". It gives no calibration claim, advises setting thresholds from labelled examples, and states no option limit. | CONFIRMED | Add independent datapoints (see R2 corrections) |
| V20 | Decisions API public beta on 2026-10-06 | LLM-045 | 2026-10-06 (press) | The **official changelog** says: "Oct 6 · Released the Decisions API in beta with `gpt-6-luna`." The press article (letsdatascience, 2026-10-07) agrees. JevBench says "opened on 6 Oct 2026". | CONFIRMED | Cite the official changelog as the primary source and raise the date to [Certain] |
| V21 | Decisions API relative to Jev's launch | LLM-045 caveat; R2 takeaway 2 | "Launched 5 days before Jev's announcement (2026-10-11)"; "undercuts … 'first System One model' framing" | Jev launched on 2026-09-15 (V01). **The Decisions API came 3 weeks after Jev**, in a wave of copycat products (see V22–V24). | CONTRADICTED | Rewrite (see R2 corrections) |
| V22 | Microsoft-Decision-1 | JEV-089 | On Azure Foundry; Qwen3.5-9B base; 459 ms native median | **Sources:**<ul><li>Official Microsoft blog (commandline.microsoft.com, 2026.10.09): available in Microsoft Foundry and through OpenRouter. Vendor claims: highest accuracy on 36 benchmarks, fastest measured.</li><li>OpenRouter: post-trained from Qwen3.5-9B; $0.042 in / $0 out; 32,768-token context.</li><li>JevBench: "native Azure Foundry measurement … Native median latency is 459 ms on the 124-request speed subset". Capability 70.78 and Calibration 84.40, both **below Jev's 77.1 / 90.6**.</li><li>The Register (2026-10-10): Microsoft claims it is 2.8× faster than Jev.</li></ul> | CONFIRMED | Add the official URL and the JevBench score (see the R1 new rows) |
| V23 | Liquid d1 | JEV-089 | $0.04/MTok input | **Sources:**<ul><li>Liquid AI blog (OCT 5, 2026): decision model with text and images; vendor says "a text decision takes 200 to 300 ms".</li><li>OpenRouter: `liquid/d1` at $0.04 in / $0 out; 65,536-token context; "served as a System One endpoint" using the same `/v1/systemone` schema.</li></ul> | CONFIRMED | Add the official URL |
| V24 | Cloudflare Clef / Clef-flash | JEV-089 | Named only | **Cloudflare Workers AI docs:**<ul><li>Clef: "a 27B multimodal decision model", $0.24 per MTok input, 65,536-token context.</li><li>Clef-flash: "a fast 9B" model at **$0.038 per MTok input, which is below Jev's $0.042**, 24,576-token context.</li><li>Neither charges for output tokens.</li></ul>**The Register (2026-10-01):** "open weight and runnable locally", built on post-trained Qwen3.8-27B / Qwen3.5-9B, served on edge GPUs. Cloudflare self-reports beating Jev on 3 of TypeSafe's 4 workflows; this has not been reproduced. | CONFIRMED (and more significant than R1 records) | Add a new row (see the R1 new rows) |
| V25 | JevBench exists; "several rivals beat Jev on JevBench and BANKING77 at similar cost" | JEV-088, JEV-089, R1 takeaway 5 | As stated | JevBench exists as described. **Open-weight** rows beat Jev (for example Quyet 81.7 vs 77.1). However, the **hosted API** rivals score below Jev on JevBench: Microsoft-Decision-1 at 70.78, and OpenAI Decisions at a preliminary 68.8 on 300 public items. On BANKING77, Clef, Clef-flash, Mercury Decide and d1 do beat Jev (n = 77). | PARTIALLY | Add this nuance to takeaway 5 and JEV-089 |
| V26 | Claude Messages API has no logprobs | LLM-021 | No parameter or field | `messages/create.md` contains 0 occurrences of "logprob". | CONFIRMED | — |
| V27 | Claude OpenAI-compatibility layer | LLM-022 | `logprobs` and `top_logprobs` ignored; response `logprobs` "Always empty"; `n` must be 1 | Verbatim in `openai-sdk.md`. Also: temperature below 1 returns 400 on Claude 4.7+ models. | CONFIRMED | — |
| V28 | Haiku 5.5 prices | ECO-001, ECO-002, LLM-028 | ≤100K: 0.10 / 0.50 / cache read 0.01 / writes 0.125 and 0.20. >100K: 0.50 / 2.50 / 0.05 | Verbatim in `pricing.md`. A request over the threshold pays the higher rates on all its tokens. | CONFIRMED | — |
| V29 | GPT-6 Luna price | ECO-013, LLM-038 | 0.10 / cached 0.01 / write 0.125 / 0.50 | Verbatim in `pricing.md`. Long context is 0.20 / 0.02 / 0.25 / 0.75. | CONFIRMED | — |
| V30 | Sonnet 5.5 cache read | ECO-004, LLM-028 | $0.10 (0.05×); the seed said $0.20 | `pricing.md`: "$0.10 / MTok²", where footnote 2 reads "0.05x the base input price". | CONFIRMED (the seed fact is wrong) | — |
| V31 | Gemini 3.5 Flash-Lite price | ECO-021, LLM-047 | 0.30 / 2.50 | `pricing.md.txt`: input $0.30, output $2.50 (including thinking), cache $0.03 plus $1.00 per MTok-hour. | CONFIRMED | — |
| V32 | Artificial Analysis (AA): Haiku 4.5 TTFT | LLM-007 | 0.48 s; 86.6 tok/s; peer median 1.16 s | Live page now shows 0.48 s; 86.1 tok/s; peer median 1.14 s. These are rolling 72-hour P50s. | CONFIRMED (minor drift) | Note "rolling; re-snapshot before Phase 4" |
| V33 | AA: GPT-6 Luna non-reasoning | LLM-011 | 0.83 s (leaderboard) / 0.79 s (model page) | The leaderboard and model page now both show 0.83 s; 118–126 tok/s; peer median 1.78 s. | CONFIRMED (drift) | Same note |
| V34 | AA: Haiku 5.5 low effort; Terra non-reasoning | LLM-003, LLM-015 | 9.72 s first answer chunk / E2E 12.53; Terra 0.77 s / E2E 6.29 | Leaderboard rows match exactly. AA lists no non-reasoning Haiku 5.5 (the page says "A non-reasoning variant may also exist"). | CONFIRMED | — |
| V35 | AA probe conditions | LLM-001 | 10k input (website default), P50 over 72 h, `us-central1-a`, tested 8× per day | Methodology page: primary server is a GCP `us-central1-a` VM; P50 over the past 72 h; the 10k workload is "default benchmark on our website" with "at least 1,500 answer tokens"; TTFT "includes network latency". | CONFIRMED | — |
| V36 | India → US-West RTT | ECO-066, ECO-071, R3 takeaway 5 | 211–240 ms median | **Azure** (P50, 30 days ending 2026-07-30; Azure backbone):<ul><li>Central India → West US 2: 211 ms.</li><li>Jio India West → West US 2: 231 ms.</li><li>**South India → West US 2: 194 ms** (omitted from the ledger).</li></ul>**CloudPing** (P50, 1-day rolling):<ul><li>ap-south-1 ↔ us-west-2: 232 / 237 ms today (R3 recorded 232.10 / 239.77).</li><li>ap-south-2 ↔ us-west-2: 216 / 224 ms.</li></ul>All of these are datacenter-to-datacenter P50s with no end-user last mile. | PARTIALLY | Change the range to **194–240 ms P50 (datacenter backbone)** |
| V37 | In-India inference availability | LLM-031, LLM-034, LLM-043, LLM-053 | Claude and OpenAI first-party: none; Bedrock Mumbai is Global only; Vertex `asia-south1` only for gemini-3.5-flash / 2.5-flash | **Sources:**<ul><li>Anthropic: `inference_geo` is "global" or "us" only.</li><li>Bedrock: `ap-south-1` and `ap-south-2` are "Global" only; structured outputs are listed under "Features not supported".</li><li>OpenAI `your-data`: India has regional storage Yes, regional processing No.</li><li>The Google data-residency table's India (`asia-south1`) column is ticked only for gemini-3.5-flash, gemini-2.5-flash and text-embedding-005.</li></ul> | CONFIRMED | — |
| V38 | Jev status page | JEV-017 | 99.838%; incidents on 09-21, 09-23 and 09-28; "≈3.5 h downtime per 90 days" | The 99.838% figure and the three incidents (2, 12 and 11 minutes) are confirmed (page re-read at 6:35am UTC). **The derived "≈3.5 h per 90 days" is not supported.** The listed API incidents total 25 minutes. The service launched on 2026-09-15, about 26 days ago. The window behind the percentage is not defined. | PARTIALLY | Replace the derived sentence |
| V39 | Regions; no SLA | JEV-016, JEV-018 | `api.us` and `api.us-west-2`; no SLA found | The status page lists `api.us.typesafe.ai` ("served from the closest US region") and `api.us-west-2.typesafe.ai`. The enterprise page and its FAQ module contain 0 matches for "SLA", "service level" or "uptime". | CONFIRMED | — |
| V40 | Waitlist bypass | JEV-020 | OpenRouter; MotherDuck; "an HN user reports a Vercel listing" | **Sources:**<ul><li>OpenRouter: `typesafe/jev-1.13` page.</li><li>MotherDuck: `prompt_jev` docs (preview; requests are processed "by TypeSafe's servers in the United States").</li><li>**Vercel AI Gateway officially lists `typesafe-ai/jev`** (with `zdr: "some"`), in the `ai-gateway.vercel.sh/v1/models` JSON.</li></ul>The Vercel claim is stronger than the ledger says. | CONFIRMED | Replace the HN hearsay with the official Vercel URL |
| V41 | Fixed per-request overhead of about 250–300 tokens | JEV-050, JEV-054 | ≈280 derived; MotherDuck says ≈250 | `api.md` usage examples: 296, 307, 318 and 304 input tokens for a 46-character state and one short question. MotherDuck: "a fixed overhead of about 250 input tokens per request". | CONFIRMED | — |
| V42 | "57 tokens per question" (GDPR cookbook) | JEV-051 | (11,833 − 11,154) / 12 = 56.6 | The cookbook's `PRICE = (0.042, 0.00)` (jev-1.12, "as of 2026-09") gives $0.000497 → 11,833 tokens, and $0.006090 / 13 → 11,154 tokens. The arithmetic holds. | CONFIRMED | Change "as of 2026-08" to "2026-08/09" in JEV-003 |
| V43 | "About 100–130 tokens per question" in Customer Service cases | JEV-051, R1 takeaway 6 | 100–130 (upper bound, including the state share) | Recomputed from the 5 Jev example cases at $0.042/MTok: 2,077–4,106 tokens, 14–26 questions and 2–5 calls per case. **Gross tokens per question are 148–189. Net of about 250 tokens of overhead plus the state on each call, they are about 75–95** (assuming 4 characters per token for the state). Neither figure matches 100–130. R1 also contradicts itself on a 77-option Choice: about 1,670 tokens in JEV-051 but "1,300+" in the takeaways. | CONTRADICTED | Replace the figure (see R1 corrections) |
| V44 | Jaggedness failure modes | JEV-068–076 | 9 | `model-jaggedness/jev-1.13.md`: numbered table 1–9, "Last reviewed 2026-10-02". | CONFIRMED (9, not 8) | — |
| V45 | Claude tokenizer | ECO-007, LLM-036 | "approximately 30%" more tokens | `pricing.md`: "Claude 4.7 and later models … produces approximately 30% more tokens for the same text." This is relative to the older Claude tokenizer. | CONFIRMED | — |
| V46 | Haiku 5.5 thinking rules | LLM-026, ECO-010 | On by default; `disabled` allowed at effort ≤ high; 400 at xhigh/max; default effort medium | `thinking.md`, line 55 table and line 472; `effort.md`: "Claude Opus 5.5 and Claude Haiku 5.5 default to medium". Also confirmed: "With thinking off, the model can skip a tool call it needs when you also request JSON output." | CONFIRMED | — |
| V47 | GPT-6 Astra and effort `none` | LLM-027 vs ECO-020, R3 bullet 3 | R2: `none` → 400. R3: "not verified for Astra" | OpenAI reasoning guide: "GPT-6 Astra does not support `none` reasoning … returns HTTP 400". | CONTRADICTED (R3) | Fix R3 |
| V48 | Vertex `asia-south1` availability | LLM-053 vs ECO-012, R3 takeaway 5, R3 contradiction 6 | R2: verified. R3: "unverified" | Same as V37. R2 is right and R3 is out of date. | CONFIRMED (R2) | Update R3 to cite LLM-053 |
| V49 | Suraj Phanindra load test | JEV-032, JEV-091 | $0.048 per 1k correct on-time decisions; Haiku $24.48; 45× → 3.3× with 32 slots; 92.2% vs 93.6% | Verbatim (2026-09-21). The comparators were GPT-5.6 Luna, Haiku 4.5 and two DeepSeek models. **Not noted in the ledger: "Luna and Haiku 0%" cached.** | CONFIRMED | Add "LLMs ran with 0% cache hits" |
| V50 | Jack & Jill case study | JEV-085 | $0.755 → $0.092 per 1k; 20.3 → 10.3 s; 93.9% → 94.6%; AUC 0.924 → 0.933; 150 roles | Verbatim. Offline test; replaced Gemini 3.1 Flash Lite. | CONFIRMED | Downgrade the confidence (see R1 corrections) |
| V51 | SDK defaults | JEV-098, JEV-099 | 10 s timeout; 2 retries; 0.5 → 5 s backoff; statuses 408/429/5xx; 30 s total budget | `constants.md`: `DEFAULT_TIMEOUT = 10.0`. `retries.md`: `max_retries=2`, `backoff_initial=0.5`, `backoff_max=5.0`, `backoff_jitter=0.25`, statuses `{408, 429, *range(500, 600)}`, `timeout=30.0`. | CONFIRMED | — |
| V52 | Enterprise FAQ | JEV-015 | US-only processing; hosted API only; no BAA; ZDR | Framer module text: "All data is currently processed in the US." "Jev is currently available only through our hosted API." "We don't currently support HIPAA compliance or sign … BAAs." "Zero data retention is available to companies on request." | CONFIRMED | — |
| V53 | Small-tier rate limits and caching | LLM-029, LLM-030, LLM-038 | Haiku 5.5: 1K/2M, 5K/5M, 10K/10M. Luna: 5K/2M, 10K/10M, 30K/180M. Claude cache reads not counted toward ITPM | Verbatim in `rate-limits.md` and `gpt-6-luna.md`. "`cache_read_input_tokens` ✗ Do NOT count toward ITPM for most models." | CONFIRMED | — |
| V54 | Haiku 5.5 release date | LLM-036, ECO-001 | 2026-10-07 | "Latest. Released October 7, 2026." This is the day after Vals published, which explains why every independent Jev study uses Haiku 4.5. | CONFIRMED | Add that explanation to the R1 takeaway |
| V55 | arXiv 2609.29429 | JEV-093 | Median AUROC 0.886 zero-shot; 44 benchmarks | Abstract verbatim (Guo et al., 2026/09/24). It also claims Jev "costs 63x less than LLM-judge scorers". | CONFIRMED | — |
| V56 | Parallel-questions cookbook | JEV-027 | 12.2× / 10.0×; "faster" sums 13 sequential calls | Verbatim, including "Fire them concurrently and the gap shrinks, but the 13x token cost stays." | CONFIRMED | — |
| V57 | Consistency cookbook latency | JEV-024 | 114 ms mean of 15; LLMs in a 16-way pool | Verbatim: `ThreadPoolExecutor(max_workers=16)`, "mean round-trip latency of 114ms", run on jev-latest on 2026-09-11. | CONFIRMED | — |
| V58 | Claude on Bedrock: Mumbai and structured outputs | LLM-025, LLM-034, ECO-012 | Global endpoint only; no structured outputs | Verbatim (V37). | CONFIRMED | — |
| V59 | "3 to 329 seconds" for frontier LLMs | JEV-029, LLM-019, LLM-020 | Quote verified; range not reproducible | The quote is confirmed in the blog. The mirror site now embeds AA data server-side (`aa-models-payload`, `refreshedAt` 2026-10-11T06:41Z), but the launch-day snapshot behind "3–329 s" cannot be reproduced. | UNVERIFIABLE | Keep at [Guessing]; update the "loads dynamically" note |
| V60 | Human turn-taking gap (Stivers 2009, PNAS) | LLM-068 | Mean +208 ms; mode 0 | Not re-fetched by me. R2 got HTTP 403 and read the content from a search-engine excerpt. | UNVERIFIABLE | Downgrade [Certain] → [Likely] and note "via search excerpt" |
| V61 | "No per-language accuracy published or found independently" | JEV-013 | None found | JevBench has a **Languages** view covering 23 languages (including Hindi) for 199 systems. The values are client-rendered, so I could not confirm whether Jev's row is populated. | UNVERIFIABLE (a lead R1 missed) | Fetch the JevBench data JSON/CSV before saying "none found" |

---

## Required corrections (row-level, mechanical)

### R1 (`ledger-R1-jev.md`)

**Factual and label fixes**

| Row | Field | Change |
|---|---|---|
| JEV-021 | Counter-evidence | Append: "The vendor post shows no article date. The 'Oct 11, 2026' seen on the page is Framer's site-deploy stamp (HTML comment `Published Oct 11, 2026, 5:54 AM UTC`; `data-framer-page-optimized-at=2026-10-11T05:54Z`), which also appears on the homepage. TechCrunch 2026-10-09: 'September 15 release'." Add the TechCrunch URL to Source. |
| JEV-017 | Counter-evidence | Delete "99.838% is about 3.5 h of downtime per 90 days". Replace with: "The window is undefined: the listed API incidents total 25 min (2 + 12 + 11), and the service launched 2026-09-15. Treat 99.838% as an operator-reported figure, not a measured availability." |
| JEV-025 | Conditions | Prepend: "The homepage labels the comparator only 'LLMs'. Terra at default reasoning comes from the blog's side-by-side Nuance section; The Register ties the homepage demo to Terra." |
| JEV-028 | Conditions | Append: "Probe location not stated (one machine, residential connection). Document token count not stated. LLM reasoning settings not stated. Load tests: 8 Jev requests in flight vs 4 per LLM. 64-judgment cell added after preregistration. Isolated single-call median 0.10 s; 0.11 s under load." |
| JEV-030 | Conditions | Append: "Includes the OpenRouter Decisions hop. About 1,670 input tokens per request (77 options with descriptions). Median of n = 77." |
| JEV-031 | Unit / Conditions | Unit → "s, median". Conditions append: "Probe location not stated." |
| JEV-033 | Counter-evidence | Replace "Vals reads it as …" with: "The vendor names no comparator. Vals reads it as 'than the average of GPT-6 Astra and Claude Fable 5.1'; those are the reference-label models, not plotted points." |
| JEV-042 | Conditions | Append: "Case data identifies 'sol' as `openai:gpt-5.6-sol`. The 'luna' and 'terra' labels are unversioned and most likely GPT-5.6 generation. Do not equate them with GPT-6 Luna / GPT-6.1 Sol. Run from the vendor's West Coast laptops (blog)." |
| JEV-043 | Counter-evidence | Replace the first sentence with: "No single comparator reproduces both multipliers. Each fits a different plotted point within Jev's rounding: Sonnet 5 time 78.1 s ÷ 0.403 s = 193.6× (DS v4 pro, 86.5 s, also fits); Opus 5 cost $0.1761 ÷ $0.000396 = 444.6×." |
| JEV-045, JEV-046, JEV-047 | Value / caveat | Replace "Luna", "Sol" and "Terra" with "GPT-5.6-gen 'luna'", "GPT-5.6 Sol" and "GPT-5.6-gen 'terra'". |
| JEV-051 | Value | Replace "About 100–130 per question (upper bound, including state share) in evals Customer Service cases" with: "Customer Service examples (5 cases): gross 148–189 tokens per question; net of about 250 overhead plus the state on each call, about 75–95 per question (assumes 4 characters per token for the state)." |
| JEV-084 | Counter-evidence | Append: "openjev-sglang is an open-source server implementing the TypeSafe `/v1/systemone` API on Qwen3.6-35B-A3B (SGLang, Modal B200). The report compares that re-implementation ('OpenJev': 89.45%, ECE 4.64%) with the real Jev called via OpenRouter, so the Jev numbers are real-Jev measurements by the author of a competing open implementation. Single author, not peer-reviewed. The method is documented (passage-clustered bootstrap, manifests, completion required)." |
| JEV-087 | Counter-evidence | Replace the rival list with: "Clef 96.1% ($0.44/1k, 0.75 s); Clef-flash 94.8% ($0.17/1k, 0.49 s); Mercury Decide 92.2% (free, 0.46 s); Liquid d1 88.3% ($0.02/1k); Kev 4B 87.0%; **OpenAI Decisions (GPT-6 Luna) 79.2% (61/77), $0.10/1k, 0.31 s; GPT-6 Luna via chat 77.9% (60/77), $0.06/1k, 1.07 s**." Append: "Chat LLMs report verbalized 0–100 confidence and decision models report the chosen-label probability, so ECE is not like-for-like across the two groups. Reasoning was off for the Lunas, GPT-5.6 Sol and DeepSeek, and low for the others." |
| JEV-089 | Source / caveat | Add the URLs listed under "New rows to add" (Microsoft, Liquid, Cloudflare, OpenRouter rankings). Append: "On JevBench the hosted rivals score below Jev (Microsoft-Decision-1 Capability 70.78; OpenAI Decisions preliminary 68.8 vs Jev 77.1). The open-weight rows above Jev are self-hosted." Delete "R2 must verify … Microsoft-Decision-1" (now verified). |
| JEV-090 | VENDOR / caveat | VENDOR N → **Y** (MotherDuck sells `prompt_jev`). Append: "The enterprise-page tile also claims '48× faster' vs Terra." |
| JEV-091 | Counter-evidence | Append: "Luna and Haiku ran with 0% cache hits (author's statement)." |
| JEV-013 | Counter-evidence | Replace "or found independently" with: "JevBench publishes a Languages view (23 languages, including Hindi); Jev's row has not yet been extracted." |
| JEV-003 | Counter-evidence | "as of 2026-08" → "as of 2026-08/09 (varies by cookbook; the parallel-questions cookbook says 2026-09)". |
| JEV-053, JEV-061 | Conditions | Replace "—" with "Any request; vendor doc statement, no measurement". |

**Confidence-cap compliance (gate rule: marketing ≤ [Guessing])**

Option A, recommended because it keeps information: add two source types to the Method section, then retype the rows below.
- `vendor-benchmark`: a vendor-run evaluation with published data. VENDOR=Y, cap [Likely].
- `vendor-disclosure`: a verbatim vendor statement about its own method or caveats. VENDOR=Y, cap [Likely].

| Row(s) | Action |
|---|---|
| JEV-042, JEV-044, JEV-045, JEV-046, JEV-047, JEV-048 | Source type → `vendor-benchmark`; keep [Likely] |
| JEV-019, JEV-020, JEV-040, JEV-041, JEV-081 | Source type → `vendor-disclosure`; keep [Likely] |
| JEV-078 | Source type → `press` (TechCrunch primary; the vendor post and a16z corroborate); VENDOR → N; keep [Likely] |
| JEV-009, JEV-022, JEV-025, JEV-036, JEV-085, JEV-090 | Confidence [Likely] → **[Guessing]** |

Option B: set all 18 rows to [Guessing].

**Takeaway edits**

- **Takeaway 2:** "vendor workflows 67.8% vs Sol 74.1%" → "vs GPT-5.6 Sol 74.1%".
- **Takeaway 3:** add "probe locations are unstated in all three sources; medians only".
- **Takeaway 4:** add "Haiku 5.5 was released 2026-10-07, after every independent study".
- **Takeaway 5:**
  - Replace "Several beat Jev on JevBench and BANKING77 at similar cost" with "Open-weight decision models beat Jev on JevBench, and Clef, Mercury and d1 beat it on BANKING77 (n = 77). Hosted rivals score below Jev on JevBench."
  - Add Clef's open weights and Clef-flash's $0.038 price.
- **Takeaway 6:**
  - "rubric-heavy support questions run about 100–130" → "about 75–95 net (148–189 gross)".
  - "a 77-option Choice is about 1,300+ tokens" → "about 1,670 tokens per request".

### R2 (`ledger-R2-llm.md`)

| Row | Field | Change |
|---|---|---|
| LLM-045 | Source / confidence / caveat | Add the primary source `https://developers.openai.com/api/docs/changelog.md` ("Oct 6 … Released the Decisions API in beta with gpt-6-luna"). Raise the date to [Certain]. **Replace** "Launched 5 days before Jev's announcement (2026-10-11). R1 should cross-check independent coverage" with: "Launched 3 weeks **after** Jev (2026-09-15, JEV-021), within a 2–4-week wave of competing decision APIs: Cloudflare Clef (10-01), Liquid d1 (10-05), Microsoft-Decision-1 (10-09)." |
| LLM-044 | Counter-evidence | Append:<ul><li>Independent data: S. Anand BANKING77 (n = 77): OpenAI Decisions 61/77 (79.2%), median 0.31 s, "materially overconfident"; the same model via chat scored 60/77 at 1.07 s (JEV-087).</li><li>JevBench preliminary Capability 68.8 on 300 public items, vs Jev 77.1.</li><li>No cache discount. At 2,000 tokens per message: $0.00020 vs Jev $0.000084 (2.4×).</li></ul> |
| LLM-068 | Confidence / caveat | [Certain] → [Likely]. Append: "Content from a search-engine excerpt; the direct fetch returned 403 (the URL itself was not fetched)." |
| LLM-007, LLM-011 | Caveat | Append: "Rolling 72 h P50. On 2026-10-11 the re-fetch showed Haiku 4.5 at 86.1 tok/s (peer median 1.14 s) and GPT-6 Luna at 0.83 s on both pages. Re-snapshot before Phase 4." |
| LLM-019, LLM-020 | Caveat | Replace "values rendered client-side and not visible" with "the mirror now embeds the AA payload server-side (`refreshedAt` 2026-10-11), but the launch-day snapshot is not reproducible". |
| Takeaway 2 | Text | Replace the "undercuts … 'first System One model' framing" sentence with: "Jev was first (2026-09-15); OpenAI followed 3 weeks later, alongside Cloudflare, Liquid and Microsoft. Jev's differentiation is eroding rather than its 'first' claim." Replace "near parity per decision" with "2.4× Jev per input token; neither offers a cache discount". Broaden the proposed rung to "**L2d: hosted decision-model API** (OpenAI Decisions, Clef/Clef-flash, Microsoft-Decision-1, d1)". |
| Takeaway 3 | Text | Add: "The only independent small-tier decision-API latency is OpenAI Decisions at 0.31 s median (Anand, location unstated), against Jev's 0.39 s in the same harness." |
| Gap row (new) | — | Add AA TTFT and tok/s for **Gemini 3.1 Flash-Lite**, which R3 uses in the ladder, or drop it from the ladder. |

### R3 (`ledger-R3-econ.md`)

| Row(s) | Field | Change |
|---|---|---|
| ECO-001–007, 009–037, 039–048, 050, 061 (48 rows) | VENDOR | **Y → N**, to match the R1 and R2 convention: VENDOR=Y marks a vendor's performance or marketing claim, not a list price or doc spec read from an official page. Edit the Conventions paragraph to match. Otherwise these rows breach the "VENDOR ≤ [Likely]" gate rule. |
| ECO-051, ECO-053, ECO-054 | Source type | `vendor-marketing` → `vendor-benchmark` (keep [Likely]), or confidence → [Guessing]. |
| ECO-066 | Value | Add "South India → West US 2: **194 ms**" (same Azure table). |
| R3 takeaway 5; contradiction 8 | Text | "India → US-West P50 RTT is 211–240 ms" → "**194–240 ms** P50 (Azure South India 194; Central India 211; Jio India West 231; AWS ap-south-1 ↔ us-west-2 232–240), datacenter-to-datacenter, no last mile". |
| ECO-020; R3 bullet 3 | Caveat / text | "Not checked for Astra" / "effort `none` is not verified for Astra" → "GPT-6 Astra rejects `none` with HTTP 400 (OpenAI reasoning guide; LLM-027). L1b on OpenAI also needs a reasoning allowance." |
| ECO-012; R3 takeaway 5; contradiction 6 | Text | "Vertex `asia-south1` per-model availability is unverified" → "Verified (LLM-053): in-India ML processing only for gemini-3.5-flash (deprecated on the Gemini API), gemini-2.5-flash and text-embedding-005." Also add: "Azure OpenAI Standard in South India covers gpt-4.1-mini and gpt-4o (LLM-046)." |
| ECO-019 | Caveat | "does not exist for OpenAI" → "does not exist for OpenAI first-party; Azure South India Standard serves gpt-4.1-mini and gpt-4o in-region (LLM-046)". |
| BoE table (new rows) | — | Add hosted decision-model APIs at 2,000 input tokens per message, no cache (prices from V19, V22–V24):<ul><li>OpenAI Decisions $0.10 → **$0.00020 (2.4×)**.</li><li>Clef-flash $0.038 → $0.000076 (0.90×).</li><li>Liquid d1 $0.04 → $0.000080 (0.95×).</li><li>Microsoft-Decision-1 $0.042 → $0.000084 (1.0×).</li><li>Clef $0.24 → $0.00048 (5.7×).</li></ul>Caveat: tokenizers differ. |
| BoE note | — | Add: "Jev's 2,000 tokens include the fixed overhead of about 250–300 (JEV-050). With 7 support questions at about 75–95 net each, plus a ~300-token state, a Jev call is about 1,100–1,250 tokens, so 2,000 is a conservative (high) Jev cost." |

---

## Cross-ledger issues

1. **Jev launch date.**
   - R1 is correct: 2026-09-15.
   - PLAN §0 ("Announced 2026-10-11") and R2 LLM-045 use the wrong date, and R2's ordering conclusion rests on it (V21).
   - PLAN §0 truth #1 ("vendor self-reported, from launch day") and §2 ("a vendor that launched today") are out of date. There are now 4 weeks of third-party evidence.
2. **Comparator generations are mixed.** "Luna", "Sol" and "Terra" appear unversioned in R1.
   - Vendor evals: the case data shows GPT-5.6 Sol.
   - Suraj: GPT-5.6 Luna.
   - Vals and the Decisions API: GPT-6 Luna and GPT-6.1 Sol.
   - R2 and R3 price GPT-6 Luna.
   - Every ratio in the study must name the exact model ID.
3. **VENDOR flag semantics differ.**
   - R1 and R2 use VENDOR=Y for vendor performance or marketing.
   - R3 uses it for any vendor-published fact, including list prices.
   - Harmonize these before M1 parses the ledgers.
4. **India in-region options.**
   - R2 verified Vertex `asia-south1` and Azure South India.
   - R3 still says "unverified" and "does not exist for OpenAI".
   - Neither ledger considers **open-weight decision models** (Clef, Clef-flash, Microsoft-Decision-1's Qwen base, Kev, Quyet). These could be self-hosted in Mumbai, which strengthens the L3 rung for P1-IN.
5. **GPT-6 Astra `none`.** R2 says 400 ([Certain]); R3 says unverified. Use R2.
6. **The decision-API rung lives in different places.** R1 lists the competitors, R2 has only OpenAI, and R3's BoE has none. The rung needs a single home: R2 for capabilities and R3 for prices.
7. **Duplicate values that disagree.**
   - India RTT: 211–240 (R3) vs 194–240 (sources) vs 200–280 (PLAN).
   - 77-option Choice: 1,670 tokens (JEV-051) vs "1,300+" (R1 takeaway).
   - GPT-6 Luna TTFT: 0.79 / 0.83 s (rolling).
   - Per-question tokens: 57 (GDPR) vs 100–130 (R1) vs 75–95 net (re-derived).
8. **Rows lacking conditions.**
   - JEV-053 and JEV-061 have "—".
   - Latency rows missing probe location, state size or concurrency: JEV-028, JEV-030, JEV-031, and R1 takeaway 3.
   - LLM-060 (TTS) states that its location is unknown, which is acceptable.
9. **VENDOR rows above [Likely]:** 48, all in R3 (see the R3 corrections).
10. **Marketing rows above [Guessing]:** 18 in R1 (JEV-009, 019, 020, 022, 025, 036, 040, 041, 042, 044, 045, 046, 047, 048, 078, 081, 085, 090) and 3 in R3 (ECO-051, 053, 054).
11. **Community sources at [Certain]:** none. The nearest case is LLM-068, a paper read through a search excerpt, which should be downgraded.

---

## Balance findings

**Is there counter-evidence for every headline claim?** Yes, on both sides, at the row level.
- **Jev:** every vendor multiplier, latency and accuracy row in R1 carries a counter-entry.
- **LLMs:**
  - Haiku 5.5 "Fastest" is countered by AA.
  - AA's E2E (10k input, 500 tokens) is explicitly flagged as overstating decision latency.

**Cherry-picking and omission signals to fix:**
1. JEV-087 drops the two systems at the top of the BANKING77 pilot (Clef 96.1% and Clef-flash 94.8%) and mislabels OpenAI Decisions.
2. R1 takeaway 5 implies that hosted rivals beat Jev on JevBench. They do not: Microsoft-Decision-1 scores 70.78 and OpenAI Decisions a preliminary 68.8, against Jev's 77.1.
3. **Pro-Jev evidence that is missing:**
   - OpenRouter's decision-model ranking shows **Jev 1.13 at 1.03B requests per week**, against 14.5M for the next model (GPT-6 Luna Decisions). This is real adoption evidence and is independent of the vendor.
   - Cisco: Jev's AUC beat a Gemma 4 31B judge on 7 of 8 safety benchmarks.
4. **Anti-Jev evidence that is missing:**
   - Cisco: a fine-tuned 1B encoder beats Jev at a 0.5% false-positive rate (recall 61% vs 34% on Cisco multi-turn). This directly supports C1b and S2.
   - JevOut (USC et al., NeurIPS 2026 Agenthon poster): short, natural context additions flip **61.4–73.2%** of correct decisions to a pre-chosen wrong option. The result covers Jev and other decision models.
   - Microsoft and Cloudflare say they are faster or better than Jev. These are vendor claims and should be labelled as such.
5. **Biases against LLMs inside the Jev evidence (the study must say so):**
   - The vendor evals use default reasoning and uncached estimated LLM costs.
   - The consistency cookbook ran the LLMs in a 16-way pool while Jev ran alone.
   - In Suraj's test the LLMs had 0% cache hits.
   - Vals ran 8 Jev requests in flight against 4 per LLM.
   - Anand's chat LLMs used verbalized confidence.
6. **Biases against Jev:**
   - Vendor accuracy is agreement with Astra and Fable, which, by the vendor's own admission, favours OpenAI and Anthropic.
   - Anand's 77-way Choice is a high-cardinality task that the docs flag as hard.

**Independence of the "independent" Jev sources:**

| Source | Relationship to TypeSafe | Note |
|---|---|---|
| Vals AI | No tie found or disclosed | Calls the vendor headline one that "holds up". Treat as independent, sympathetic in tone. |
| S. Anand | Individual | Reproducible files. Pilot scale (n = 77). |
| openjev-sglang | Builds a competing open re-implementation | Jev beat the author's own model, so there was no incentive to flatter Jev. |
| JevBench | Community leaderboard; states it is "independently of TypeSafe AI" | Maintainers and funding not identified. Scoring revisions are disclosed. |
| Suraj Phanindra | Individual | Not peer-reviewed. |
| Cisco | Independent, but sells its own classifier | Competing interest. |
| Microsoft, Cloudflare, Liquid | Competitors | Self-reported numbers. |
| MotherDuck | Partner that resells Jev | Should be VENDOR=Y. |
| Jack & Jill | Customer story published by the vendor | Vendor marketing. |
| a16z | Investor | Vendor marketing. |
| arXiv 2609.29429 | Academic | No ties stated. |
| TechCrunch, The Register | Press | Mostly repeat vendor numbers. |

**Important evidence still missing for the study:**
1. **No p95/p99 latency, for Jev or for any LLM decision path,** from any source. P1 must stay modelled, with flip thresholds.
2. No Jev latency measured from India or the EU.
3. No independent Haiku 5.5 thinking-off TTFT.
4. No AA data at about 2K input (the 1k workload is not shown in text).
5. Jev per-language accuracy: JevBench's Languages view is the lead to follow.
6. Whether Clef on Workers AI serves from India: unverified.
7. Decision-API latency distributions: OpenAI publishes none.

---

## Gate checklist (`phase-0-plan-critic.md`, Phase 1)

| # | Criterion | Status | Evidence / fix |
|---|---|---|---|
| G1 | ≥ 40 rows (all three ledgers combined); every row has all 11 columns, including conditions | **PASS (with fixes)** | 272 rows, 11 columns each. Fix the conditions on JEV-053 and JEV-061 ("—"), and the probe/state/concurrency gaps in JEV-028, JEV-030 and JEV-031. Note: the output is three files, not `research/evidence-ledger.md`. Either update the PLAN §5 Phase 1 output name or add an index file. |
| G2 | Mandatory IDs present (all three ledgers combined) | **PASS** | All Jev items are present (JEV-003/005/006/007/008/010/022/023/027/025/033/035/036/040/039/020/019/016/015/013). LLM prices for 3 providers × 3 tiers including Haiku 5.5 and the tokenizer note (ECO-001–024, ECO-007). AA TTFT/tok/s with date and probe (LLM-001–017). Capability matrix (R2). GPU $/hr (ECO-039–050). Encoders on CPU and GPU (ECO-054–057). Token sizes (ECO-058/059). Voice (LLM-056–064). **Gaps:** AA data for Gemini 3.1 Flash-Lite, which the ladder uses; Haiku 5.5 thinking-off TTFT, which does not exist anywhere and is properly logged. |
| G3 | Critic re-fetches ≥ 12 named high-impact claims; zero unresolved mismatches | **FAIL until fixed** | 61 re-fetched (table above). 3 CONTRADICTED and 8 PARTIALLY, all with mechanical fixes. Passes once the R1, R2 and R3 corrections are applied. |
| G4 | 100% of VENDOR rows ≤ [Likely]; marketing rows ≤ [Guessing]; counter-evidence for every headline vendor claim | **FAIL until fixed** | 48 R3 VENDOR=Y rows at [Certain] (convention mismatch). 18 R1 and 3 R3 `vendor-marketing` rows at [Likely]. The counter-evidence part passes. |
| G5 | "Independent coverage of Jev" section, with queries logged | **PASS (with additions)** | R1 Method lists 10 queries and the sources used. Add the Cisco, JevOut, OpenRouter-rankings and official competitor posts (new rows below). |
| G6 | No row without a URL; no URL used without being fetched; fetch failures logged | **PASS (one exception)** | All rows have URLs, and failures are logged in all three ledgers. Exception: LLM-068's PNAS URL returned 403 and its content came from a search excerpt. Downgrade it and annotate it. |

---

## New rows to add (sources already fetched by Critic-1 on 2026-10-11)

| Proposed ID | Claim | Value / conditions | URL | Type | VENDOR | Confidence |
|---|---|---|---|---|---|---|
| JEV-105 | Cisco: Jev vs a fine-tuned 1B encoder vs Laya, content safety | <ul><li>24 harm categories, 6 datasets, LLM-generated reference labels.</li><li>At 0.5% FPR on Cisco multi-turn, recall is encoder 61% vs Jev 34% vs Laya ≈ 0.</li><li>The encoder had the best AUC on 5 of 6 datasets.</li><li>Jev vs a Gemma 4 31B judge (thinking off, P("Yes")): Jev's AUC was higher on 7 of 8; results were mixed at 0.5% FPR.</li><li>Published 2026-10-05.</li></ul> | https://blogs.cisco.com/ai/jev-decision-models-on-trial | independent-benchmark | N (Cisco has a competing product) | [Likely] |
| JEV-106 | JevOut: context-redirection fragility | <ul><li>Probability-guided natural additions (median 31 words) flip 61.4–73.2% of initially correct decisions to a fixed wrong option.</li><li>Covers 4 decision systems (including Jev) and 7 datasets; transfers across models.</li><li>91.6% of 250 sampled additions were judged natural by humans.</li><li>NeurIPS 2026 Agenthon poster.</li></ul> | https://xzx34.github.io/jevout/ | paper | N | [Likely] |
| JEV-107 | OpenRouter decision-model usage | <ul><li>Jev 1.13: 1.03B requests per week (+7%).</li><li>Then GPT-6 Luna Decisions 14.5M, Perplexity Decider 9.66M, Clef Flash 8.79M, Clef 6.08M, Mercury Decide 4.9M, Microsoft-Decision-1 4.16M, d1 3.87M.</li><li>Snapshot 2026-10-11; OpenRouter traffic only.</li></ul> | https://openrouter.ai/rankings/decisions | independent-benchmark (marketplace data) | N | [Likely] |
| JEV-108 | Cloudflare Clef / Clef-flash | <ul><li>Clef: 27B, $0.24/MTok input, 65,536-token context.</li><li>Clef-flash: 9B, $0.038/MTok input, 24,576-token context.</li><li>Output free; multimodal; Jev-compatible Noul/Choice/Score.</li><li>Open weights (post-trained Qwen3.8-27B / Qwen3.5-9B); Workers AI edge GPUs.</li><li>Self-reports beating Jev on 3 of 4 TypeSafe workflows (not reproduced).</li></ul> | https://developers.cloudflare.com/ai/models/%40cf/cloudflare/clef/ ; https://developers.cloudflare.com/ai/models/%40cf/cloudflare/clef-flash/ ; https://www.theregister.com/ai-and-ml/2026/10/01/cloudflare-tries-to-outplay-jev-with-open-weight-clef-models/5300649 | official-doc + press | Y (performance claims) | Prices [Certain]; performance [Guessing] |
| JEV-109 | Microsoft-Decision-1 | <ul><li>Announced 2026-10-09; available in Microsoft Foundry and on OpenRouter.</li><li>Qwen3.5-9B post-train; $0.042/MTok input, $0 output; 32,768-token context.</li><li>Vendor claim: fastest and most accurate in its 36-benchmark test.</li><li>JevBench: 459 ms native median; Capability 70.78 (below Jev).</li></ul> | https://commandline.microsoft.com/microsoft-decision-1-model-foundry/ ; https://openrouter.ai/microsoft/microsoft-decision-1 ; https://benchmarkheaven.com/jev-models | official-doc + independent-benchmark | Y (claims) | Specs [Certain]; claims [Guessing] |
| JEV-110 | Liquid d1 | <ul><li>Announced 2026-10-05; text and images.</li><li>Vendor: 200–300 ms per text decision.</li><li>OpenRouter: $0.04/MTok input, 65,536-token context, `/v1/systemone` schema.</li></ul> | https://www.liquid.ai/blog/d1-decision-model ; https://openrouter.ai/liquid/d1 | official-doc | Y | Specs [Certain]; latency [Guessing] |

---

## Lead-level corrections to PLAN.md (outside the ledgers, flagged for the lead)

- **§0 "Announced 2026-10-11"** → "Launched 2026-09-15 (early access); Series A $870M at $7.5B on 2026-10-09".
- **Truth #1 ("vendor self-reported, from launch day")** → "4 weeks of third-party evidence exist; quality and calibration are task-dependent".
- **§2:** rename L1b to "frontier at lowest effort" (it is not buildable as written). Add an **L2d hosted decision-model API** rung. Change "a vendor that launched today" to "a 4-week-old vendor in a fast-commoditizing category".
- **§1 India RTT:** "about 200–280 ms" → "194–240 ms P50 datacenter backbone; tail and last mile not captured".
- **§4 token model:** "about 57 tokens per question" → "57 (short GDPR questions) to about 75–95 (support rubrics) net, plus about 250–300 fixed overhead per request".
- **P1-IN:** add self-hosted open-weight decision models in an Indian region as an in-region option.
- **phase-0-plan-critic Risk 3.2 ("Jev has no public calibration metrics")** is superseded by JEV-083, JEV-084 and JEV-087.

---

## Top findings the study must reflect (survived verification)

1. **Jev launched on 2026-09-15, not 2026-10-11.**
   - TypeSafe raised $870M at $7.5B on 2026-10-09.
   - On OpenRouter, Jev carries about 1.03B decision requests per week, about 70× the next decision model.
   - Adoption is real. The "launch-day, vendor-only evidence" framing is obsolete.
2. **"Decision model" is now a category, not a moat.**
   - Within 4 weeks came OpenAI Decisions (2026-10-06), Cloudflare Clef/Clef-flash (open weights, Clef-flash $0.038/MTok), Liquid d1 ($0.04), Microsoft-Decision-1 ($0.042) and more than 100 others.
   - OpenAI's API offers gpt-6-luna at $0.10/MTok input only, with images, US/EU residency and ZDR/HIPAA.
   - The architecture should put a **Decision Service port** in front of swappable backends. The ladder needs a hosted-decision-API rung.
3. **Price parity at the small tier.**
   - Haiku 5.5 and GPT-6 Luna both list at $0.10 in / $0.50 out / $0.01 cached.
   - A cached 7-decision call costs $0.000077–0.000091, against Jev's $0.000084.
   - Decisions are about 2% of the per-message bill.
   - Jev's price advantage is real only against mid-tier and frontier models.
4. **The headline multipliers depend on the comparator.**
   - 193.6× / 444.6× is the vendor's own "higher end", with no named comparator. Each figure fits a different plotted Anthropic point.
   - The homepage example implies 75× / 171× against GPT-5.6 Terra at default reasoning.
   - Against cheap tiers in practice: about 8× cheaper and 2× faster (Jack & Jill), and about 3× cheaper once LLMs have enough capacity (Suraj).
5. **Quality depends on the task.**
   - Near the frontier on bounded verification: claims 0.975, tying GPT-6 Astra, Sol and Luna; BoolQ 91.6%.
   - Last of 12 on LegalBench (class-balanced 0.730).
   - Last of 17 on a 77-case BANKING77 pilot (75.3%).
   - Below GPT-5.6 Sol on the vendor's own workflows (67.8% vs 74.1%).
   - A fine-tuned 1B encoder beats Jev at strict FPR on safety (recall 61% vs 34%).
6. **Calibration does not transfer between tasks.**
   - ECE is 0.011 on claims and 0.108 on LegalBench.
   - Under a 1% error budget, the realised error on held-out items was 1.6%.
   - Jev was overconfident by 12 points on BANKING77.
   - Thresholds still need labelled data, so Jev's "no labels" edge is a cold-start edge.
7. **Latency.**
   - Independent Jev medians are 0.10–0.39 s, with probe locations unstated.
   - Latency barely grows with the number of questions (0.10 → 0.12 s for 1 → 64 judgments).
   - Multi-call workflows take 0.3–1.0 s.
   - **No p95 exists for Jev or for any LLM decision path**, so P1 must be modelled with flip thresholds.
   - OpenAI Decisions measured a 0.31 s median in the same harness where Jev measured 0.39 s.
8. **The fair LLM baseline is not independently measured.**
   - Haiku 5.5 defaults to thinking on at medium effort: 9.7–13.4 s to the first answer token on AA, at 10k input, P50, `us-central1`.
   - Thinking must be disabled explicitly, and only at effort ≤ high.
   - Thinking-off proxies are 0.48–0.83 s TTFT (Haiku 4.5, GPT-6 Luna `none`, Terra non-reasoning).
   - Frontier models cannot turn reasoning off (Opus 5.5, Fable 5.1, Astra, 6.1 Sol), so L1b as written cannot be built.
9. **Capacity binds on both sides.**
   - Jev's defaults are 80 req/s and 100K tok/s, about 50 msg/s at 2K tokens per message.
   - Haiku 5.5's Scale tier is 10K RPM, about 167 req/s.
   - Both need custom limits for 2,000 msg/s.
   - Claude cache reads are not counted toward ITPM; OpenAI cached tokens do count toward TPM.
   - The Jev SDK defaults (10 s timeout, 2 retries, 30 s budget) break a 300 ms SLO unless overridden.
10. **Operations and residency.**
    - Jev processes only in the US (us-west-2), with no SLA (operator-reported 99.838%), no VPC and no BAA. ZDR is available on request.
    - From India, the backbone P50 to US-West is 194–240 ms.
    - In-India processing exists only on Vertex `asia-south1` (gemini-3.5-flash, gemini-2.5-flash) and in Azure South India Standard (gpt-4.1-mini, gpt-4o). Neither current Claude nor GPT-6 has it.
    - Open-weight decision models are the realistic in-region option.
11. **LLM confidence mechanics.**
    - Claude has no token logprobs. The OpenAI-compatible layer silently returns empty `logprobs`, and temperature is fixed at 1.0.
    - LLM-side confidence on Claude therefore means verbalized scores or k-sampling.
    - Logprob-based confidence is realistic only on GPT-6 Luna at effort `none` (top-20 cap) or on a self-hosted model.
12. **Robustness of guardrails.**
    - Jev's own docs list 9 jaggedness modes, including "adversarial content … can move the answer" and a first-option bias.
    - JevOut flips 61–73% of correct decisions with natural context additions.
    - A guardrail built on Jev, or on any single decision model, must not be the only control.
