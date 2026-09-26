# -*- coding: utf-8 -*-
"""PATCH_048: VERSION.json is the single source of truth for the version.

The cross-product audit found the product saying five different versions at
once (VERSION.json 2.2.0/PATCH 47, README/NOTICE 1.0.614, plain VERSION
1.0.632, core/version.py fallback 1.0.620, version_info 1.0.603/1.0.614) and a
version_info file PyInstaller could not read, so the EXE build stopped.

Run: python dev_checks/version_consistency_self_check.py
"""
import ast
import importlib
import json
import re
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

FAIL = []


def check(ok, label, detail=""):
    if ok:
        print(f"  [OK]   {label}")
    else:
        FAIL.append(f"{label} :: {detail}")
        print(f"  [NG]   {label} :: {detail}")


data = json.loads((ROOT / "VERSION.json").read_text(encoding="utf-8-sig"))
version = str(data.get("version") or "")
patch = data.get("patch")
print(f"version_consistency self-check (VERSION.json: {version} / PATCH {patch})")

print("-- 1. VERSION.json itself")
check(re.fullmatch(r"\d+\.\d+\.\d+", version) is not None, "version is N.N.N", version)
check(isinstance(patch, int) and not isinstance(patch, bool) and patch >= 0,
      "patch is a whole number (JSON number, not text)", repr(patch))
feat = str(data.get("feature") or "")
check(isinstance(patch, int) and feat.startswith(f"PATCH_{patch:03d}:"),
      "feature text describes the current patch", feat[:40])

print("-- 2. no second place states a different version")
check(not (ROOT / "VERSION").exists(), "the plain VERSION file (old 1.0.x) is gone")
for name in ("README_JA.txt", "README_EN.txt", "NOTICE.txt"):
    first = (ROOT / name).read_text(encoding="utf-8-sig").splitlines()[0]
    others = [v for v in re.findall(r"\d+\.\d+\.\d+", first) if v != version]
    check(version in first and not others, f"{name} first line states {version}", first)
for name in ("requirements.txt", "build_AZRAS_Planning.bat"):
    text = (ROOT / name).read_text(encoding="utf-8-sig")
    check(re.search(r"v\d+\.\d+\.\d+", text) is None, f"{name} hard-codes no version", "")
from core import version as V  # noqa: E402
check(V.DEFAULT_VERSION == version, "core/version.py fallback equals VERSION.json", V.DEFAULT_VERSION)
check(V.VERSION == version, "core/version.py reads VERSION.json", V.VERSION)

print("-- 3. VERSION.json is found inside a PyInstaller 6 build")
with tempfile.TemporaryDirectory() as td:
    internal = Path(td) / "AZRAS_Planning" / "_internal"
    internal.mkdir(parents=True)
    saved = (getattr(sys, "frozen", None), getattr(sys, "_MEIPASS", None), sys.executable)
    try:
        sys.frozen = True
        sys._MEIPASS = str(internal)
        sys.executable = str(internal.parent / "AZRAS_Planning.exe")
        cands = V._version_json_candidates()
    finally:
        if saved[0] is None:
            del sys.frozen
        else:
            sys.frozen = saved[0]
        if saved[1] is None:
            del sys._MEIPASS
        else:
            sys._MEIPASS = saved[1]
        sys.executable = saved[2]
    check(internal / "VERSION.json" in cands, "_internal/VERSION.json (sys._MEIPASS) is searched", str(cands))
    check((internal.parent / "VERSION.json") in cands, "the EXE folder is still searched as a fallback")

print("-- 4. the EXE version resource")
mvi = importlib.import_module("build_tools.make_version_info")
vi = ROOT / "version_info_AZRAS_Planning.txt"
check(vi.exists() and vi.read_text(encoding="utf-8") == mvi.render(data),
      "version_info_AZRAS_Planning.txt is up to date with VERSION.json",
      "run: python build_tools/make_version_info.py")
try:
    tree = ast.parse(vi.read_text(encoding="utf-8"), mode="eval")
    call = tree.body
    ok = isinstance(call, ast.Call) and getattr(call.func, "id", "") == "VSVersionInfo"
    check(ok, "version_info is a VSVersionInfo(...) expression PyInstaller can eval")
except SyntaxError as exc:
    check(False, "version_info is a VSVersionInfo(...) expression PyInstaller can eval", str(exc))
check(f"filevers={mvi._four_part(version, patch)!r}" in vi.read_text(encoding="utf-8"),
      "file version numbers are version + patch", str(mvi._four_part(version, patch)))
bat = (ROOT / "build_AZRAS_Planning.bat").read_text(encoding="utf-8")
check(bat.find("make_version_info.py") != -1 and bat.find("make_version_info.py") < bat.find("PyInstaller --clean"),
      "the build script regenerates it before PyInstaller runs")

print("-- 5. .spec files")
for spec in sorted(ROOT.glob("*.spec")):
    s = spec.read_text(encoding="utf-8")
    m = re.search(r"version=str\(root / '([^']+)'\)", s)
    check(m is not None and (ROOT / m.group(1)).exists(), f"{spec.name}: version file exists",
          m.group(1) if m else "no version=")
    for d in ("('resources', 'resources')", "('module1/*.json', 'module1')", "('VERSION.json', '.')"):
        check(d in s, f"{spec.name}: bundles {d}")

print()
if FAIL:
    print("[NG] version_consistency self-check FAILED:")
    for f in FAIL:
        print("   -", f)
    raise SystemExit(1)
print("VERSION_CONSISTENCY_PASS")
