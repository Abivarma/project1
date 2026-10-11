"""CLI: python -m jevlab {run,probe,task} ...  (run from the lab/ directory)."""
from __future__ import annotations

import argparse
import json
import sys


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m jevlab", description="Local Lab: LLM way vs Jev-style decision primitive (emulation)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run", help="probe, predict, calibrate, permute, write results/")
    r.add_argument("--config", required=True)
    r.add_argument("--limit-test", type=int, default=None, help="cap test items (quick tries)")
    r.add_argument("--limit-cal", type=int, default=None, help="cap calibration items")
    r.add_argument("--only", default=None, help="comma list of backend names or name:mode")
    r.add_argument("--no-permutation", action="store_true")
    r.add_argument("--out", default=None, help="results directory (default lab/results)")
    p = sub.add_parser("probe", help="run only the capability probes (LL2)")
    p.add_argument("--config", required=True)
    t = sub.add_parser("task", help="print the task summary")
    t.add_argument("--name", default="clinc150")
    t.add_argument("--n-intents", type=int, default=15)
    t.add_argument("--seed", type=int, default=7)
    a = ap.parse_args(argv)

    from . import run as R

    if a.cmd == "task":
        from .data import load_task, task_summary

        task = load_task(a.name, n_intents=a.n_intents, seed=a.seed)
        print(json.dumps(task_summary(task), indent=1))
        print(json.dumps(task.label_descriptions, indent=1))
        return 0
    cfg = R.load_config(a.config)
    if a.cmd == "probe":
        from .data import load_task

        tc = cfg.get("task", {})
        task = load_task(tc.get("name", "clinc150"), n_intents=tc.get("n_intents", 15), seed=tc.get("seed", 7), per_class=tc.get("per_class"))
        bad = 0
        for be in R.build_backends(cfg):
            try:
                print(f"OK   {be.name}:{be.mode} {json.dumps(be.probe(task), default=str)[:400]}")
            except Exception as e:
                bad += 1
                print(f"FAIL {be.name}:{be.mode} {type(e).__name__}: {e}")
        return 1 if bad else 0
    res = R.run(cfg, out_dir=a.out, limit_test=a.limit_test, limit_cal=a.limit_cal,
                only=a.only.split(",") if a.only else None, permutation=not a.no_permutation)
    return 2 if res["failures"] else 0


if __name__ == "__main__":
    sys.exit(main())
