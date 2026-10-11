"""C1a classical baseline: TF-IDF (word + char n-grams) or a small static sentence embedding,
then multinomial logistic regression. MEASURED here on CPU. Owner: LAB-B.

This is the only first-party measured non-LLM baseline in the study (critic fix 11). It feeds
hypothesis P3: "C1a at N=50 per class is within 2 accuracy points of the lab zero-shot scorer"
(falsified if C1a@N=50 is > 2 points below it on the held-out test split, bootstrap 95% CI).

Protocol (LL4)
--------------
- Data: jevlab.data.load_task (LAB-A); the TEST split is asserted identical to the default task's test
  split, i.e. the same items LAB-A's zero-shot scorer is evaluated on.
- Label-count sweep: N per class drawn from the TRAIN split only, as nested seeded prefixes
  (N=10 subset of N=50 subset of N=200). When a class has fewer than N train items, all are used and the
  effective min/max per class is logged (CLINC150 caps in-scope classes at 100 train items).
- Temperature scaling: T fitted on the CALIBRATION split only (never on test), applied to log-probs.
- Metrics on TEST: accuracy (+ bootstrap CI95), macro-F1, ECE (10 equal-mass bins), Brier, before and
  after temperature scaling, using LAB-A's jevlab.metrics (and jevlab.calibration when present).
- Latency: per-item wall clock of featurise + predict_proba for ONE utterance, warm (after warm-up),
  single-threaded BLAS (one worker per core); cold = first call after fit. Training time = wall clock fit.
- Model safety (LL6): the embedding variant loads safetensors only, pinned revision, no remote code.

Provenance: "LAB:c1:<model>:fp32:linux-cpu-4vcpu".
Run: python -m jevlab.backends.c1 --sweep [--config configs/c1.yaml]
"""
from __future__ import annotations

import argparse
import csv
import dataclasses
import math
import platform
import random
import sys
import time
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

import numpy as np
import sklearn
from scipy.optimize import minimize_scalar
from scipy.special import log_softmax
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import FeatureUnion
from threadpoolctl import threadpool_limits

from jevlab.types import Item, Prediction, RunResult, Task

LAB_DIR = Path(__file__).resolve().parents[2]
HARDWARE = "linux-cpu-4vcpu"

# Pinned embedding model (LL6): safetensors weights, MIT licence, ~30 MB, static (no transformer forward pass).
EMBED_REPO = "minishlab/potion-base-8M"
EMBED_REVISION = "bf8b056651a2c21b8d2565580b8569da283cab23"
EMBED_FILES = ("config.json", "model.safetensors", "tokenizer.json")

RUNNER_KEYS = ("name", "kind", "modes", "quant")  # keys of a runner `backends:` entry that are not backend settings


@dataclass
class C1Config:
    features: str = "tfidf"  # "tfidf" | "model2vec"
    n_per_class: int | None = None  # None -> all train items (used by predict()'s lazy fit)
    C: float = 10.0  # fixed a priori (no tuning on test or calibration)
    max_iter: int = 3000
    seed: int = 7
    word_ngrams: tuple[int, int] = (1, 2)
    char_ngrams: tuple[int, int] = (2, 5)
    embed_repo: str = EMBED_REPO
    embed_revision: str = EMBED_REVISION
    embed_dir: str = "models/potion-base-8M"
    latency_threads: int = 1
    warmup: int = 20
    hardware: str = HARDWARE
    # [Guessing; range 0.02-0.10] on-demand USD per vCPU-hour, for a $-equivalent per 1k decisions.
    usd_per_vcpu_hour: float = 0.0425

    @classmethod
    def from_dict(cls, d: Mapping[str, Any]) -> "C1Config":
        unknown = set(d) - set(cls.__dataclass_fields__) - {"sweep"}  # 'sweep' is read by run_sweep only
        if unknown:  # fail loudly on config typos (LL2 spirit)
            raise ValueError(f"unknown c1 config keys: {sorted(unknown)}")
        kw = {k: v for k, v in d.items() if k in cls.__dataclass_fields__}
        for k in ("word_ngrams", "char_ngrams"):
            if k in kw:
                kw[k] = tuple(kw[k])
        return cls(**kw)

    @property
    def model_id(self) -> str:
        if self.features == "tfidf":
            w, c = self.word_ngrams, self.char_ngrams
            return f"tfidf-w{w[0]}{w[1]}-c{c[0]}{c[1]}-lr"
        if self.features == "model2vec":
            return f"potion-base-8M@{self.embed_revision[:7]}-lr"
        raise ValueError(f"unknown features {self.features!r}")


