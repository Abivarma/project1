# Local Lab: load any local model and learn

This lab answers one closed-set question two ways, on the same labelled data, and scores both on accuracy, calibration and latency:

- **(a) The LLM way.** JSON-schema structured generation: the model writes `{"label": "<one of the options>"}` under a grammar.
- **(b) A Jev-style decision primitive (emulation).** The options get single-token codes (A, B, C, ...). The model's next-token distribution at the answer position, summed over each code's variants, *is* the option distribution. Temperature scaling then calibrates it. This is an emulation of the *shape* of Jev's output. It is never "local Jev": it says nothing about Jev's accuracy, calibration or latency.

Three statements to keep in front of you:

1. **Lab numbers are illustrative.** They come from tiny local models on a laptop or a CPU container and a public dataset. They are not production numbers and they are not Jev numbers. Every result row is tagged `LAB:<backend>:<model>:<quant>:<hardware>`, and the leakage test keeps `LAB`/`MOCK` values out of the study's headline tables.
2. **Temperature scaling needs labels.** The calibration step fits one parameter T on a labelled calibration split. Jev's pitch is calibrated probabilities *without* labels. That gap is the lesson: a local model gets calibrated probabilities only after you pay for labels; whether Jev's claim holds can only be checked against Jev itself.
3. **The ($) column for local models is a $-equivalent:** power × time × $/kWh plus amortised hardware, with [Guessing] parameters printed in every run log. It is not comparable to API list prices without utilisation assumptions.

