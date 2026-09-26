# -*- coding: utf-8 -*-
"""PATCH_048: duplicate dictionary-literal keys.

In a Python dict literal a repeated key is silently overwritten by the LAST
entry.  PATCH_047 found this twice in module1/app.py (one of them changed a
display label), and the cross-product audit after it found two more.  pyflakes
only warns when the repeated entries have DIFFERENT values, so an identical
duplicate - harmless today, a trap the next time one of the two is edited -
passes it.  This check fails on every repeated constant key, same value or not,
in every product .py file, and on every repeated key in every product .json file.

Run: python dev_checks/duplicate_dict_key_self_check.py
"""
import ast
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKIP_PARTS = {"PATCH", "__pycache__", "build", "dist"}


def product_files(pattern):
    return sorted(p for p in ROOT.rglob(pattern) if not (SKIP_PARTS & set(p.relative_to(ROOT).parts)))


problems = []
py_files = product_files("*.py")
for f in py_files:
    try:
        tree = ast.parse(f.read_text(encoding="utf-8-sig"), filename=str(f))
    except SyntaxError as exc:
        problems.append(f"{f.relative_to(ROOT)}: cannot parse ({exc})")
        continue
    for node in ast.walk(tree):
        if not isinstance(node, ast.Dict):
            continue
        seen = {}
        for key in node.keys:
            if not isinstance(key, ast.Constant):
                continue  # **spread or computed key
            marker = (type(key.value).__name__, key.value)
            if marker in seen:
                problems.append(f"{f.relative_to(ROOT)}:{key.lineno}: key {key.value!r} repeats line {seen[marker]}")
            else:
                seen[marker] = key.lineno

json_files = product_files("*.json")


def _pairs_hook(path):
    def hook(pairs):
        keys = [k for k, _ in pairs]
        for k in sorted({k for k in keys if keys.count(k) > 1}):
            problems.append(f"{path.relative_to(ROOT)}: JSON key {k!r} repeated")
        return dict(pairs)
    return hook


for f in json_files:
    try:
        json.loads(f.read_text(encoding="utf-8-sig"), object_pairs_hook=_pairs_hook(f))
    except ValueError as exc:
        problems.append(f"{f.relative_to(ROOT)}: invalid JSON ({exc})")

if problems:
    for line in problems:
        print("[NG]", line)
    sys.exit(1)
print(f"DUPLICATE_DICT_KEY_CLEAN_ACROSS_{len(py_files)}_PY_AND_{len(json_files)}_JSON_FILES_PASS")