# ------------------------------------- features ----------------------------------------
_EMBED_CACHE: dict[str, object] = {}


class _Model2VecFeaturizer:
    """Static sentence embedding via the model2vec package (safetensors only, pinned revision).

    Loaded once per process and reused across fits; load time is NOT counted as training time."""

    def __init__(self, cfg: C1Config) -> None:
        local = (LAB_DIR / cfg.embed_dir / cfg.embed_revision).resolve()
        key = str(local)
        if key not in _EMBED_CACHE:
            if not all((local / f).exists() for f in EMBED_FILES):
                from huggingface_hub import hf_hub_download

                for fname in EMBED_FILES:  # only these files; no pickles, no code
                    # hf_hub_download(repo_id, filename, *, revision, local_dir)
                    # docs: https://huggingface.co/docs/huggingface_hub/package_reference/file_download
                    hf_hub_download(cfg.embed_repo, fname, revision=cfg.embed_revision, local_dir=local)
            from model2vec import StaticModel

            # StaticModel.from_pretrained(path) reads model.safetensors (safetensors.safe_open, numpy),
            # tokenizer.json and config.json only.
            _EMBED_CACHE[key] = StaticModel.from_pretrained(str(local))
        self.model = _EMBED_CACHE[key]

    def fit(self, texts: Sequence[str]) -> "_Model2VecFeaturizer":
        return self

    def transform(self, texts: Sequence[str]) -> np.ndarray:
        return np.asarray(self.model.encode(list(texts)), dtype=np.float32)


def _make_featurizer(cfg: C1Config):
    if cfg.features == "tfidf":
        return FeatureUnion([
            ("word", TfidfVectorizer(analyzer="word", ngram_range=cfg.word_ngrams, sublinear_tf=True,
                                     lowercase=True, min_df=1)),
            ("char", TfidfVectorizer(analyzer="char_wb", ngram_range=cfg.char_ngrams, sublinear_tf=True,
                                     lowercase=True, min_df=1)),
        ])
    if cfg.features == "model2vec":
        return _Model2VecFeaturizer(cfg)
    raise ValueError(f"unknown features {cfg.features!r}")


# ------------------------------------ sampling ------------------------------------------
def sample_train(task: Task, n_per_class: int | None, seed: int) -> list[Item]:
    """Nested seeded prefix of each class's TRAIN items (never touches calibration/test)."""
    by_label: dict[str, list[Item]] = defaultdict(list)
    for it in task.split("train"):
        by_label[it.label].append(it)
    out: list[Item] = []
    for lab in task.labels:
        pool = sorted(by_label.get(lab, []), key=lambda it: it.id)
        random.Random(f"{seed}:c1:{lab}").shuffle(pool)
        out.extend(pool if n_per_class is None else pool[:n_per_class])
    return out


# ------------------------------------ temperature ---------------------------------------
def fit_temperature(logp: np.ndarray, y_idx: np.ndarray) -> float:
    """Fallback temperature scaling (NLL on the calibration split). Prefer jevlab.calibration if present."""
    def nll(log_t: float) -> float:
        z = log_softmax(logp / math.exp(log_t), axis=1)
        return float(-z[np.arange(len(y_idx)), y_idx].mean())

    res = minimize_scalar(nll, bounds=(-4.0, 4.0), method="bounded")
    return float(math.exp(res.x))


