## From LAB-B (2026-10-11)

Nothing here blocks LAB-B. Each item has a workaround in place; the lead decides.

1. **`RunResult`: add `train_time_s: float | None` and `n_per_class: int | None`.** C1a must report training time and the label-count N (P3). The workaround is that `results/c1_sweep.csv` appends extra columns after the `RunResult` columns: `n_per_class`, `n_per_class_min`, `n_per_class_max`, `n_train`, `train_time_s`.
2. **`DecisionBackend`: an optional `fit(task) -> dict` hook for trainable backends.** Without it, C1a fits lazily inside `predict()`/`probe()` on the task's train split, so the runner cannot time training separately.
3. **`Prediction`: an optional `usd: float | None`, the per-decision $ cost from the vendor `usage` block.** This would let the runner compute `usd_per_1k_decisions` the same way for every vendor backend. The workaround is that the Jev and Claude backends put it in `raw["usd"]`, with the price parameters in their configs labelled [Guessing].
4. **CSV encoding of `accuracy_ci95`.** c1_sweep.csv writes the tuple as the string `"[lo, hi]"`. Please fix one convention for all results CSVs, so LAB-A's writer and LAB-B's match.
5. **Runner dispatch convention (for LAB-A's `run.py`).** The config has `backend: <name>` plus a `<name>:` section, and the runner calls `jevlab.backends.<name>.make_backend(cfg[<name>])`. `jev.py`, `claude.py` and `c1.py` all expose `make_backend`. The c1 section also holds `sweep:`, which `make_backend` ignores; the sweep runs through `python -m jevlab.backends.c1 --sweep`.
6. **OWNERSHIP.md: add a `jevlab/leakage.py` row, owner LAB-B.** It holds `assert_no_lab_or_mock_in(path)`, the LL5 leakage check for STUDY.md (CLI: `python -m jevlab.leakage STUDY.md`), plus `jevlab/backends/_vendor.py` (shared provenance and key helpers for jev and claude).
