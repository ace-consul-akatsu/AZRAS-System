# -*- coding: utf-8 -*-
"""v2.2.0 baseline: the launcher opens the newest working folder of each product.

Working folders are named <slot>_<Product>_NN and NN rises with every patch
(01_Planning_48, 02_Evaluation_10, 03_Compare_07, 00_Installer_03).  When an
older folder is still beside the new one, the launcher must pick the higher
NN - numerically, so _10 beats _09 and _9.

Run: python dev_checks/launcher_product_resolution_self_check.py
"""
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import azras_launcher as L  # noqa: E402

FAIL = []


def check(ok, label, detail=""):
    if ok:
        print(f"  [OK]   {label}")
    else:
        FAIL.append(f"{label} :: {detail}")
        print(f"  [NG]   {label} :: {detail}")


print("launcher_product_resolution self-check")
LAYOUT = {
    "01_Planning_47": "run_AZRAS_Planning_without_build.bat",
    "01_Planning_48": "run_AZRAS_Planning_without_build.bat",
    "02_Evaluation_9": "run_AZRAS_Evaluation_without_build.bat",
    "02_Evaluation_09": "run_AZRAS_Evaluation_without_build.bat",
    "02_Evaluation_10": "run_AZRAS_Evaluation_without_build.bat",
    "03_Compare_06": "run_AZRAS_Compare_without_build.bat",
    "03_Compare_07": "run_AZRAS_Compare_without_build.bat",
}
EXPECT = {"P": "01_Planning_48", "E": "02_Evaluation_10", "C": "03_Compare_07"}
saved = L.BASE
with tempfile.TemporaryDirectory() as td:
    system = Path(td) / "AZRAS"
    (system / "00_Installer_03").mkdir(parents=True)
    for folder, bat in LAYOUT.items():
        (system / folder).mkdir()
        (system / folder / bat).write_text("@echo off\n", encoding="ascii")
        (system / folder / "main.py").write_text("", encoding="ascii")
    try:
        L.BASE = system / "00_Installer_03"
        for key, _name, prefixes, bats in L.PRODUCT_SPECS:
            entry = L.resolve_product(prefixes, bats)
            got = entry.parent.name if entry else None
            check(got == EXPECT[key], f"{_name} opens {EXPECT[key]}", str(entry))
            check(entry is not None and entry.suffix.lower() == ".bat", f"{_name} starts through its BAT", str(entry))
    finally:
        L.BASE = saved

print()
if FAIL:
    print("[NG] launcher_product_resolution self-check FAILED:")
    for f in FAIL:
        print("   -", f)
    raise SystemExit(1)
print("LAUNCHER_PRODUCT_RESOLUTION_PASS")
