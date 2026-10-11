## Vendor backends (Jev, Claude)

> Written by LAB-B for the lead to merge into `lab/LEARNING.md`. Everything in this section that came from the stub is **MOCK**. The live paths are **UNTESTED**: no API keys exist in this environment, and Jev is early access with a waitlist.

### What is here

| File | What it does |
|---|---|
| `jevlab/backends/jev.py` | Jev backend on the real `typesafe-sdk==0.7.4`. It asks one **Choice** question per utterance: `state` = the utterance, `criteria` = `{label: description}`, model pinned to `jev-1.13.0`. Optional speculative fan-out. |
| `jevlab/backends/claude.py` | Claude backend on the real `anthropic==1.13.0` (rung L2). Uses `claude-haiku-5-5` with structured outputs (`output_config.format`, enum label), `effort: low`, thinking disabled, and the rubric cached with `cache_control`. |
| `jevlab/stub_server.py` | Local HTTP stub for `POST /v1/systemone` and `POST /v1/messages`. Every response is MOCK. |
| `jevlab/backends/c1.py` | C1a classical baseline (TF-IDF or model2vec + logistic regression), measured on CPU. |
| `jevlab/leakage.py` | `assert_no_lab_or_mock_in(path)`: fails if a markdown table outside a "Hands-on lab" section contains `LAB:` or `MOCK`. |
| `configs/jev.yaml`, `configs/claude.yaml`, `configs/c1.yaml` | Backend configs. Committed vendor configs default to **stub** mode. |

### Verified-on matrix (LAB-B parts)

| Path | Linux CPU container (executed here) | macOS (Apple Silicon) |
|---|---|---|
| Jev backend → stub (real SDK, end to end) | ✅ `pytest tests/test_b_*.py` | untested (pure Python, expected to work) |
| Claude backend → stub (real SDK, end to end) | ✅ same | untested |
| Jev backend → **live** `api.typesafe.ai` | ❌ **untested** (no key) | ❌ untested |
| Claude backend → **live** `api.anthropic.com` | ❌ **untested** (no key) | ❌ untested |
| C1a sweep (`python -m jevlab.backends.c1 --sweep`) | ✅ about 30 s, results in `results/c1_sweep.*` | untested (sklearn/scipy have arm64 wheels) |

### Stub mode: run the real SDK code without keys

The stub is what the tests use. It makes the real SDK serialise the request, send HTTP, retry, parse and validate, exactly as it would against the vendor.

```bash
cd lab && source .venv/bin/activate
python -m jevlab.stub_server --port 8765 &          # prints: listening on http://127.0.0.1:8765 -- every response is MOCK
python - <<'PY'
from jevlab.data import load_task
from jevlab.backends.jev import JevBackend
from jevlab.backends.claude import ClaudeBackend
task = load_task("clinc150")
with JevBackend({"mode": "stub", "base_url": "http://127.0.0.1:8765"}) as jev:
    print(jev.probe(task))                         # provenance MOCK:jev
    print(jev.predict(task, task.split("test")[:3])[0])
with ClaudeBackend({"mode": "stub", "base_url": "http://127.0.0.1:8765", "confidence": "self_consistency", "k": 5}) as cl:
    print(cl.predict(task, task.split("test")[:1])[0].probs)   # vote fractions, MOCK:claude
PY
```

How the stub behaves:
- **Documented examples are replayed verbatim.** If a request matches one of the `api.md` examples (the payouts message with `is_urgent`, `department` or `frustration`), the stub returns the documented response byte-for-byte in JSON terms.
- **Other requests get a fake distribution.** It is deterministic, seeded by a hash of the request, and its numbers mean nothing. The confidence values use the documented formulas from `confidence.md`, so the response shape is realistic. The token counts use a crude `~300 + chars/4` model.
- **`/v1/messages` simulates prompt caching.** The cached-prefix estimate must be at least 512 tokens for `claude-haiku-5-5`, the same minimum the docs give. Repeat calls draw new samples, as temperature 1 would, so self-consistency has something to vote on.
- **Watermarks.** Every response carries `x-jevlab-mock: 1`. The backends tag a Prediction `MOCK:<backend>` if they see that header, if the base URL is loopback, or if the config says `mode: stub`. This holds even when the config claims `live`.
- **Keys.** Stub mode always sends the dummy key `stub-not-a-real-key`. It never forwards `$TYPESAFE_API_KEY` or `$ANTHROPIC_API_KEY`, even if they are set. Live mode refuses a loopback URL.
- **Fault injection.** `POST /__stub/config` accepts these fields:
  - `delay_ms`
  - `fail_status` with `fail_count`, for example 529 or 429
  - `jev_model_override` (alias drift)
  - `jev_bad_probs`
  - `claude_refuse`
  - `claude_thinking_block`
  - `claude_case_flip` (enum capitalisation)

  `GET /__stub/requests` returns the recorded requests. Secrets are redacted to `<dummy-key>` or `<redacted-non-dummy>`.

