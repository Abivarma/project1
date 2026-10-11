"""Local Lab runner: `python -m jevlab run --config configs/<name>.yaml`. Owner: LAB-A.

For every configured backend x mode:
  probe (LL2, fails loudly) -> predict calibration + test splits -> metrics before and
  after temperature scaling (T fitted on the calibration split only) -> option-order
  permutation test on a test subset -> rows in results/<run_id>.csv.
Also: optional agreement check (server top-logprob path vs in-process exact scorer),
results/<run_id>.log, results/<run_id>_reliability.png, results/<run_id>_predictions.jsonl.gz.

Two config shapes are accepted:
  LAB-A (multi-backend):  backends: [{name, kind, modes, ...}, ...]
  LAB-B (single backend): backend: <c1|jev|claude>, mode: <mode>, <backend>: {section}
                          (the module's make_backend(section) builds it)

ALL NUMBERS FROM THIS RUNNER ARE ILLUSTRATIVE LAB NUMBERS (tiny models, CPU or a Mac,
public data). They are not production numbers and not Jev numbers (PLAN §6, LL5).
"""
from __future__ import annotations

import csv
import dataclasses
import datetime as dt
import importlib
import json
import logging
import platform
import random
import sys
import time
from pathlib import Path
from typing import Any, Sequence

import numpy as np
import yaml

from . import metrics as M
from .calibration import apply_temperature, fit_temperature
from .data import load_task, task_summary
from .types import Item, Prediction, RunResult, Task

LAB_DIR = Path(__file__).resolve().parent.parent
log = logging.getLogger("jevlab")

DISCLAIMER = (
    "LAB numbers: illustrative only (tiny local model / CPU or Mac, public dataset). "
    "Not production numbers, not Jev numbers. The logprob path is a 'Jev-style decision "
    "primitive (emulation)', never 'local Jev'."
)

DEFAULT_COST = {  # all [Guessing]; override in config `cost:`
    "power_w": 65.0,  # whole-machine draw under load
    "usd_per_kwh": 0.15,
    "hardware_usd": 1500.0,
    "amortisation_years": 3.0,
    "utilisation": 0.5,  # fraction of wall-clock the box does useful decisions
}


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
def load_config(path: str | Path) -> dict:
    p = Path(path)
    if not p.is_absolute() and not p.exists():
        p = LAB_DIR / p
    cfg = yaml.safe_load(p.read_text())
    cfg["_path"] = str(p)
    cfg.setdefault("run_name", p.stem)
    if "backends" not in cfg and "backend" in cfg:  # LAB-B single-backend shape
        kind = cfg["backend"]
        cfg["backends"] = [{"name": kind, "kind": kind, "modes": [cfg.get("mode", "vendor")], "section": cfg.get(kind, {})}]
    if not cfg.get("backends"):
        raise ValueError("config has no backends")
    return cfg


def _resolve_path(p: str | None) -> str | None:
    if p is None:
        return None
    q = Path(p)
    return str(q if q.is_absolute() else (LAB_DIR / q))


def _hardware(cfg: dict) -> str:
    return cfg.get("hardware") or f"{platform.system().lower()}-{platform.machine()}"