def _lab_a_temperature():
    """LAB-A's jevlab.calibration (fit_temperature(items, probs, labels) -> TemperatureFit,
    apply_temperature(probs, T)), which refuses non-calibration items. None if unavailable."""
    try:
        from jevlab import calibration  # type: ignore
    except ImportError:
        return None
    if not (hasattr(calibration, "fit_temperature") and hasattr(calibration, "apply_temperature")):
        return None
    return calibration


def apply_temperature(logp: np.ndarray, t: float) -> np.ndarray:
    """softmax(log p / T). Uses LAB-A's implementation when present (same formula, clips p at 1e-12)."""
    cal = _lab_a_temperature()
    if cal is not None:
        return cal.apply_temperature(np.exp(logp), t)
    return np.exp(log_softmax(logp / t, axis=1))


# ------------------------------------- backend ------------------------------------------
class C1Backend:
    """DecisionBackend for C1a. predict() fits lazily on the task's train split if not fitted."""

    name = "c1"
    mode = "classifier"

    def __init__(self, config: C1Config | Mapping[str, Any] | None = None) -> None:
        self.cfg = config if isinstance(config, C1Config) else C1Config.from_dict(config or {})
        self.featurizer = None
        self.clf: LogisticRegression | None = None
        self.fitted_task: str | None = None
        self.labels: tuple[str, ...] = ()
        self.temperature: float | None = None
        self.calibration_fit: Any = None
        self.train_info: dict[str, Any] = {}

    @property
    def provenance(self) -> str:
        return f"LAB:c1:{self.cfg.model_id}:fp32:{self.cfg.hardware}"

    def fit(self, task: Task, n_per_class: int | None = None) -> dict:
        train = sample_train(task, n_per_class, self.cfg.seed)
        counts = Counter(it.label for it in train)
        missing = [lab for lab in task.labels if counts.get(lab, 0) == 0]
        if missing:
            raise RuntimeError(f"C1a: no train items for labels {missing}; cannot fit a full distribution")
        texts = [it.text for it in train]
        y = np.array([task.labels.index(it.label) for it in train])
        feat = _make_featurizer(self.cfg)  # model load (if any) happens here, outside the training timer
        t0 = time.perf_counter()
        x = feat.fit(texts).transform(texts) if self.cfg.features != "tfidf" else feat.fit_transform(texts)
        clf = LogisticRegression(C=self.cfg.C, max_iter=self.cfg.max_iter, random_state=self.cfg.seed)
        clf.fit(x, y)
        train_time = time.perf_counter() - t0
        if list(clf.classes_) != list(range(len(task.labels))):
            raise RuntimeError("C1a: classifier classes do not cover task.labels")
        self.featurizer, self.clf, self.fitted_task, self.labels = feat, clf, task.name, task.labels
        self.temperature = None
        self.train_info = {"n_train": len(train), "n_per_class_requested": n_per_class,
                           "n_per_class_min": min(counts.values()), "n_per_class_max": max(counts.values()),
                           "train_time_s": train_time}
        return dict(self.train_info)

    def _ensure_fitted(self, task: Task) -> None:
        if self.clf is None or self.fitted_task != task.name or self.labels != task.labels:
            self.fit(task, self.cfg.n_per_class)

    def log_proba(self, texts: Sequence[str]) -> np.ndarray:
        assert self.clf is not None and self.featurizer is not None
        return self.clf.predict_log_proba(self.featurizer.transform(list(texts)))

    def timed_log_proba(self, items: Sequence[Item]) -> tuple[np.ndarray, list[float], float]:
        """Per-item (batch size 1) warm latency; returns (logp, latencies_s, cold_latency_s)."""
        with threadpool_limits(limits=self.cfg.latency_threads):
            t0 = time.perf_counter()
            self.log_proba([items[0].text])  # cold: first call after fit
            cold = time.perf_counter() - t0
            for it in items[: self.cfg.warmup]:
                self.log_proba([it.text])
            rows, lats = [], []
            for it in items:
                t0 = time.perf_counter()
                rows.append(self.log_proba([it.text])[0])
                lats.append(time.perf_counter() - t0)
        return np.vstack(rows), lats, cold

    def fit_calibration(self, task: Task) -> float:
        """Fit T on the CALIBRATION split only."""
        cal = task.split("calibration")
        if not cal:
            raise RuntimeError("C1a: task has no calibration split")
        logp = self.log_proba([it.text for it in cal])
        lab_a = _lab_a_temperature()
        if lab_a is not None:
            self.calibration_fit = lab_a.fit_temperature(cal, np.exp(logp), task.labels)  # raises on leakage
            self.temperature = float(self.calibration_fit.T)
        else:
            y = np.array([task.labels.index(it.label) for it in cal])
            self.temperature = fit_temperature(logp, y)
        return self.temperature

    # ------------------------------- DecisionBackend ----------------------------------
    def predict(self, task: Task, items: Sequence[Item], labels_order: Sequence[str] | None = None) -> list[Prediction]:
        # labels_order is irrelevant: a classifier has no option presentation order (flip rate is 0 by construction).
        self._ensure_fitted(task)
        logp, lats, cold = self.timed_log_proba(items)
        probs = np.exp(logp) if self.temperature is None else apply_temperature(logp, self.temperature)
        out = []
        for i, it in enumerate(items):
            p = {lab: float(probs[i, j]) for j, lab in enumerate(task.labels)}
            out.append(Prediction(item_id=it.id, label=task.labels[int(probs[i].argmax())], probs=p,
                                  latency_s=lats[i], input_tokens=None, output_tokens=None,
                                  provenance=self.provenance, cold=False,
                                  raw={"temperature": self.temperature, "cold_latency_s": cold if i == 0 else None}))
        return out

    def probe(self, task: Task) -> dict:
        self._ensure_fitted(task)
        p = self.predict(task, (task.split("test") or list(task.items))[:3])
        for x in p:
            if x.probs is None or not math.isclose(sum(x.probs.values()), 1.0, abs_tol=1e-6):
                raise RuntimeError("C1a probe: probabilities do not sum to 1")
            if set(x.probs) != set(task.labels):
                raise RuntimeError("C1a probe: distribution does not cover task.labels")
        return {"backend": self.name, "provenance": self.provenance, "has_distribution": True,
                "sklearn": sklearn.__version__, **self.train_info}