Contents: [Quickstart (Linux CPU, executed)](#quickstart-linux-cpu-what-was-executed-here) · [Mac setup](#mac-setup-apple-silicon) · [Verified-on matrix](#verified-on-matrix) · [Swapping models](#swapping-models) · [How the two modes work](#how-the-two-modes-work) · [Smoke-run results](#hands-on-lab-smoke-run-results-lab-illustrative) · [Exercises](#exercises) · [Troubleshooting](#troubleshooting) · [Vendor backends (Jev, Claude)](#vendor-backends-jev-claude)

---

## Quickstart (Linux CPU, what was executed here)

The container had 4 vCPUs, 15 GB RAM, no GPU and Python 3.13.

```bash
cd lab
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt   # llama-cpp-python compiles (~10 min)

# 1. Model: Qwen2.5-0.5B-Instruct, Q4_K_M GGUF (Apache-2.0), pinned revision, 491 MB
.venv/bin/python -I -c "from huggingface_hub import hf_hub_download as d; print(d('Qwen/Qwen2.5-0.5B-Instruct-GGUF', \
  'qwen2.5-0.5b-instruct-q4_k_m.gguf', revision='9217f5db79a29953eb74d5343926648285ec7e67', local_dir='models/qwen2.5-0.5b-instruct-gguf'))"
# sha256 74a4da8c9fdbcd15bd1f6d01d621410d31c6fc00986f5eb687824e7b93d7a9db

# 2. llama-server. Here it was built from the llama.cpp source vendored in the llama-cpp-python 0.3.36
#    sdist (llama.cpp commit 0c1e570), because github.com release pages were blocked by the proxy:
#    cmake -S <sdist>/vendor/llama.cpp -B build -DLLAMA_CURL=OFF && cmake --build build --target llama-server -j4
llama-server -m models/qwen2.5-0.5b-instruct-gguf/qwen2.5-0.5b-instruct-q4_k_m.gguf \
  --host 127.0.0.1 --port 8081 -c 4096 -t 4 --jinja -a qwen2.5-0.5b-instruct-q4_k_m --parallel 1 &

# 3. Ollama 0.40.2 (official Linux tarball, ~1.44 GB with CUDA libs), serving the SAME GGUF
OLLAMA_MODELS=$PWD/models/ollama ollama serve &
printf 'FROM %s\nPARAMETER temperature 0\n' "$PWD/models/qwen2.5-0.5b-instruct-gguf/qwen2.5-0.5b-instruct-q4_k_m.gguf" > Modelfile
ollama create qwen2.5-0.5b-lab:q4_k_m -f Modelfile

# 4. Run: probe -> predict (calibration + test) -> metrics before/after T -> permutation test -> agreement check
.venv/bin/python -m jevlab run --config configs/ci-cpu.yaml
#    -> results/<run_id>.csv, .log, _reliability.png, _predictions.jsonl.gz

# Tests (no network, no model needed for the unit tests)
.venv/bin/python -m pytest -q
```

Other commands: `python -m jevlab probe --config <cfg>` (capability probes only), `python -m jevlab task` (print the task and label descriptions), `python -m jevlab state-sweep ...` (exercise 5), `python -m jevlab run ... --limit-test 20 --no-permutation` (a quick try).

**The task.** `clinc150` (default): CLINC150's 15 *banking-domain* intents plus CLINC's own out-of-scope class, renamed `out_of_scope` (CC-BY-3.0, pinned parquet revision). Splits follow CLINC's: train ← CLINC train (100 per class), calibration ← CLINC validation (10 per class = 160), test ← CLINC test (15 per class = 240). `banking77` is also available: 15 seeded Banking77 intents (CC-BY-4.0, parquet mirror `legacy-datasets/banking77`, because the canonical repo is a loading script, which is not run) plus CLINC out-of-scope utterances. That out-of-scope class comes from a different dataset, so it may be easier to spot by style. The processed splits are cached as JSONL in `lab/data/`, so tests run offline.

---

## Mac setup (Apple Silicon)

### How big a model fits? (RAM tiers, [Guessing])

Assumptions: Q4 weights take about 0.55–0.6 GB per billion parameters; add the KV cache (grows with context) and 1–2 GB of runtime overhead. By default macOS lets Metal wire only about 65–75% of unified memory (raising it with `sudo sysctl iogpu.wired_limit_mb=<MB>` is an advanced setting with risk: the OS can run out of memory). Leave room for your browser and IDE.

| Mac unified memory | Comfortable model size (Q4 unless noted) | Example to try |
|---|---|---|
| 8 GB | up to 3–4B | `qwen2.5:3b-instruct`, `llama3.2:3b` |
| 16 GB | 7–9B; 12–14B is tight | `qwen2.5:7b-instruct` (the Mac configs' default) |
| 24 GB | about 14B | `qwen2.5:14b-instruct` |
| 32–36 GB | 27–32B | `qwen2.5:32b-instruct` |
| 64 GB | 70B | `llama3.3:70b` |
| 96–128 GB | 70B at Q8, or large MoE models | |

For decision tasks the learning sweet spot is 1–8B: big enough to follow the option list, small enough to iterate in seconds.

### Install (official sources; cite: research/ledger-LOC-local.md)

**The lab itself**

```bash
cd lab && python3 -m venv .venv
CMAKE_ARGS="-DGGML_METAL=on" .venv/bin/pip install -r requirements.txt   # Metal build of llama-cpp-python 0.3.36
.venv/bin/python -m pytest -q                                            # unit tests: no server, no model
```

**Ollama** (macOS 14 Sonoma or newer; LOC-008). Logprobs need ≥ 0.12.11 (LOC-001); this lab ran 0.40.2.

```bash
# Download from https://ollama.com/download and drag Ollama.app to /Applications (the docs' preferred method)
ollama --version                    # must be >= 0.12.11 for logprobs
ollama pull qwen2.5:7b-instruct     # ~4.7 GB
.venv/bin/python -m jevlab run --config configs/mac-ollama.yaml
```

**LM Studio** (≥ 0.3.39 for `/v1/responses` logprobs; LOC-016..019)

```bash
# Install the app from https://lmstudio.ai ; the `lms` CLI ships with it
lms get qwen2.5-7b-instruct
lms load qwen2.5-7b-instruct
lms server start                    # http://localhost:1234
.venv/bin/python -m jevlab run --config configs/mac-lmstudio.yaml
```

**llama.cpp `llama-server`** (LOC-015). Homebrew tracks the latest release, so record `llama-server --version` in your notes. To pin, build a tagged source tree (Metal is on by default on macOS).

```bash
brew install llama.cpp
hf download bartowski/Qwen2.5-7B-Instruct-GGUF Qwen2.5-7B-Instruct-Q4_K_M.gguf \
   --revision 8911e8a47f92bac19d6f5c64a2e2095bd2f7d031 --local-dir models/qwen2.5-7b-instruct-gguf
llama-server -m models/qwen2.5-7b-instruct-gguf/Qwen2.5-7B-Instruct-Q4_K_M.gguf --port 8081 -c 4096 --jinja -ngl 99 &
.venv/bin/python -m jevlab run --config configs/mac-llamacpp.yaml      # includes the exact scorer + agreement check
```

**mlx-lm** (Apple Silicon only; LOC-020, LOC-021)

```bash
.venv/bin/pip install mlx-lm==0.32.0
hf download mlx-community/Qwen2.5-7B-Instruct-4bit --revision c26a38f6a37d0a51b4e9a1eb3026530fa35d9fed \
   --local-dir models/qwen2.5-7b-instruct-mlx-4bit
.venv/bin/mlx_lm.server --model models/qwen2.5-7b-instruct-mlx-4bit --port 8080 &
.venv/bin/python -m jevlab run --config configs/mac-mlx.yaml
```

mlx-lm needs care: its server caps `top_logprobs` at about 10, returns an unsorted top-k with raw BPE pieces (`ĠA`), and has no `response_format`. The config handles this with `token_format: bpe_raw`, `label_position: first`, `max_tokens: 1` and prompt-only JSON. Expect more items below the 0.9 captured-mass threshold with 16 options and only 10 visible tokens.

---

## Verified-on matrix

✅ = executed in this container (Linux x86_64, 4 vCPU, CPU only). 🧪 = exercised only with fake payloads in unit tests. ❌ = not executed here. **Every macOS path is UNTESTED**: no Mac was available.

| Path | Linux CPU (here) | macOS Apple Silicon |
|---|---|---|
| Data: pinned parquet download → seeded splits → JSONL cache | ✅ | untested (pure Python) |
| Metrics, calibration, scoring, CLI (pytest) | ✅ | untested (pure Python) |
| llama-server (llama.cpp 0c1e570, CPU build) — `json_schema` and `logprob_scoring` via `/v1/chat/completions` | ✅ smoke run, N_test = 240 | ❌ UNTESTED (Metal build via brew) |
| llama-server `/tokenize` and `/apply-template` | ✅ | ❌ UNTESTED |
| Ollama 0.40.2 — `json_schema` and `logprob_scoring` via OpenAI-compatible `/v1/chat/completions` | ✅ smoke run, N_test = 240 | ❌ UNTESTED (Ollama.app) |
| Ollama native `/api/chat` logprobs (`logprobs_endpoint: ollama_native`) | 🧪 + one manual request | ❌ UNTESTED |
| Ollama `keep_alive: 0` forced cold start | ✅ | ❌ UNTESTED |
| Exact scorer, llama-cpp-python 0.3.36 on CPU (codes + full-sequence), same GGUF | ✅ | ❌ UNTESTED (`n_gpu_layers: -1`, Metal) |
| Agreement check: server top-20 path vs exact full-vocabulary scorer | ✅ (see results) | ❌ UNTESTED |
| LM Studio (`/v1/chat/completions` JSON; `/v1/responses` logprobs) | 🧪 parser only | ❌ UNTESTED |
| mlx-lm server (bool `logprobs` + int `top_logprobs`, raw BPE pieces) | 🧪 parser only (shape read from the 0.32.0 wheel) | ❌ UNTESTED |
| Thinking-model handling (`<think>` stripping, `reasoning_effort: none`, `enable_thinking: false`) | 🧪 fake `<think>` payloads; params accepted by both servers on a non-thinking model | ❌ UNTESTED with a real thinking model |
| Vendor backends (Jev, Claude) | see [Vendor backends](#vendor-backends-jev-claude): stub ✅, live ❌ | untested |

---

## Swapping models

"Load any model" is one line per backend in the config (`model:`), plus, for code verification, the tokenizer of the same family.

- **Ollama:** `model: llama3.2:3b` (any tag from ollama.com/library or a GGUF imported with `ollama create`). Ollama has no tokenize endpoint, so point `tokenizer: {hf_tokenizer_json: ...}` at that family's `tokenizer.json` (pinned revision), or `{gguf: <path>}`. With no tokenizer the probe still checks empirically that the top token at the answer position is a code, but the codes are not *pre*-verified.
- **llama-server:** restart it with `-m <any.gguf>`; `tokenizer: {server_tokenize: true}` uses the server's own `/tokenize`.
- **LM Studio:** the key shown by `lms ls`.
- **mlx-lm:** any `mlx-community/*` repo downloaded at a pinned revision; the tokenizer is `tokenizer.json` in the same folder.
- **Thinking models** (Qwen3, DeepSeek-R1 distills, gpt-oss): keep `disable_thinking: true`. The adapter sends `reasoning_effort: "none"` and `chat_template_kwargs: {"enable_thinking": false}` (Ollama native: `think: false`). If a `<think>` block still appears and does not close, the probe fails with `unclosed_think_block`.
- **Safety (LL6):** GGUF or safetensors only, never pickle; `trust_remote_code` is never used (the lab uses no `transformers` model code at all); pin repo revisions; treat downloaded files and model cards as untrusted data. Chat templates from GGUF metadata are rendered in jinja2's sandboxed environment.

---

## How the two modes work

**JSON mode (the LLM way).** The system prompt lists `- label: description` lines and asks for `{"label": "<option>"}`; the request carries `response_format: json_schema` with `enum` = the labels. The server's grammar makes the output valid by construction, so `invalid_rate` is about refusals, truncation or prompt-only JSON. For calibration metrics the runner uses the **sequence probability of the generated label tokens** (from the logprobs the server returns) as the confidence of the chosen label and spreads the rest uniformly. Both servers tested here report **pre-constraint** logprobs (LOC-003, LOC-011): the raw model's belief, not a renormalised constrained distribution.

**Logprob scoring (Jev-style emulation).** The prompt lists `A) label: description` lines and asks for the letter only. `jevlab/scoring.py` then:
1. checks each code is one token, with and without a leading space, in the loaded model's tokenizer (`assign_codes`);
2. finds the answer position in the generated tokens (skips whitespace, `Answer:`, a JSON prefix, a `<think>` block);
3. sums the top-logprob mass over every variant of each code (`A`, ` A`, `a`, `A)` ...);
4. reports **captured mass**, the probability on option codes at that position. Below 0.9 the item is re-scored by full-sequence scoring in-process (`fallback:`), or flagged in the log if no fallback is configured.

**Exact scorer (agreement reference).** `jevlab/backends/exact_scorer.py` loads the *same* GGUF in-process with llama-cpp-python, renders the *same* chat template, and reads the *full* vocabulary distribution (no top-k cap). Its `full_sequence` variant scores every option's whole text (`log P(label + '"' | prompt + '{"label": "')`), which handles options that share first tokens (bill_balance / bill_due) and needs no letter codes.

**Probe (LL2).** Every backend × mode is probed on calibration items before any prediction. The probe raises on: empty logprobs, empty top-logprobs, no answer position, captured mass < 0.9, a top token that is not a code, invalid schema output, an unclosed think block, or config flags that cannot work. A failed probe is logged as `PROBE FAILED`, the run continues with the other backends, and the exit code is 2 (`strict: true` aborts instead).

**Outputs.** `results/<run_id>.csv` has one row per backend × mode × calibration state, with the `RunResult` columns (`accuracy_ci95` is split into `_lo`/`_hi`). The `.log` has the probe output, T, ECE/Brier before and after, AURC, accuracy at 50% coverage, the permutation flip rate, the $-equivalent formula and the agreement check. `_reliability.png` shows the reliability diagrams, and `_predictions.jsonl.gz` has every prediction with its distribution and provenance.

---

## Hands-on lab: smoke-run results (LAB, illustrative)

Run `ci-cpu-20261011T062914Z` (files in `lab/results/`): `python -m jevlab run --config configs/ci-cpu.yaml`, 963 s wall time, exit 0, no probe failures. Model: Qwen2.5-0.5B-Instruct Q4_K_M (the same GGUF in all three model backends). Task: `clinc150-banking15+oos`, 16 balanced labels, so chance is 1/16 = 0.0625. N_test = 240, N_calibration = 160. ECE uses 10 equal-mass bins. Every row is tagged `LAB:<backend>:qwen2.5-0.5b-instruct-q4_k_m:Q4_K_M:linux-x86_64-4vcpu-cpu` (C1a: `LAB:c1:tfidf-w12-c25-lr:fp32:linux-cpu-4vcpu`). **These are LAB numbers: illustrative only, not production, not Jev.**

| backend : mode | Accuracy [CI95] | Macro-F1 | ECE raw → scaled (T) | Brier raw → scaled | p50 / p95 / cold (s) | Flip rate | Captured mass | $-equiv per 1k [Guessing] |
|---|---|---|---|---|---|---|---|---|
| llama-server : json_schema | 0.533 [0.471, 0.592] | 0.507 | 0.127 → 0.155 (1.61) | 0.686 → 0.692 | 0.344 / 0.468 / 0.551 | 0.175 | — | 0.012 |
| llama-server : logprob_scoring (letters) | 0.117 [0.079, 0.158] | 0.076 | 0.355 → 0.102 (3.98) | 1.056 → 0.898 | 0.162 / 0.284 / 0.195 | 0.917 | 0.998 | 0.006 |
| ollama : json_schema | 0.517 [0.454, 0.575] | 0.491 | 0.141 → 0.143 (1.63) | 0.696 → 0.697 | 0.301 / 0.406 / 2.469 | 0.217 | — | 0.011 |
| ollama : logprob_scoring (letters) | 0.096 [0.058, 0.133] | 0.062 | 0.363 → 0.106 (3.98) | 1.052 → 0.899 | 0.127 / 0.183 / 2.726 | 0.933 | 0.997 | 0.005 |
| llamacpp-inproc/codes : exact_scoring | 0.113 [0.075, 0.154] | 0.079 | 0.354 → 0.104 (4.17) | 1.054 → 0.899 | 0.087 / 0.128 / 2.896 | 0.933 | 0.997 (full vocab) | 0.003 |
| llamacpp-inproc/full_sequence : exact_scoring | 0.404 [0.346, 0.467] | 0.336 | 0.208 → 0.158 (2.38) | 0.801 → 0.759 | 0.696 / 0.810 / 1.832 | 0.442 | — | 0.024 |
| c1 : classifier (TF-IDF + LR, 50 labels/class; LAB-B) | 0.917 [0.879, 0.950] | 0.916 | 0.124 → 0.018 (0.51) | 0.150 → 0.115 | 0.0014 / 0.0022 / 0.0016 | 0.000 | — | 0.00005 |

Cold latency: Ollama was force-unloaded before its probe (`keep_alive: 0`), so its cold number includes the model load. llama-server already had the model in memory, so its cold number is only the first, uncached request. The exact scorer's cold number includes loading the model in-process.

**Agreement check (gate): PASS.** The server's top-20 logprob path (llama-server) was compared with the in-process exact scorer, which reads the full vocabulary, on the same GGUF and the same rendered prompt (n = 240, 0 fallbacks). Argmax matched on **0.958** of items. Mean |Δp| was **0.033**, taking the strictest reading: the maximum over the 16 options for each item, averaged over items. Mean total variation was 0.045. Captured mass was 0.9976 on the server path and 0.9974 in-process. As an extra check, Ollama against the exact scorer gave 0.950 / 0.033, and Ollama against llama-server gave 0.946 / 0.041. The disagreements are near-ties in the flat letter distributions of a 0.5B model. Three small sources explain them:
- the top-20 truncation floor;
- llama.cpp's prompt cache, whose logits are not bit-identical across batch sizes (LOC-014);
- different thread and batch layouts.

It is not a quantization mismatch: the GGUF file is the same everywhere.

What the run teaches (LAB, 0.5B model):
1. **Letter codes fail at 0.5B.** Logprob scoring with letter codes is near chance (0.10–0.12), and its flip rate is about 0.92: the model picks letters by position, and 109 of 240 llama-server predictions were the same letter. The mechanics are fine, though: captured mass is above 0.99 and the server matches the exact scorer. **Full-sequence scoring of the option names** (0.40) is the more faithful Jev-style emulation for a model this small, and **JSON mode** (0.52–0.53) is better still. A 7B model on a Mac should close much of this gap; that is exercise 1.
2. **Prompt changes did not rescue letter codes** (40 calibration items, llama-server; these items were not used for any reported number):
   - the default prompt scored 0.05;
   - repeating the instruction after the message scored 0.05, with 37/40 answers collapsing to `P` (out_of_scope);
   - repeating the whole option list after the message scored 0.20, at about 5× the latency.
3. **Temperature scaling fixes over-confidence, but only with labels and only for real distributions.**
   - Letter-code ECE fell from 0.36 to 0.10 with T ≈ 4.
   - C1a was *under*-confident (T = 0.51); its ECE fell from 0.124 to 0.018.
   - JSON mode did **not** improve: 0.127 became 0.155 on llama-server. Its "distribution" is one sequence probability with the rest spread uniformly, and the NLL-optimal T is not ECE-optimal on 160 items.
   - All of this used 160 labelled calibration items. That is the lesson about the "calibrated without labels" claim.
4. **Letter scoring halves the latency.** It emits about 2 tokens against about 8 for JSON, so p50 is about 0.13–0.16 s against 0.30–0.34 s on the servers. The in-process exact scorer is fastest at 0.087 s because it has no HTTP and no generation. Full-sequence scoring costs about 0.7 s, since it teacher-forces 16 options.
5. **State length dominates latency.** In exercise 5, `state-sweep` on llama-server (letters, 8–10 items per step) gave these p50 values:
   - 0.17 s with no extra state;
   - 0.92 s with about +220 tokens;
   - 3.3 s with about +860 tokens;
   - 13.5 s with about +1,700 tokens. This last step also includes in-process fallback re-scoring of items whose captured mass fell below 0.9.

   The extra state also distracted the 0.5B model: accuracy fell to 0–0.25 on these small samples.
6. **The classical baseline wins on this task.** C1a with 50 labels per class beats every zero-shot LLM path here, at about 1 ms and about 0.02 ECE after scaling. On a closed intent set with labels available, that is the bar a Jev-like or LLM-like decider has to clear.

---

## Exercises

Each exercise says what to change, what to look at, and what you should expect. "Expected" comes from the smoke run here (tiny model, CPU) or from first principles; your Mac and your model will move the numbers, and that is the point.

### 1. JSON mode vs logprob scoring
**Do:** run any config with both modes; compare the `json_schema` and `logprob_scoring` rows, then the `llamacpp-inproc/full_sequence` row.
**Look at:** accuracy, macro-F1, `invalid_rate`, p50 latency, `mean_output_tokens`.
**Expect:** logprob scoring is cheaper per decision (one or a few output tokens instead of ~8 JSON tokens), so p50 is lower. With a tiny model, letter codes can *cost* accuracy: the model has to map a letter back to an option it read earlier. Full-sequence scoring of the option names usually recovers most of it at a higher compute cost. With 7B+ models the gap between modes should shrink. Note that both modes produce a valid label every time; "type-safe" is not the differentiator, a *wrong valid option* is.

### 2. Calibration before and after temperature scaling
**Do:** compare each backend's `calibrated=False` and `calibrated=True` rows; open `_reliability.png`.
**Look at:** `temperature`, `ece` (10 equal-mass bins), `brier`; the reliability curves vs the diagonal.
**Expect:** raw letter-code distributions from small instruct models are usually **over-confident** (T > 1 softens them); ECE drops after scaling and accuracy is unchanged (T never changes the argmax). Now ask what it cost: 160 labelled calibration items. Jev claims calibrated probabilities with no labels; this exercise shows why that claim is valuable and why it must be tested against Jev itself, not assumed. Try `per_class: {calibration: 3}` in the task config and watch T and test ECE get noisy.

### 3. Option-order bias
**Do:** look at `permutation_flip_rate` (k = 2 permutations on 60 test items; the first is the full reversal). Raise `permutation: {k: 3, n_items: 240}` for a tighter estimate.
**Expect:** a non-trivial flip rate for both LLM modes: the prediction depends on where an option sits in the list (and, in logprob mode, which letter it gets). Small models flip more. The C1a classifier's flip rate is 0 by construction. Jev documents its own option-order bias, so this is a property to measure on any LLM-based decider, not a lab artefact. Averaging over k permutations removes some of it but costs k×.

### 4. Quantization vs ECE
**Do:** download two or three quantizations of the same model (for example `qwen2.5-0.5b-instruct-q4_k_m.gguf`, `-q8_0.gguf`, `-fp16.gguf` from the same pinned repo, or `qwen2.5:7b-instruct-q4_K_M` vs `-q8_0` in Ollama, or MLX 4-bit vs 8-bit). Run the same config once per file, changing only `model:`/`gguf:`.
**Look at:** `quant` column, raw ECE, T, Brier, accuracy, p50.
**Expect:** lower bits change logits, so raw ECE and T move even when accuracy barely changes; Q8 tracks F16 closely, Q4 and below drift more. Latency falls with fewer bits (memory-bandwidth bound). This is why every result row records the quantization (LL4), and why a calibration fitted on one quantization should not be reused on another.

### 5. Latency vs state length
**Do:** `python -m jevlab state-sweep --config configs/ci-cpu.yaml --backend llama-server:logprob_scoring --lengths 0,200,800,2000 --n-items 20` (or your Mac config).
**Look at:** `p50_s`, `mean_input_tokens` per length.
**Expect:** the options/system prompt is a shared prefix that the server caches, so with no state the per-item cost is a few dozen tokens. Each extra state token must be prefilled, so latency grows roughly linearly with state length (prompt processing dominates; the answer is one token). On a Mac GPU the slope should be much flatter than on CPU (expected, not measured here). Compare with Jev, which bills state tokens on every request and has a 32k state limit: in both worlds the state length, not the question, drives cost and latency.

### 6. Emulate Jev's Choice / Score / Noul confidence (`confidence.md`)
**Do:** the run log already prints the mean emulated Choice confidence. For more, load `_predictions.jsonl.gz`:

```python
import gzip, json, numpy as np
from jevlab import metrics as M
from jevlab.data import load_task
rows = [json.loads(l) for l in gzip.open("results/<run_id>_predictions.jsonl.gz", "rt")]
gold = {it.id: it.label for it in load_task("clinc150").items}
r = [x for x in rows if x["backend_mode"] == "llama-server:logprob_scoring" and x["split"] == "test"]
conf = np.array([M.jev_choice_confidence(list(x["probs"].values())) for x in r])   # (p_max - 1/n) / (1 - 1/n)
ok = np.array([x["label"] == gold[x["item_id"]] for x in r])
for t in (0.0, 0.5, 0.9):
    m = conf >= t
    print(f"confidence >= {t}: automate {m.mean():.0%} of items, accuracy on those {ok[m].mean() if m.any() else float('nan'):.3f}")
print("top-2 ratio median:", np.median([M.top2_ratio(list(x["probs"].values())) for x in r]))
```
**Expect:** accuracy rises as you raise the threshold and the automation rate falls: that is the risk-coverage curve (AURC in the log). Before temperature scaling the confidence numbers are over-stated; the same thresholds mean different things after scaling. `M.jev_score_confidence` and `M.jev_noul_confidence` implement the Score and Noul formulas (unit-tested against the doc's worked examples: (0, 0.57, 0.43) → 0.355; (0.9, 0.06, 0.04) → 0.85). The formulas are the vendor's; the probabilities here are a local model's. That is exactly the emulation boundary.

### 7. (Bonus) Jevons fan-out: many questions over one state
**Do:** with llama-server or Ollama running, ask k different Choice questions about the *same* message (intent, urgency, needs-human, sentiment...). Send them as k requests whose prompts put the **state first** and the question last, then as k requests with the question first.
**Expect:** with state-first prompts the server's prefix cache prefills the state once and each extra question costs only its own tokens, so k questions cost far less than k× one question; question-first prompts break the shared prefix and pay the state every time. Jev bills every request's state and question tokens (no cache discount), so cheap per-decision prices invite many speculative questions: the Jevons rebound. Keep a decision budget: every question needs a consumer. LAB-B's `JevBackend.fanout_token_demo` shows the Jev-side token accounting (MOCK).

---

## Troubleshooting

- **Ollama cold starts (`keep_alive`).** Ollama unloads a model after 5 idle minutes by default (LOC-006). The next call pays the model load (seconds, more for bigger models). Set `OLLAMA_KEEP_ALIVE=30m` (server) or `keep_alive` per request; `force_cold_start: true` in a config deliberately unloads first so the run log reports a true cold latency. Report warm and cold latency separately (the CSV has `cold_latency_s`).
- **Thinking models.** If a Qwen3/R1-style model starts with `<think>`, the first-token distribution is about thinking, not the answer. Keep `disable_thinking: true`. If the probe says `unclosed_think_block`, the server ignored the switch: use the model's non-thinking variant, Ollama's native endpoint (`think: false`), or llama-server with `--jinja` and `chat_template_kwargs`.
- **Top-k caps.** Ollama rejects `top_logprobs` > 20 with HTTP 400 (LOC-002); mlx-lm allows about 10; OpenAI-style APIs cap at 20. With more options than visible tokens, some options get no mass. Watch `mean_captured_mass` and the `fallback` count in the log; use fewer options, or full-sequence scoring.
- **Silent empty logprobs.** Some servers accept `logprobs: true` and return nothing (e.g. the omlx issue cited in the critic review; LM Studio's chat-completions endpoint does not document logprobs at all, LOC-017). The probe raises `server returned EMPTY logprobs` instead of degrading to "no confidence". Fix the endpoint (`logprobs_endpoint`) or the server version.
- **Low captured mass.** The model is not answering with a code: it writes the option name, "The answer is", or a quote. Check `probe_top_tokens` in the log. Lower the temperature (the lab uses 0), strengthen "Reply with the letter only", or raise `max_tokens` so the answer position is reached.
- **`top token at label position is not an option code`.** Same cause as above; with mlx-lm make sure `label_position: first` and `max_tokens: 1`.
- **JSON mode invalid outputs.** With a grammar (`supports_json_schema: true`) this should be ~0; if not, the server ignored `response_format` (check the version). mlx-lm has no `response_format`: JSON is prompt-only, and invalid outputs are counted.
- **Exact scorer runs out of memory.** llama-cpp-python 0.3.36 keeps logits only with `logits_all=True` (LOC-022), which allocates n_ctx × vocab × 4 bytes. Lower `n_ctx` (prompts here are < 600 tokens).
- **Server vs exact scorer disagree.** Check the same GGUF file is loaded (sha256), the same chat template (`/apply-template` on llama-server), and that both run at temperature 0. Small |Δp| also comes from prompt-cache batch-size effects (LOC-014) and different thread counts.
- **GitHub downloads blocked.** In this container the proxy blocked github.com release pages for llama.cpp; the llama.cpp source vendored in the PyPI `llama-cpp-python` sdist was used instead.

---

## Vendor backends (Jev, Claude)

> Written by LAB-B (merged from `LEARNING-vendor-section.md`). Everything in this section that came from the stub is **MOCK**. The live paths are **UNTESTED**: no API keys exist in this environment, and Jev is early access with a waitlist.

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
| TF-IDF word 1–2 + char 2–5 | 10 | 0.846 (0.800–0.892) | 0.847 | 0.275 → 0.053 | 1.45 / 2.28 ms | 0.9 s |
| TF-IDF | 50 | 0.908 (0.867–0.946) | 0.907 | 0.122 → 0.022 | 1.44 / 2.73 ms | 2.3 s |
| TF-IDF | 200 (in-scope capped at 100) | 0.938 (0.904–0.967) | 0.938 | 0.091 → 0.023 | 1.42 / 2.10 ms | 4.8 s |
| model2vec potion-base-8M | 50 | 0.925 (0.887–0.958) | 0.925 | 0.116 → 0.030 | 0.16 / 0.49 ms | 1.6 s |

ECE uses 10 equal-mass bins. Latency and training times are noisy, because the container's 4 vCPUs were shared with LAB-A's model runs; rerun the sweep on an idle machine before quoting them. The raw logistic regression is **under**-confident (T ≈ 0.4–0.6 sharpens it). Temperature scaling needs the labelled calibration split, which is exactly the lesson from Jev's "calibrated without labels" pitch. P3 compares the N = 50 row with the lab zero-shot scorer (LAB-A) on the same split.

### Exercises (vendor and baseline)

1. **Fan-out token accounting (P6).** Call `JevBackend.fanout_token_demo(task, item, extra_questions)` against the stub. You should observe that k questions in one request pay the state and the fixed overhead once, while k separate requests pay them k times. The stub's token model is MOCK; redo it live if you have a key.
2. **Self-consistency cost versus resolution.** Run the Claude backend in the stub with `k` ∈ {3, 5, 9}. You should observe that tokens and $ scale k×, while the probability grid is only 1/k. ECE needs real data, so do this live.
3. **Real-time deadline.** Run `curl -XPOST localhost:8765/__stub/config -d '{"delay_ms": 400}'`, then predict with `timeout_s: 0.25`. You should observe `label=None` and `raw.error == "timeout"` in about 0.25 s. With the SDK defaults, the same call would wait.
4. **Label-count sweep (P3).** Edit `sweep.n_per_class` in the `kind: c1` entry of `configs/c1.yaml`, for example `[5, 10, 20, 50, 100]`. You should observe that accuracy climbs fast from N = 5 to 50 and then flattens, and that ECE before temperature scaling falls as N grows.

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