def build_backends(cfg: dict) -> list[Any]:
    """Instantiate one backend object per (backend entry x mode)."""
    hw = _hardware(cfg)
    built: list[Any] = []
    exact_entries = {b["name"]: b for b in cfg["backends"] if b.get("kind") == "exact_scorer"}

    def exact_from(entry: dict, scoring_kind: str):
        from .backends.exact_scorer import from_config as ex_from

        e = dict(entry)
        e["gguf"] = _resolve_path(e["gguf"])
        e["scoring"] = scoring_kind
        e["name"] = f"{entry['name']}/{scoring_kind}"
        return ex_from(e, hw)

    for b in cfg["backends"]:
        if b.get("enabled", True) is False:
            continue
        kind = b.get("kind", "openai_compat")
        if kind == "openai_compat":
            from .backends.openai_compat import from_config as oa_from

            fb = None
            if b.get("fallback"):
                if b["fallback"] not in exact_entries:
                    raise ValueError(f"{b['name']}: fallback {b['fallback']!r} is not an exact_scorer entry")
                fb = exact_from(exact_entries[b["fallback"]], "full_sequence")
            entry = dict(b)
            if entry.get("tokenizer") and entry["tokenizer"].get("gguf"):
                entry["tokenizer"] = {**entry["tokenizer"], "gguf": _resolve_path(entry["tokenizer"]["gguf"])}
            if entry.get("tokenizer") and entry["tokenizer"].get("hf_tokenizer_json"):
                entry["tokenizer"] = {**entry["tokenizer"], "hf_tokenizer_json": _resolve_path(entry["tokenizer"]["hf_tokenizer_json"])}
            for mode in b.get("modes", ["json_schema", "logprob_scoring"]):
                built.append(oa_from(entry, mode, hw, fallback=fb))
        elif kind == "exact_scorer":
            for s in b.get("scorings", ["codes"]):
                built.append(exact_from(b, s))
        elif kind in ("c1", "jev", "claude"):
            # Contract change 5: make_backend(entry); it ignores name/kind/modes/quant.
            mod = importlib.import_module(f".backends.{kind}", __package__)
            entry = {k: v for k, v in b.items() if k not in ("enabled", "section")}
            if "section" in b:  # legacy single-backend shape: backend: <kind> + <kind>: {...}
                entry = {**b["section"], **{k: entry[k] for k in ("name", "kind", "modes") if k in entry}}
            built.append(mod.make_backend(entry))
        else:
            raise ValueError(f"unknown backend kind {kind!r}")
    return built


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _probs_or_uniform(preds: Sequence[Prediction], labels: Sequence[str]) -> tuple[np.ndarray | None, int]:
    """(n,k) probs; items without a distribution get uniform (counted). None if no item has one."""
    if not any(p.probs for p in preds):
        return None, len(preds)
    k = len(labels)
    rows, filled = [], 0
    for p in preds:
        if p.probs:
            rows.append(p.probs)
        else:  # uniform, tipped by epsilon toward the predicted label so argmax == prediction
            rows.append({l: 1.0 / k + (1e-6 if l == p.label else 0.0) for l in labels})
            filled += 1
    return M.probs_matrix(rows, labels), filled


def _usd_per_1k(preds: Sequence[Prediction], cost: dict) -> tuple[float | None, str]:
    usd = [getattr(p, "usd", None) for p in preds]
    if usd and all(u is not None for u in usd):  # contract change 3
        return 1000 * float(np.mean(usd)), "1000 x mean(Prediction.usd): vendor usage x list price (params in the backend config)"
    usd = [p.raw.get("usd") if isinstance(p.raw, dict) else None for p in preds]
    if usd and all(u is not None for u in usd):
        return 1000 * float(np.mean(usd)), "1000 x mean(raw.usd)"
    if not preds or not preds[0].provenance.startswith("LAB:"):
        return None, "n/a"
    lat = float(np.mean([p.latency_s for p in preds]))
    c = {**DEFAULT_COST, **cost}
    energy = c["power_w"] / 1000 / 3600 * c["usd_per_kwh"]  # $/s
    hw = c["hardware_usd"] / (c["amortisation_years"] * 365 * 24 * 3600 * c["utilisation"])  # $/s
    return 1000 * lat * (energy + hw), "local $-equivalent formula"


def _cold_latency(info: dict, preds: Sequence[Prediction]) -> float | None:
    """Probe's first call if the backend reports it, else a prediction flagged cold."""
    if info.get("cold_latency_s") is not None:
        return float(info["cold_latency_s"])
    for p in preds:
        if isinstance(p.raw, dict) and p.raw.get("cold_latency_s") is not None:
            return float(p.raw["cold_latency_s"])
    cold = [p.latency_s for p in preds if p.cold]
    return float(cold[0]) if cold else None


def _mean_or_none(xs: Sequence[float | None]) -> float | None:
    v = [x for x in xs if x is not None]
    return float(np.mean(v)) if v else None


def _permutations(labels: Sequence[str], k: int, seed: int) -> list[list[str]]:
    rng = random.Random(seed)
    out: list[list[str]] = []
    rev = list(reversed(labels))  # first permutation: full reversal (max position change)
    out.append(rev)
    while len(out) < k:
        p = list(labels)
        rng.shuffle(p)
        if p != list(labels) and p not in out:
            out.append(p)
    return out[:k]


# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------
def run(cfg: dict, out_dir: Path | None = None, limit_test: int | None = None, limit_cal: int | None = None,
        only: Sequence[str] | None = None, permutation: bool = True) -> dict:
    t_start = time.perf_counter()
    out_dir = Path(out_dir or LAB_DIR / "results")
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    run_id = f"{cfg['run_name']}-{stamp}"
    log_path = out_dir / f"{run_id}.log"
    fh = logging.FileHandler(log_path, encoding="utf-8")
    fh.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    log.addHandler(fh)
    if not any(isinstance(h, logging.StreamHandler) and not isinstance(h, logging.FileHandler) for h in log.handlers):
        sh = logging.StreamHandler(sys.stdout)
        sh.setFormatter(logging.Formatter("%(message)s"))
        log.addHandler(sh)
    log.setLevel(logging.INFO)
    try:
        return _run(cfg, out_dir, run_id, log_path, limit_test, limit_cal, only, permutation, t_start)
    finally:
        log.removeHandler(fh)
        fh.close()


def _run(cfg, out_dir, run_id, log_path, limit_test, limit_cal, only, permutation, t_start) -> dict:
    log.info("run_id=%s config=%s", run_id, cfg["_path"])
    log.info(DISCLAIMER)
    tcfg = cfg.get("task", {})
    task = load_task(tcfg.get("name", "clinc150"), n_intents=tcfg.get("n_intents", 15), seed=tcfg.get("seed", 7), per_class=tcfg.get("per_class"))
    lim = cfg.get("limits", {}) or {}
    limit_test = limit_test or lim.get("n_test")
    limit_cal = limit_cal or lim.get("n_calibration")
    test = task.split("test")
    cal = task.split("calibration")
    rng = random.Random(task.seed)
    if limit_test and limit_test < len(test):
        test = sorted(rng.sample(test, limit_test), key=lambda i: i.id)
    if limit_cal and limit_cal < len(cal):
        cal = sorted(rng.sample(cal, limit_cal), key=lambda i: i.id)
    log.info("task=%s source=%s", task.name, task.source)
    log.info("task summary=%s ; used: n_calibration=%d n_test=%d", json.dumps(task_summary(task)), len(cal), len(test))
    labels = list(task.labels)
    hw = _hardware(cfg)
    n_bins = int(cfg.get("ece_bins", 10))
    perm_cfg = {"k": 2, "n_items": 60, "seed": 11, **(cfg.get("permutation") or {})}
    cost = cfg.get("cost") or {}
    log.info("hardware=%s python=%s numpy=%s", hw, platform.python_version(), np.__version__)
    c = {**DEFAULT_COST, **cost}
    log.info(
        "$-equivalent formula (local backends): usd_per_1k = 1000 * mean_latency_s * "
        "(power_W/1000/3600 * usd_per_kWh + hardware_usd / (amortisation_years*365*24*3600*utilisation)); "
        "params [Guessing]: power_W=%s usd_per_kWh=%s hardware_usd=%s amortisation_years=%s utilisation=%s. "
        "Not comparable to API list prices without utilisation assumptions (critic: scope distortion 2).",
        c["power_w"], c["usd_per_kwh"], c["hardware_usd"], c["amortisation_years"], c["utilisation"],
    )

    backends = build_backends(cfg)
    if only:
        backends = [b for b in backends if b.name in only or f"{b.name}:{b.mode}" in only]
    rows: list[RunResult] = []
    reliab: dict[str, dict] = {}
    all_preds: dict[str, dict[str, list[Prediction]]] = {}
    failures: list[str] = []
    perm_items = test[: min(int(perm_cfg["n_items"]), len(test))]
    perms = _permutations(labels, int(perm_cfg["k"]), int(perm_cfg["seed"]))

    for be in backends:
        key = f"{be.name}:{be.mode}"
        log.info("=" * 70)
        log.info("backend %s", key)
        train_time_s, n_per_class = None, None
        try:
            if hasattr(be, "fit"):  # contract change 2: optional fit(task) before probe()
                t_fit = time.perf_counter()
                fit_info = be.fit(task) or {}
                train_time_s = float(fit_info.get("train_time_s", time.perf_counter() - t_fit))
                n_per_class = fit_info.get("n_per_class", fit_info.get("n_per_class_requested"))
                log.info("fit: %s", json.dumps(fit_info, default=str))
            info = be.probe(task)
            log.info("probe OK: %s", json.dumps(info, default=str)[:2000])
        except Exception as e:  # LL2: loud, recorded, never silent
            msg = f"PROBE FAILED for {key}: {type(e).__name__}: {e}"
            log.error(msg)
            failures.append(msg)
            if cfg.get("strict", False):
                raise
            continue
        t0 = time.perf_counter()
        cal_preds = be.predict(task, cal)
        test_preds = be.predict(task, test)
        log.info("predicted %d cal + %d test items in %.1fs", len(cal_preds), len(test_preds), time.perf_counter() - t0)
        all_preds[key] = {"calibration": cal_preds, "test": test_preds}
        for p in test_preds + cal_preds:
            if not (p.provenance.startswith("LAB:") or p.provenance.startswith("MOCK:") or p.provenance.startswith("LIVE:")):
                raise RuntimeError(f"prediction without a LAB/MOCK/LIVE provenance tag: {p.provenance!r}")

        y_test = [it.label for it in test]
        y_pred = [p.label for p in test_preds]
        fallbacks = sum(1 for p in test_preds if "fallback" in str(p.raw.get("method", "")) or "FLAGGED" in str(p.raw.get("method", "")))
        if fallbacks:
            log.info("items routed to full-sequence fallback or flagged (captured mass < threshold): %d/%d", fallbacks, len(test_preds))

        # permutation test
        flip = None
        if permutation and perm_items:
            base = {p.item_id: p.label for p in test_preds}
            base_list = [base[it.id] for it in perm_items]
            perm_preds = []
            for order in perms:
                pp = be.predict(task, perm_items, labels_order=order)
                perm_preds.append([p.label for p in pp])
            flip = M.permutation_flip_rate(base_list, perm_preds)
            log.info("permutation flip rate (k=%d, n=%d, first permutation = reversed order): %.3f", len(perms), len(perm_items), flip)
            all_preds[key]["permutations"] = perm_preds  # type: ignore[assignment]

        probs_test, filled_t = _probs_or_uniform(test_preds, labels)
        probs_cal, filled_c = _probs_or_uniform(cal_preds, labels)
        if probs_test is not None and (filled_t or filled_c):
            log.info("items without a distribution filled with uniform for ECE/Brier/T: test=%d cal=%d", filled_t, filled_c)
        lat = M.latency_percentiles([p.latency_s for p in test_preds])
        usd, usd_how = _usd_per_1k(test_preds, cost)
        prov = test_preds[0].provenance if test_preds else "?"
        common = dict(
            run_id=run_id, task=task.name, backend=be.name, mode=be.mode,
            model=getattr(be, "model", None) or getattr(getattr(be, "cfg", None), "model", None) or getattr(getattr(be, "cfg", None), "model_id", "?"),
            quant=str(getattr(be, "quant", None) or info.get("quant") or "n/a"),
            hardware=getattr(be, "hardware", None) or hw,
            backend_version=str(getattr(be, "backend_version", None) or info.get("backend_version") or info.get("sdk_version") or info.get("sklearn") or "?"),
            provenance=prov, n_test=len(test),
            accuracy=M.accuracy(y_test, y_pred), accuracy_ci95=M.accuracy_ci95(y_test, y_pred),
            macro_f1=M.macro_f1(y_test, y_pred, labels),
            p50_latency_s=lat["p50"], p95_latency_s=lat["p95"],
            cold_latency_s=_cold_latency(info, test_preds + cal_preds),
            mean_input_tokens=_mean_or_none([p.input_tokens for p in test_preds]),
            mean_output_tokens=_mean_or_none([p.output_tokens for p in test_preds]),
            usd_per_1k_decisions=usd,
            mean_captured_mass=_mean_or_none([p.captured_mass for p in test_preds]),
            permutation_flip_rate=flip,
            invalid_rate=float(np.mean([p.label is None for p in test_preds])),
            n_per_class=n_per_class,
            train_time_s=train_time_s,
        )
        log.info("usd_per_1k_decisions=%s (%s)", usd, usd_how)
        if probs_test is None:
            rows.append(RunResult(**common, ece=None, ece_bins=None, ece_binning=None, brier=None, calibrated=False, temperature=None))
            log.info("no probability distribution from this backend: ECE/Brier = n/a")
        else:
            y_idx = M.label_indices(y_test, labels)
            ece0, br0 = M.ece(probs_test, y_idx, n_bins), M.brier(probs_test, y_idx)
            rows.append(RunResult(**common, ece=ece0, ece_bins=n_bins, ece_binning="equal-mass", brier=br0, calibrated=False, temperature=None))
            fit = fit_temperature(cal, probs_cal, labels)  # refuses non-calibration items
            pt = apply_temperature(probs_test, fit.T)
            ece1, br1 = M.ece(pt, y_idx, n_bins), M.brier(pt, y_idx)
            # temperature scaling never changes the argmax, so accuracy/F1 are identical by construction
            rows.append(RunResult(**common, ece=ece1, ece_bins=n_bins, ece_binning="equal-mass", brier=br1, calibrated=True, temperature=fit.T))
            _, _, aurc0 = M.risk_coverage(probs_test.max(1), (probs_test.argmax(1) == y_idx).astype(float))
            log.info("T=%.3f fitted on %d calibration items (NLL %.3f -> %.3f)", fit.T, fit.n_fit, fit.nll_before, fit.nll_after)
            log.info("ECE(%d equal-mass bins) %.4f -> %.4f ; Brier %.4f -> %.4f ; AURC %.4f ; acc@50%%coverage %.3f",
                     n_bins, ece0, ece1, br0, br1, aurc0, M.accuracy_at_coverage(probs_test.max(1), (probs_test.argmax(1) == y_idx).astype(float), 0.5))
            reliab[key] = {"before": M.reliability_data(probs_test, y_idx, n_bins), "after": M.reliability_data(pt, y_idx, n_bins), "ece_before": ece0, "ece_after": ece1, "T": fit.T, "prov": prov}
            # Jev-style confidence summary (confidence.md Choice formula)
            jc = [M.jev_choice_confidence(r) for r in probs_test]
            log.info("Jev-style Choice confidence (emulated formula) mean=%.3f ; share >= 0.5: %.2f", float(np.mean(jc)), float(np.mean(np.array(jc) >= 0.5)))
        r = rows[-1]
        log.info("RESULT %s acc=%.3f [%.3f, %.3f] macroF1=%.3f p50=%.3fs p95=%.3fs cold=%s invalid=%.3f captured=%s flip=%s",
                 key, r.accuracy, r.accuracy_ci95[0], r.accuracy_ci95[1], r.macro_f1, r.p50_latency_s, r.p95_latency_s,
                 f"{r.cold_latency_s:.3f}s" if r.cold_latency_s is not None else "n/a", r.invalid_rate,
                 f"{r.mean_captured_mass:.3f}" if r.mean_captured_mass is not None else "n/a",
                 f"{r.permutation_flip_rate:.3f}" if r.permutation_flip_rate is not None else "n/a")

    agreement = None
    if cfg.get("agreement"):
        agreement = agreement_check(cfg["agreement"], all_preds, labels)

    csv_path = out_dir / f"{run_id}.csv"
    write_csv(rows, csv_path)
    pred_path = out_dir / f"{run_id}_predictions.jsonl.gz"
    write_predictions(all_preds, pred_path)
    png_path = None
    if reliab:
        png_path = out_dir / f"{run_id}_reliability.png"
        plot_reliability(reliab, png_path, n_bins, task.name)
    log.info("=" * 70)
    log.info("wrote %s (%d rows), %s, %s%s", csv_path.name, len(rows), log_path.name, pred_path.name, f", {png_path.name}" if png_path else "")
    if failures:
        log.error("%d backend(s) FAILED their probe:\n  %s", len(failures), "\n  ".join(failures))
    log.info("total wall time %.1fs", time.perf_counter() - t_start)
    log.info(DISCLAIMER)
    return {"run_id": run_id, "csv": str(csv_path), "log": str(log_path), "png": str(png_path) if png_path else None,
            "rows": rows, "failures": failures, "agreement": agreement}