# --------------------------------------- sweep ------------------------------------------
EXTRA_COLS = ("n_per_class", "n_per_class_min", "n_per_class_max", "n_train", "train_time_s")


def _metrics():
    from jevlab import metrics  # LAB-A

    return metrics


def _evaluate(task: Task, backend: C1Backend, logp_test: np.ndarray, lats: list[float], cold: float,
              n_req: int, calibrated: bool, run_tag: str) -> tuple[RunResult, dict]:
    m = _metrics()
    test = task.split("test")
    y_true = [it.label for it in test]
    probs = apply_temperature(logp_test, backend.temperature) if calibrated else np.exp(logp_test)
    y_pred = [task.labels[int(i)] for i in probs.argmax(axis=1)]
    s = m.summarize(y_true, y_pred, task.labels, probs=probs, n_bins=10, n_boot=2000, seed=0)
    lat = m.latency_percentiles(lats)
    mean_lat = float(np.mean(lats))
    usd_1k = mean_lat * 1000 / 3600 * backend.cfg.usd_per_vcpu_hour * backend.cfg.latency_threads
    ti = backend.train_info
    rr = RunResult(
        run_id=f"{run_tag}-N{n_req}-{'ts' if calibrated else 'raw'}",
        task=task.name, backend="c1", mode="classifier", model=backend.cfg.model_id, quant="fp32",
        hardware=backend.cfg.hardware, backend_version=f"scikit-learn {sklearn.__version__}",
        provenance=backend.provenance, n_test=len(test),
        accuracy=s["accuracy"], accuracy_ci95=tuple(s["accuracy_ci95"]), macro_f1=s["macro_f1"],
        ece=s["ece"], ece_bins=s["ece_bins"], ece_binning=s["ece_binning"], brier=s["brier"],
        calibrated=calibrated, temperature=backend.temperature if calibrated else None,
        p50_latency_s=lat["p50"], p95_latency_s=lat["p95"], cold_latency_s=cold,
        mean_input_tokens=None, mean_output_tokens=None, usd_per_1k_decisions=usd_1k,
        mean_captured_mass=None, permutation_flip_rate=0.0, invalid_rate=s["invalid_rate"],
    )
    extra = {"n_per_class": n_req, "n_per_class_min": ti["n_per_class_min"],
             "n_per_class_max": ti["n_per_class_max"], "n_train": ti["n_train"],
             "train_time_s": ti["train_time_s"], "nll": s.get("nll"), "aurc": s.get("aurc"), "p99": lat["p99"]}
    return rr, extra


