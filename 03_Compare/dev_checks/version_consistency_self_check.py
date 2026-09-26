# -*- coding: utf-8 -*-
"""v2.2.0 baseline: VERSION.json is the single source of truth for the version.

The four-product audit found each product stating several different versions
at once (VERSION.json vs README/NOTICE/other files).  This check fails when any
first line of the distributed text files states a version other than
VERSION.json, when the patch number is not a whole number, or when the
feature text does not describe the current patch.

Run: python dev_checks/version_consistency_self_check.py
"""
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

# ---- product-specific configuration ----
TEXT_FILES = ("README.txt", "README_JA.txt", "NOTICE.txt")
VERSION_KEY = "version"
VERSION_PATTERN = r"\d+\.\d+\.\d+"
# ----------------------------------------

FAIL = []


def check(ok, label, detail=""):
    if ok:
        print(f"  [OK]   {label}")
    else:
        FAIL.append(f"{label} :: {detail}")
        print(f"  [NG]   {label} :: {detail}")


data = json.loads((ROOT / "VERSION.json").read_text(encoding="utf-8-sig"))
version = str(data.get(VERSION_KEY) or "")
patch = data.get("patch")
print(f"version_consistency self-check (VERSION.json: {version} / PATCH {patch})")

print("-- 1. VERSION.json itself")
check(re.fullmatch(VERSION_PATTERN, version) is not None, f"{VERSION_KEY} has the expected form", version)
check(isinstance(patch, int) and not isinstance(patch, bool) and patch >= 0,
      "patch is a whole number (JSON number, not text)", repr(patch))
feat = str(data.get("feature") or "")
check(isinstance(patch, int) and feat.startswith(f"PATCH_{patch:03d}:"),
      "feature text describes the current patch", feat[:40])

print("-- 2. no second place states a different version")
check(not (ROOT / "VERSION").exists(), "no plain VERSION file")
for name in TEXT_FILES:
    path = ROOT / name
    if not path.exists():
        check(False, f"{name} exists")
        continue
    first = path.read_text(encoding="utf-8-sig").splitlines()[0]
    found = re.findall(r"\d+\.\d+\.\d+(?:-p\d+)?", first)
    others = [v for v in found if v != version]
    check(version in first and not others, f"{name} first line states {version}", first)

print("-- 3. the screen reads VERSION.json")
src = (ROOT / "main.py").read_text(encoding="utf-8")
check("VERSION.json" in src and re.search(r"VERSION\s*=\s*'\d", src) is None,
      "main.py takes the version from VERSION.json (no hard-coded version)")

print()
if FAIL:
    print("[NG] version_consistency self-check FAILED:")
    for f in FAIL:
        print("   -", f)
    raise SystemExit(1)
print("VERSION_CONSISTENCY_PASS")
