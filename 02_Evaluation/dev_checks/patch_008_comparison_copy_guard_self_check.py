# -*- coding: utf-8 -*-
"""PATCH_008 self-check: comparison copies in 02 Evaluation.

A copy created by 03 Compare exists to be re-evaluated in Modules 6 and 7.
Modules 3 and 4 depend only on inputs that must stay identical to the source
Project, so they may not be saved on a copy.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.project_store import comparison_copy_block_reason  # noqa: E402
from core.project_coordinator import update_module_and_propagate  # noqa: E402

FAIL = []


def check(ok, label, detail=""):
    if ok:
        print(f"  [OK]   {label}")
    else:
        FAIL.append(f"{label} :: {detail}")
        print(f"  [NG]   {label} :: {detail}")


COPY = {"project_id": "c1", "comparison_copy": {
    "schema": "AZRAS_COMPARISON_COPY_V1", "allowed_modules": ["module5", "module6", "module7"],
    "source_project_path": "C:/JSON/RC/RC.json"}}
PLAIN = {"project_id": "p1"}

print("PATCH_008 self-check")
for m in ("module6", "module7"):
    check(comparison_copy_block_reason(COPY, m) is None, f"{m} may be recalculated and saved on a copy")
for m in ("module3", "module4"):
    check(bool(comparison_copy_block_reason(COPY, m)), f"{m} is blocked on a copy")
    check(comparison_copy_block_reason(PLAIN, m) is None, f"{m} is never blocked on an ordinary Project")
check("元Project" in comparison_copy_block_reason(COPY, "module3", "ja"), "the message names the source Project")
check("Module 6" in comparison_copy_block_reason(COPY, "module3", "en"), "an English message exists")
check(comparison_copy_block_reason({"comparison_copy": {"schema": "OTHER"}}, "module3") is None,
      "an unrelated marker schema is not treated as a copy")
try:
    update_module_and_propagate(dict(COPY), "unused.json", "module3", {}, {}, ROOT)
    check(False, "a Module 3 save on a copy raises")
except ValueError as exc:
    check("比較用コピー" in str(exc), "a Module 3 save on a copy raises with the copy message", str(exc)[:50])

print()
if FAIL:
    print("[NG] PATCH_008 self-check FAILED:")
    for f in FAIL:
        print("   -", f)
    raise SystemExit(1)
print("PATCH_008_COMPARISON_COPY_GUARD_PASS")
