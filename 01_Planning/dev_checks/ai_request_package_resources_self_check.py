# -*- coding: utf-8 -*-
"""PATCH_048: every resource file the AI request ZIP lists must exist.

module1/app.py adds the protocol/schema/template files to the R1 request ZIP
with "if src.exists()", so a wrong file name is skipped silently.  The
Japanese protocol was listed under a name that never existed and was never
sent.  This check reads the list from the source and fails on any name that
is not in resources/ai_takeoff_contract/, and checks that the Japanese and
English protocols carry the same sections.

Run: python dev_checks/ai_request_package_resources_self_check.py
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RES = ROOT / "resources" / "ai_takeoff_contract"
FAIL = []


def check(ok, label, detail=""):
    if ok:
        print(f"  [OK]   {label}")
    else:
        FAIL.append(f"{label} :: {detail}")
        print(f"  [NG]   {label} :: {detail}")


print("ai_request_package_resources self-check")
src = (ROOT / "module1" / "app.py").read_text(encoding="utf-8")
anchor = src.find('resroot=self.root_dir/"resources"/"ai_takeoff_contract"')
check(anchor != -1, "the request-package resource list is found")
start = src.find("for name in (", anchor)
block = src[start:src.find("if src.exists()", start)]
names = re.findall(r'"([^"]+\.(?:md|json|txt))"', block)
check(len(names) >= 4, "the resource list has the expected entries", str(names))
for name in names:
    check((RES / name).is_file(), f"{name} exists in resources/ai_takeoff_contract")
check(any(n.endswith("_JP.md") for n in names) and any(n.endswith("_EN.md") for n in names),
      "both the Japanese and the English protocol are sent")

print("-- the two protocols carry the same sections")
jp = (RES / "AZRAS_AI_Longitudinal_Observation_Protocol_v1.1_JP.md").read_text(encoding="utf-8-sig")
en = (RES / "AZRAS_AI_Longitudinal_Observation_Protocol_v1.1_EN.md").read_text(encoding="utf-8-sig")
jp_h = re.findall(r"^## ", jp, flags=re.M)
en_h = re.findall(r"^## ", en, flags=re.M)
check(len(jp_h) == len(en_h), "same number of sections", f"JP {len(jp_h)} / EN {len(en_h)}")
for token in ("R1/01_Request for Estimate", "R1/04_Final determination", "quantity:null",
              "evidence_status", "AZRAS_AI_TAKEOFF_RESPONSE_TEMPLATE_v1.0.json", "required_filename"):
    check(token in jp and token in en, f"both protocols state {token}")

print()
if FAIL:
    print("[NG] ai_request_package_resources self-check FAILED:")
    for f in FAIL:
        print("   -", f)
    raise SystemExit(1)
print("AI_REQUEST_PACKAGE_RESOURCES_PASS")