# ---------------------------------------------------------------------------
# Agreement check (gate): server top-logprob path vs in-process exact scorer
# ---------------------------------------------------------------------------
def agreement_check(acfg: dict, all_preds: dict, labels: Sequence[str]) -> dict | None:
    s_key, r_key = acfg["server"], acfg["reference"]
    if s_key not in all_preds or r_key not in all_preds:
        log.error("AGREEMENT CHECK SKIPPED: missing %s or %s (probe failed or not configured)", s_key, r_key)
        return None
    sp = {p.item_id: p for p in all_preds[s_key]["test"]}
    rp = {p.item_id: p for p in all_preds[r_key]["test"]}
    ids = [i for i in sp if i in rp and sp[i].probs and rp[i].probs]
    excluded_fallback = [i for i in ids if "fallback" in str(sp[i].raw.get("method", ""))]
    ids_tl = [i for i in ids if i not in excluded_fallback]
    match = [max(labels, key=lambda l: sp[i].probs[l]) == max(labels, key=lambda l: rp[i].probs[l]) for i in ids_tl]
    d_max = [max(abs(sp[i].probs[l] - rp[i].probs[l]) for l in labels) for i in ids_tl]
    d_top = [abs(sp[i].probs[max(labels, key=lambda l: rp[i].probs[l])] - rp[i].probs[max(labels, key=lambda l: rp[i].probs[l])]) for i in ids_tl]
    tvd = [0.5 * sum(abs(sp[i].probs[l] - rp[i].probs[l]) for l in labels) for i in ids_tl]
    cm_s = [sp[i].captured_mass for i in ids_tl if sp[i].captured_mass is not None]
    cm_r = [rp[i].captured_mass for i in ids_tl if rp[i].captured_mass is not None]
    res = {
        "server": s_key, "reference": r_key, "n_items": len(ids_tl), "n_server_fallback_excluded": len(excluded_fallback),
        "argmax_match": float(np.mean(match)) if match else float("nan"),
        "mean_abs_dp_max_over_options": float(np.mean(d_max)) if d_max else float("nan"),
        "mean_abs_dp_reference_top_option": float(np.mean(d_top)) if d_top else float("nan"),
        "mean_total_variation": float(np.mean(tvd)) if tvd else float("nan"),
        "mean_captured_mass_server_topk": float(np.mean(cm_s)) if cm_s else None,
        "mean_captured_mass_exact_fullvocab": float(np.mean(cm_r)) if cm_r else None,
    }
    res["pass"] = bool(res["argmax_match"] >= 0.95 and res["mean_abs_dp_max_over_options"] <= 0.05)
    log.info("=" * 70)
    log.info("AGREEMENT CHECK (gate: argmax match >= 0.95 and mean |dp| <= 0.05; |dp| = max over options per item, the strictest reading)")
    log.info(json.dumps(res, indent=1))
    log.info("AGREEMENT %s", "PASS" if res["pass"] else "FAIL (see explanation in LEARNING.md / log)")
    return res