def _row(rr: RunResult, extra: dict) -> dict:
    d = dataclasses.asdict(rr)
    lo, hi = d.pop("accuracy_ci95")
    d["accuracy_ci95"] = f"[{lo:.4f}, {hi:.4f}]"
    for k in EXTRA_COLS:
        d[k] = extra[k]
    return d


def run_sweep(sweep_cfg: Mapping[str, Any], out_csv: Path, out_log: Path) -> list[dict]:
    from jevlab.data import load_task  # LAB-A

    tasks = sweep_cfg.get("tasks") or [{"name": "clinc150", "n_intents": 15, "seed": 7}]
    feats = sweep_cfg.get("features") or ["tfidf"]
    ns = sweep_cfg.get("n_per_class") or [10, 50, 200]
    base = {k: v for k, v in sweep_cfg.items() if k not in ("tasks", "features", "n_per_class")}
    rows: list[dict] = []
    log: list[str] = []

    def say(msg: str) -> None:
        print(msg, flush=True)
        log.append(msg)

    say(f"# C1a label-count sweep  ({time.strftime('%Y-%m-%d %H:%M:%S %Z')})")
    say(f"# python {platform.python_version()}  scikit-learn {sklearn.__version__}  numpy {np.__version__}  "
        f"platform {platform.platform()}  cpus {__import__('os').cpu_count()}")
    say("# Provenance LAB = measured in this container on public data; NOT a production number.")
    say("# Latency: batch size 1, warm, single-threaded BLAS. usd_per_1k = mean_latency_s*1000/3600*usd_per_vcpu_hour "
        f"(usd_per_vcpu_hour={base.get('usd_per_vcpu_hour', C1Config.usd_per_vcpu_hour)} [Guessing; range 0.02-0.10]).")
    say("# permutation_flip_rate=0.0 is structural (a classifier has no option order), not measured.")
    cal_mod = _lab_a_temperature()
    say(f"# temperature scaling: {'jevlab.calibration.fit_temperature (LAB-A)' if cal_mod is not None else 'c1.fit_temperature fallback (NLL, bounded log-T search)'}; fitted on the calibration split only")
    for tcfg in tasks:
        name, n_int, seed = tcfg.get("name", "clinc150"), int(tcfg.get("n_intents", 15)), int(tcfg.get("seed", 7))
        ref = load_task(name, n_intents=n_int, seed=seed)  # default per_class = LAB-A's split
        big = load_task(name, n_intents=n_int, seed=seed, per_class={"train": max(ns)})
        same_test = [i.id for i in ref.split("test")] == [i.id for i in big.split("test")]
        same_cal = [i.id for i in ref.split("calibration")] == [i.id for i in big.split("calibration")]
        if not (same_test and same_cal):
            raise RuntimeError("C1a: raising the train cap changed the test/calibration split; refusing to run")
        say(f"\n## task {big.name}  labels={len(big.labels)}  train_pool={len(big.split('train'))}  "
            f"cal={len(big.split('calibration'))}  test={len(big.split('test'))}  (test split == load_task default: {same_test})")
        say(f"## source: {big.source}")
        for feat in feats:
            for n in ns:
                b = C1Backend({**base, "features": feat, "seed": seed})
                info = b.fit(big, n)
                test = big.split("test")
                logp, lats, cold = b.timed_log_proba(test)
                t = b.fit_calibration(big)
                tag = f"c1-{name}-{feat}"
                for calibrated in (False, True):
                    rr, extra = _evaluate(big, b, logp, lats, cold, n, calibrated, tag)
                    rows.append(_row(rr, extra))
                    say(f"{rr.run_id:40s} acc={rr.accuracy:.4f} CI95={rr.accuracy_ci95[0]:.4f}-{rr.accuracy_ci95[1]:.4f} "
                        f"F1={rr.macro_f1:.4f} ECE={rr.ece:.4f} Brier={rr.brier:.4f} NLL={extra['nll']:.4f} "
                        f"T={t if calibrated else 1.0:.3f} p50={rr.p50_latency_s*1e3:.3f}ms p95={rr.p95_latency_s*1e3:.3f}ms "
                        f"cold={cold*1e3:.2f}ms train={info['train_time_s']:.3f}s n/class={info['n_per_class_min']}-{info['n_per_class_max']} "
                        f"n_train={info['n_train']}  {rr.provenance}")
    out_csv.parent.mkdir(parents=True, exist_ok=True)
    fields = [f.name for f in dataclasses.fields(RunResult)] + list(EXTRA_COLS)
    with out_csv.open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fields)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k) for k in fields})
    out_log.write_text("\n".join(log) + "\n")
    say(f"\nwrote {out_csv} ({len(rows)} rows) and {out_log}")
    return rows


