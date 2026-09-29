# -*- coding: utf-8 -*-
"""PATCH_012: default export file names must match the screen that saves them.

Module 6 (投資評価) 「キャッシュフローCSV保存」 proposed the file name
"Module6_修繕更新解体積算_イベント別.csv", and Module 7 (改修・更新・解体費)
proposed the very same name, so the two different CSVs overwrote each other
in the shared property folder.

This check fails when, in any moduleN/app.py, a default_export_path(...) call
  - passes a module number other than N, or
  - uses a label that does not start with "ModuleN_", or
  - uses a label already used by another call site;
or when MODULE_EXPORT_NAMES for 6/7 do not follow the current screen names.

Run: python dev_checks/export_filename_self_check.py
"""
import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
errors = []
seen = {}

for app in sorted(ROOT.glob("module*/app.py")):
    n = int(app.parent.name.replace("module", ""))
    tree = ast.parse(app.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Call) and getattr(node.func, "id", "") == "default_export_path"):
            continue
        where = f"{app.relative_to(ROOT)}:{node.lineno}"
        num = node.args[1].value if len(node.args) > 1 and isinstance(node.args[1], ast.Constant) else None
        label = next((k.value.value for k in node.keywords
                      if k.arg == "label" and isinstance(k.value, ast.Constant)), None)
        if num != n:
            errors.append(f"{where}: module number {num!r}, expected {n}")
        if label is None:
            errors.append(f"{where}: no literal label")
            continue
        if not label.startswith(f"Module{n}_"):
            errors.append(f"{where}: label {label!r} does not start with Module{n}_")
        if label in seen:
            errors.append(f"{where}: label {label!r} also used at {seen[label]}")
        seen[label] = where

from services.project_export_paths import MODULE_EXPORT_NAMES  # noqa: E402
for n, name in {6: "Module6_投資評価", 7: "Module7_改修更新解体費"}.items():
    if MODULE_EXPORT_NAMES.get(n) != name:
        errors.append(f"MODULE_EXPORT_NAMES[{n}] = {MODULE_EXPORT_NAMES.get(n)!r}, expected {name!r}")

if errors:
    print("[FAIL] export_filename")
    for e in errors:
        print("  -", e)
    sys.exit(1)
print(f"[PASS] export_filename: {len(seen)} export call sites, names unique and match their module")
