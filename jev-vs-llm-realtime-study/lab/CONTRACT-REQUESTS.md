## From LAB-B (2026-10-11)

Nothing here blocks LAB-B. Each item has a workaround in place; the lead decides.

1. **`RunResult`: add `train_time_s: float | None` and `n_per_class: int | None`.** C1a must report training time and the label-count N (P3). The workaround is that `results/c1_sweep.csv` appends extra columns after the `RunResult` columns: `n_per_class`, `n_per_class_min`, `n_per_class_max`, `n_train`, `train_time_s`.
2. **`DecisionBackend`: an optional `fit(task) -> dict` hook for trainable backends.** Without it, C1a fits lazily inside `predict()`/`probe()` on the task's train split, so the runner cannot time training separately.
3. **`Prediction`: an optional `usd: float | None`, the per-decision $ cost from the vendor `usage` block.** This would let the runner compute `usd_per_1k_decisions` the same way for every vendor backend. The workaround is that the Jev and Claude backends put it in `raw["usd"]`, with the price parameters in their configs labelled [Guessing].
4. **CSV encoding of `accuracy_ci95`.** c1_sweep.csv writes the tuple as the string `"[lo, hi]"`. Please fix one convention for all results CSVs, so LAB-A's writer and LAB-B's match.
5. **Runner dispatch for LAB-B backends (for LAB-A's `run.py`).** `configs/jev.yaml`, `claude.yaml` and `c1.yaml` follow the `backends:` list schema of `configs/ci-cpu.yaml`, with `kind: jev | claude | c1`. Please dispatch each to `jevlab.backends.<kind>.make_backend(entry)`. It ignores the runner keys `name`, `kind`, `modes` and `quant`, and rejects any other unknown key. All three backends follow the `DecisionBackend` protocol (`probe`, `predict`). Vendor predictions carry `raw["usd"]` and `raw["confidence"]` (Jev). C1a fits lazily on the train split. The `sweep:` block in the c1 entry is used only by `python -m jevlab.backends.c1 --sweep`.
6. **OWNERSHIP.md: add a `jevlab/leakage.py` row, owner LAB-B.** It holds `assert_no_lab_or_mock_in(path)`, the LL5 leakage check for STUDY.md (CLI: `python -m jevlab.leakage STUDY.md`), plus `jevlab/backends/_vendor.py` (shared provenance and key helpers for jev and claude).

## From LAB-A (2026-10-11)

Nothing blocks LAB-A. Contract changes 1–5 are adopted in `jevlab/run.py` (dispatch to `make_backend(entry)`, `fit()` timed as `train_time_s`, `Prediction.usd`, `RunResult.to_row()` for every CSV, LAB-B section merged into LEARNING.md).

1. **OWNERSHIP.md: add `jevlab/prompts.py`, owner LAB-A.** It holds the prompt builders shared by the server adapter and the exact scorer, so both render byte-identical chat prompts (a precondition of the agreement check).
2. **Optional: `Prediction.cold` semantics.** The runner reports `cold_latency_s` from the probe's first call (`probe()["cold_latency_s"]`), then from `raw["cold_latency_s"]`, then from a prediction with `cold=True`. A one-line note in `types.py` saying which one backends should prefer would remove the three-way fallback.
3. **Note for STUDY.md writers:** the CSV `backend` for the in-process scorer is `llamacpp-inproc/codes` or `llamacpp-inproc/full_sequence` (mode `exact_scoring`); the full-sequence row is the most faithful "Jev-style decision primitive (emulation)" for tiny models, because letter codes are near chance at 0.5B (see LEARNING.md smoke results).