def make_backend(cfg: Mapping[str, Any] | None = None) -> C1Backend:
    """Factory for LAB-A's runner. Accepts a `backends:` list entry (kind: c1) from configs/c1.yaml;
    runner-level keys (name, kind, modes) are ignored, every other key must be a C1Backend config field."""
    d = {k: v for k, v in dict(cfg or {}).items() if k not in RUNNER_KEYS}
    return C1Backend(d)


def main(argv: Sequence[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description="C1a classical baseline (LAB-B)")
    ap.add_argument("--sweep", action="store_true", help="run the label-count sweep and write results/c1_sweep.*")
    ap.add_argument("--config", default=str(LAB_DIR / "configs" / "c1.yaml"))
    args = ap.parse_args(argv)
    if not args.sweep:
        ap.error("nothing to do (use --sweep)")
    import yaml

    cfg = yaml.safe_load(Path(args.config).read_text()) if Path(args.config).exists() else {}
    entries = [b for b in (cfg.get("backends") or []) if b.get("kind") == "c1"]  # LAB-A runner schema
    c1 = dict(entries[0]) if entries else dict(cfg.get("c1") or {})
    sweep = {k: v for k, v in c1.items() if k not in ("sweep", "features", "n_per_class") + RUNNER_KEYS}
    sweep.update(c1.get("sweep") or {})
    sweep.setdefault("tasks", [cfg.get("task", {"name": "clinc150", "n_intents": 15, "seed": 7})])
    out = cfg.get("output", {})
    run_sweep(sweep, LAB_DIR / out.get("csv", "results/c1_sweep.csv"), LAB_DIR / out.get("log", "results/c1_sweep.log"))


if __name__ == "__main__":
    main(sys.argv[1:])