# ---------------------------------------------------------------------------
# Writers
# ---------------------------------------------------------------------------
def _fmt(v: Any) -> Any:
    if isinstance(v, float):
        return f"{v:.6g}"
    return "" if v is None else v


def write_csv(rows: Sequence[RunResult], path: Path) -> None:
    """Contract change 4: the one CSV convention is RunResult.to_row()."""
    if not rows:
        path.write_text("")
        return
    fields = list(rows[0].to_row().keys())
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for r in rows:
            w.writerow({k: _fmt(v) for k, v in r.to_row().items()})


def write_predictions(all_preds: dict, path: Path) -> None:
    import gzip

    with gzip.open(path, "wt", encoding="utf-8") as f:
        for key, splits in all_preds.items():
            for split in ("calibration", "test"):
                for p in splits.get(split, []):
                    rec = {
                        "backend_mode": key, "split": split, "item_id": p.item_id, "label": p.label,
                        "probs": {k: round(v, 5) for k, v in p.probs.items()} if p.probs else None,
                        "latency_s": round(p.latency_s, 5), "input_tokens": p.input_tokens, "output_tokens": p.output_tokens,
                        "captured_mass": None if p.captured_mass is None else round(p.captured_mass, 5),
                        "provenance": p.provenance, "method": p.raw.get("method") if isinstance(p.raw, dict) else None,
                        "usd": getattr(p, "usd", None),
                    }
                    f.write(json.dumps(rec) + "\n")