### Live mode: getting keys and running (UNTESTED here)

1. **Keys** (never commit them):
   - **Jev:** request early access and create a key at <https://console.typesafe.ai/>, then `export TYPESAFE_API_KEY=...`.
   - **Claude:** create a key in the Claude Console (<https://platform.claude.com/>), then `export ANTHROPIC_API_KEY=...`.
2. **Switch the config.** In `configs/jev.yaml` (or `claude.yaml`), set `mode: live` and `base_url: null`. With `null`, the SDK uses `https://api.typesafe.ai` or `$TYPESAFE_BASE_URL`; for Claude, `https://api.anthropic.com` or `$ANTHROPIC_BASE_URL`.
3. **Run.** Use `python -m jevlab run --config configs/jev.yaml` (LAB-A's CLI), or the Python snippet above with `{"mode": "live"}`. Always call `probe()` first. It raises if:
   - the answer is not from the pinned `jev-1.13.0`;
   - the probabilities don't sum to about 1;
   - the label is outside the option set;
   - the usage block is missing.
4. **Check the tags.** Results are tagged `LIVE:jev:jev-1.13.0` or `LIVE:claude:claude-haiku-5-5`.
5. **Expect a cold start.** The first call opens TLS and is marked `cold=True`. Report warm and cold latency separately.

**Real-time settings, and why they are explicit.** Both SDKs' defaults would break a 300 ms decision SLO:

| SDK | Defaults | Source |
|---|---|---|
| `typesafe-sdk` | 10 s timeout per HTTP operation; `RetryPolicy` = 2 retries, 0.5 s backoff doubling to 5 s, 30 s total budget | `constants.md`, `retries.md`; pinned by `test_sdk_defaults_would_break_realtime_slo` |
| `anthropic` | 10-minute timeout, 2 retries | — |

The configs therefore set:
- **Jev:** `timeout_s: 0.25`, `max_retries: 0`, `retry_budget_s: 0.3`. Note that the TypeSafe timeout applies to each HTTP operation, not to the whole request.
- **Claude:** `timeout_s: 1.5`, `max_retries: 0`.

On a timeout, 429 or 5xx, the backend returns `label=None` with `raw.error` set. That outcome counts in `invalid_rate`, and the caller applies its fail-open or fail-closed fallback, such as C1a.

**Claude has no logprobs.** There are zero mentions of "logprob" in the `anthropic` 1.13.0 package, in the claude-api skill, and in the Messages API reference (checked 2026-10-11). Confidence is therefore one of two settings:
- `confidence: none`: `probs = null`, so ECE and Brier are **N/A** for this backend.
- `confidence: self_consistency`, with k samples. `probs` holds the vote fractions, which are multiples of 1/k and therefore give coarse ECE. Every sample's tokens are charged on the Prediction. With `sc_parallel`, sample 1 runs alone to write the cache and the other k−1 run in parallel, so latency is about 2 calls and cost is k×.

**What live mode costs.** Everything below is **[Guessing]** until R3 verifies it in the evidence ledger. List prices were read 2026-10-11:
- Jev: $0.042 per 1M input tokens; output is free.
- Haiku 5.5, prompts ≤ 100K tokens: input $0.10, 5-minute cache write $0.125, cache read $0.01, output $0.50, all per 1M tokens.

The request sizes were measured on the default `clinc150` task (15 intents + out-of-scope). They are character counts converted at about 4 characters per token; real tokenizers differ, and Haiku 5.5's newer tokenizer counts about 30% more than Haiku 4.5.
- Choice question JSON: 1,227 characters, about 300 tokens.
- Mean utterance: about 12 tokens.
- Claude rubric: 1,357 characters, about 340 tokens.

| Per 1,000 decisions | Token arithmetic [Guessing] | USD per 1k [Guessing] |
|---|---|---|
| Jev J1, one Choice per request | (≈300 fixed overhead + ≈12 state + ≈300 question) ≈ 600 input tokens × $0.042/M. Question tokens are re-billed on every request; there is no cache | ≈ $0.025 (range $0.017–0.034 for 400–800 tokens) |
| Claude L2, rubric **not** cached | ≈340 rubric + ≈25 message + schema overhead (unknown) ≈ 400 input × $0.10/M, plus ≈10 output × $0.50/M. **The rubric is below Haiku 5.5's 512-token cache minimum** | ≈ $0.045 |
| Claude L2, rubric padded to ≥ 512 tokens and cached | 512 × $0.01/M read + 25 × $0.10/M + 10 × $0.50/M. Cache writes are about $0.00006 each, once per 5-minute TTL | ≈ $0.013 |
| Claude L2c, self-consistency k = 5 | 5 × the rows above | ≈ $0.06–0.23 |
| Claude with `thinking: adaptive` | Adds the thinking tokens at the output rate: 100 thinking tokens ≈ +$0.05 per 1k | +$0.05 per 100 thinking tokens |
| C1a TF-IDF, CPU | p50 1.5 ms × $0.0425 per vCPU-hour [Guessing] | ≈ $0.00002 |

Two lessons for the study follow (both [Guessing]):
- **Per decision, Jev and a cached small-tier LLM are within a small factor of each other** (PLAN §0.3). Jev re-bills the option rubric on every call, while the LLM's rubric can be cached.
- **A single live smoke run is cheap.** One pass over the 240-item test split costs well under $0.10 per backend, even at k = 5. The binding constraints are rate limits and latency: 80 requests/s on Jev by default, and Haiku's tier limits.

### C1a classical baseline (measured here, provenance LAB)

Run it with `python -m jevlab.backends.c1 --sweep`, which reads `configs/c1.yaml` and writes `results/c1_sweep.csv` and `results/c1_sweep.log`. The sweep:
- trains on N ∈ {10, 50, 200} examples per class, drawn from the TRAIN split only (nested seeded prefixes; CLINC150 caps in-scope classes at 100);
- fits temperature T on the CALIBRATION split only, using LAB-A's `jevlab.calibration`;
- evaluates on the **same 240-item TEST split as LAB-A's default task**, which is asserted at run time;
- measures latency per item, warm, at batch size 1 with single-threaded BLAS.

Headline numbers on the P3 reference split (`clinc150-banking15+oos`, 16 labels), all **LAB:c1:…:fp32:linux-cpu-4vcpu**:

| Features | N per class | Accuracy (CI95) | Macro-F1 | ECE raw → after T | p50 / p95 latency | Train time |
|---|---|---|---|---|---|---|
| TF-IDF word 1–2 + char 2–5 | 10 | 0.846 (0.800–0.892) | 0.847 | 0.275 → 0.053 | 1.5 / 2.7 ms | 0.8 s |
| TF-IDF | 50 | 0.908 (0.867–0.946) | 0.907 | 0.122 → 0.022 | 1.5 / 2.9 ms | 2.3 s |
| TF-IDF | 200 (in-scope capped at 100) | 0.938 (0.904–0.967) | 0.938 | 0.091 → 0.023 | 1.5 / 2.2 ms | 3.6 s |
| model2vec potion-base-8M | 50 | 0.925 (0.888–0.958) | 0.925 | 0.116 → 0.030 | 0.24 / 0.46 ms | 0.6 s |

ECE uses 10 equal-mass bins. The raw logistic regression is **under**-confident (T ≈ 0.4–0.6 sharpens it). Temperature scaling needs the labelled calibration split, which is exactly the lesson from Jev's "calibrated without labels" pitch. P3 compares the N = 50 row with the lab zero-shot scorer (LAB-A) on the same split.

### Exercises (vendor and baseline)

1. **Fan-out token accounting (P6).** Call `JevBackend.fanout_token_demo(task, item, extra_questions)` against the stub. You should observe that k questions in one request pay the state and the fixed overhead once, while k separate requests pay them k times. The stub's token model is MOCK; redo it live if you have a key.
2. **Self-consistency cost versus resolution.** Run the Claude backend in the stub with `k` ∈ {3, 5, 9}. You should observe that tokens and $ scale k×, while the probability grid is only 1/k. ECE needs real data, so do this live.
3. **Real-time deadline.** Run `curl -XPOST localhost:8765/__stub/config -d '{"delay_ms": 400}'`, then predict with `timeout_s: 0.25`. You should observe `label=None` and `raw.error == "timeout"` in about 0.25 s. With the SDK defaults, the same call would wait.
4. **Label-count sweep (P3).** Edit `c1.sweep.n_per_class`, for example `[5, 10, 20, 50, 100]`. You should observe that accuracy climbs fast from N = 5 to 50 and then flattens, and that ECE before temperature scaling falls as N grows.

### Troubleshooting

- **Stub requests time out or go to the proxy.** `127.0.0.1` and `localhost` must be in `NO_PROXY`; they are in this container. Use `http://` for the stub, not `https://`.
- **`TypeSafeError` at client creation.** The SDK validates the key before any request: no whitespace, no control characters, ASCII only. Stub mode always uses the dummy key.
- **Score answers have int keys in Python.** `typesafe-sdk` 0.7.4 parses Score `legend` and `probabilities` keys as `int`, while the wire JSON uses `"0"`, `"1"`, … (as in `api.md`). Use `resp.raw_http_response.json()` to see the wire form.
- **Haiku 5.5 400 errors.** Common causes:
  - `temperature`, `top_p` or `top_k` was sent;
  - an assistant prefill was sent;
  - `thinking: {type: "enabled", budget_tokens}` was sent;
  - `thinking: disabled` was combined with `effort` `xhigh` or `max`.

  The backend sends none of these.
- **`cache_read_input_tokens` is always 0.** The rubric is shorter than the 512-token minimum, or something in the prefix changes between calls. Permuting `labels_order` changes the prefix by design.
- **The HF "unauthenticated requests" warning** during the model2vec download is harmless. The model is pinned to revision `bf8b056…`, and only `model.safetensors`, `tokenizer.json` and `config.json` are fetched.
