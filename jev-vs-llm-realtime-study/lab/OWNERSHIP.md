# Local Lab: module ownership (parallel build)

`jevlab/types.py` is the shared contract and is owned by the lead. Only the lead changes it. If you need a change, write it in `lab/CONTRACT-REQUESTS.md` and work around it until the lead updates the contract.

| Module | Owner | Purpose |
|---|---|---|
| `jevlab/types.py` | lead | Shared dataclasses and the `DecisionBackend` protocol |
| `jevlab/data.py` | LAB-A | Download Banking77 and CLINC150, build the subset plus out-of-scope task, create seeded train/calibration/test splits. Signature: `load_task(name: str, n_intents: int = 15, seed: int = 7, per_class: dict[str, int] \| None = None) -> Task` |
| `jevlab/metrics.py` | LAB-A | Accuracy, macro-F1, equal-mass ECE, Brier, reliability data, bootstrap CI, risk–coverage/AURC, permutation flip rate |
| `jevlab/calibration.py` | LAB-A | Temperature scaling, fit on the calibration split only |
| `jevlab/backends/openai_compat.py` | LAB-A | One adapter for Ollama, LM Studio, llama-server and mlx-lm, with capability flags; JSON-schema mode and logprob-scoring mode |
| `jevlab/backends/exact_scorer.py` | LAB-A | In-process, full-sequence option scoring; the agreement reference |
| `jevlab/scoring.py` | LAB-A | Tokenizer-aware option codes, variant merging, label-position search |
| `jevlab/run.py`, `jevlab/__main__.py` | LAB-A | CLI: `python -m jevlab run --config configs/<x>.yaml` |
| `jevlab/backends/jev.py` | LAB-B | TypeSafe SDK backend (Choice question) |
| `jevlab/backends/claude.py` | LAB-B | Anthropic SDK backend (structured outputs) |
| `jevlab/backends/c1.py` | LAB-B | C1a classifier (TF-IDF or embeddings + logistic regression), with a label-count sweep |
| `jevlab/stub_server.py` | LAB-B | Local HTTP stub that replays documented Jev and Anthropic responses (MOCK) |
| `configs/*.yaml` | Both | LAB-A: `ci-cpu`, `mac-*`. LAB-B: `jev`, `claude`, `c1` |
| `tests/` | Both | Each agent tests its own modules. Name files `test_a_*.py` (LAB-A) or `test_b_*.py` (LAB-B) |
| `LEARNING.md` | LAB-A, with a section from LAB-B on the Jev and Claude backends | Mac setup, exercises |
| `requirements.txt` | Both (append only) | — |