def plot_reliability(reliab: dict, path: Path, n_bins: int, task_name: str) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    surface, ink, ink2, muted, grid = "#fcfcfb", "#0b0b0b", "#52514e", "#898781", "#e1e0d9"
    before_c, after_c = "#2a78d6", "#eb6834"  # validated categorical slots 1-2 (dataviz palette)
    keys = list(reliab)
    n = len(keys)
    cols = min(3, n)
    rows_ = int(np.ceil(n / cols))
    fig, axes = plt.subplots(rows_, cols, figsize=(4.2 * cols, 4.2 * rows_ + 0.6), squeeze=False, facecolor=surface)
    for ax, key in zip(axes.flat, keys):
        d = reliab[key]
        ax.set_facecolor(surface)
        ax.plot([0, 1], [0, 1], color=muted, lw=1, ls=(0, (4, 3)), zorder=1)
        for which, color, marker, ls in (("before", before_c, "o", "-"), ("after", after_c, "s", "--")):
            xs = [r["conf_mean"] for r in d[which]]
            ys = [r["acc"] for r in d[which]]
            ax.plot(xs, ys, color=color, lw=2, ls=ls, marker=marker, ms=6, markeredgecolor=surface, markeredgewidth=1.5, zorder=3)
        ax.set_xlim(0, 1)
        ax.set_ylim(0, 1)
        ax.set_aspect("equal")
        ax.grid(color=grid, lw=0.6)
        for s_ in ("top", "right"):
            ax.spines[s_].set_visible(False)
        for s_ in ("left", "bottom"):
            ax.spines[s_].set_color("#c3c2b7")
        ax.tick_params(colors=muted, labelsize=8)
        ax.set_title(f"{key}\nECE raw {d['ece_before']:.3f}  ->  T={d['T']:.2f}: {d['ece_after']:.3f}", fontsize=9, color=ink, loc="left")
        ax.set_xlabel("mean confidence (top option)", fontsize=8, color=ink2)
        ax.set_ylabel("accuracy", fontsize=8, color=ink2)
    for ax in list(axes.flat)[n:]:
        ax.axis("off")
    from matplotlib.lines import Line2D

    handles = [
        Line2D([], [], color=before_c, lw=2, ls="-", marker="o", label="raw probabilities"),
        Line2D([], [], color=after_c, lw=2, ls="--", marker="s", label="after temperature scaling (T fit on calibration split)"),
        Line2D([], [], color=muted, lw=1, ls=(0, (4, 3)), label="perfect calibration"),
    ]
    fig.suptitle(f"Reliability, {task_name}, test split, {n_bins} equal-mass bins. LAB numbers: illustrative only", fontsize=10, color=ink, x=0.01, ha="left")
    fig.tight_layout(rect=(0, 0, 1, 0.93))
    leg = fig.legend(handles=handles, loc="upper left", bbox_to_anchor=(0.01, 0.965), ncol=3, frameon=False, fontsize=8.5)
    for t in leg.get_texts():
        t.set_color(ink2)
    fig.savefig(path, dpi=130, facecolor=surface)
    plt.close(fig)


