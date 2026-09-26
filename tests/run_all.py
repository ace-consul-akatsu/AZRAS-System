# -*- coding: utf-8 -*-
"""Run every check of AZRAS System in one go.

1. each product's own self-checks (dev_checks/*.py, and full_self_check.py where present),
   run inside that product's folder;
2. the repository checks in tests/ (schemas, disclaimer, cross-product connections).

Run from the repository root:  python tests/run_all.py
Exit code 0 only when every check passes.  A check that cannot run
(for example a missing package) counts as a failure.
"""
import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PRODUCTS = ("00_Installer", "01_Planning", "02_Evaluation", "03_Compare")


def run(script, cwd):
    t = time.time()
    r = subprocess.run([sys.executable, str(script)], cwd=cwd, capture_output=True, text=True,
                       encoding="utf-8", errors="replace", timeout=1800)
    tail = (r.stdout.strip().splitlines() or [""])[-1]
    return r.returncode == 0, time.time() - t, tail, r


results = []
for product in PRODUCTS:
    folder = REPO / product
    scripts = sorted((folder / "dev_checks").glob("*.py"))
    if (folder / "full_self_check.py").exists():
        scripts.append(folder / "full_self_check.py")
    for s in scripts:
        ok, sec, tail, r = run(s, folder)
        results.append((product, s.name, ok, sec, tail, r))
        print(f"[{'PASS' if ok else 'FAIL'}] {product}/{s.relative_to(folder)} ({sec:.0f}s)")
for s in sorted((REPO / "tests").glob("check_*.py")):
    ok, sec, tail, r = run(s, REPO)
    results.append(("tests", s.name, ok, sec, tail, r))
    print(f"[{'PASS' if ok else 'FAIL'}] tests/{s.name} ({sec:.0f}s)")

failed = [x for x in results if not x[2]]
print()
for product, name, ok, sec, tail, r in failed:
    print(f"--- {product}/{name}")
    print("\n".join((r.stdout + r.stderr).strip().splitlines()[-8:]))
print(f"\n{len(results) - len(failed)}/{len(results)} checks passed")
sys.exit(1 if failed else 0)
