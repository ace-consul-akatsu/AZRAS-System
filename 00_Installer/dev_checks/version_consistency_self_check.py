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
TEXT_FILES = ("README_JA.txt", "README_EN.txt", "NOTICE.txt")
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

for name in ("docs/AZRAS_Installation_Guide_EN.html", "docs/AZRAS_Installation_Guide_JA.html"):
    text = (ROOT / name).read_text(encoding="utf-8-sig")
    stale = [v for v in re.findall(r"Installer Version (\d+\.\d+\.\d+)", text) if v != version]
    check(not stale, f"{name} names no other Installer version", str(stale))
notice = (ROOT / "NOTICE.txt").read_text(encoding="utf-8-sig")
check(re.search(r"\b1\.[01]\.\d{2,3}\b|v2\.[01]\.0", notice) is None,
      "NOTICE lists no pre-v2.2.0 product versions")
check("-p" not in version, "no old -pNNN counter inside the version (the patch lives in \"patch\")", version)

print("-- 3. the screen reads VERSION.json")
src = (ROOT / "azras_installer.py").read_text(encoding="utf-8")
check(re.search(r'(?<![A-Z_])APP_VERSION\s*=\s*"\d', src) is None and "Version 5." not in src,
      "azras_installer.py hard-codes no version")
import azras_installer as I  # noqa: E402
check(I.APP_VERSION == version, "the Installer shows the VERSION.json version", I.APP_VERSION)
check(I.DEFAULT_APP_VERSION == version, "the fallback equals VERSION.json", I.DEFAULT_APP_VERSION)
check(all(version in I.TEXT[lang]["subtitle"] for lang in I.TEXT), "both language subtitles show it")

print()
if FAIL:
    print("[NG] version_consistency self-check FAILED:")
    for f in FAIL:
        print("   -", f)
    raise SystemExit(1)
print("VERSION_CONSISTENCY_PASS")