# ---------------------------------------------------------------------------
# Exercise helper: latency vs state length
# ---------------------------------------------------------------------------
def state_sweep(cfg: dict, backend_key: str, lengths: Sequence[int], n_items: int = 20) -> list[dict]:
    """Prepend ~L words of earlier conversation (train-split utterances) to each test item.

    The options/system prompt stays identical, so prefix caching still covers it; only the
    per-item state grows, which is what a real support conversation does. Returns one row
    per length with p50/p95 latency, mean input tokens and accuracy. LAB numbers only.
    """
    tcfg = cfg.get("task", {})
    task = load_task(tcfg.get("name", "clinc150"), n_intents=tcfg.get("n_intents", 15), seed=tcfg.get("seed", 7), per_class=tcfg.get("per_class"))
    bes = [b for b in build_backends(cfg) if f"{b.name}:{b.mode}" == backend_key]
    if not bes:
        raise ValueError(f"no backend {backend_key!r} in config")
    be = bes[0]
    be.probe(task)
    filler_words = " ".join(it.text for it in task.split("train")).split()
    rows = []
    for L in lengths:
        items = []
        for j, it in enumerate(task.split("test")[:n_items]):
            # a different slice per item, so the server's prefix cache cannot reuse one item's state for the next
            start = (j * 997) % max(1, len(filler_words) - L)
            hist = " ".join(filler_words[start:start + L])
            items.append(dataclasses.replace(it, text=(f"(earlier in this conversation: {hist})\nLatest message: {it.text}" if L else it.text)))
        preds = be.predict(task, items)
        lat = M.latency_percentiles([p.latency_s for p in preds])
        row = {"state_words": L, "p50_s": round(lat["p50"], 4), "p95_s": round(lat["p95"], 4),
               "mean_input_tokens": _mean_or_none([p.input_tokens for p in preds]),
               "accuracy": M.accuracy([it.label for it in items], [p.label for p in preds]), "provenance": preds[0].provenance}
        rows.append(row)
        print(json.dumps(row))
    return rows
