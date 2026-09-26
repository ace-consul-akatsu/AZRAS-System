# -*- coding: utf-8 -*-
"""PATCH_005 self-check (02 Evaluation).

Module 6 can set rent two ways, and only one of them produces a result that
means anything when several Projects are compared. The saved result must say
which one was used, without a downstream product having to infer it.
"""
import sys
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


src = (ROOT / "services" / "investment_engine_v9_5.py").read_text(encoding="utf-8")

print("PATCH_005 self-check")
print("-- 1. the disclosure block is emitted")
check('"revenue_basis_disclosure"' in src, "revenue_basis_disclosure is part of the saved result")
for key in ("rent_derived_from_construction_cost", "comparable_across_projects",
            "rent_setting_method", "rent_setting_basis", "target_gross_yield_percent",
            "resolved_annual_rent_per_m2", "comparison_note_ja", "comparison_note_en"):
    check(f'"{key}"' in src, f"the block carries {key}")
check('"audit_only":True' in src, "the block is marked audit-only")

print("-- 2. the flags follow the rent method, not the other way round")
i = src.index('"revenue_basis_disclosure"')
block = src[i:i + 2600]
check('rent_setting_method=="gross_yield"' in block,
      "rent_derived_from_construction_cost is keyed off the gross-yield method")
check('rent_setting_method=="market_rent"' in block,
      "comparable_across_projects is keyed off the market-rent method")
check('target_gross_yield_percent if rent_setting_method=="gross_yield" else None' in block,
      "the target yield is reported only when it actually drove the rent")

print("-- 3. no cash flow is touched")
check("revenue_basis_disclosure" not in src[:src.index("    rows=[]") if "    rows=[]" in src else i],
      "the block is emitted in the result, not inside the cash-flow loop")
before = src[:i]
check(before.count("base_gross_rent=") == 2,
      "rent is still resolved exactly twice (market_rent and gross_yield), unchanged",
      str(before.count("base_gross_rent=")))

print("-- 4. both rent methods still exist")
check('rent_setting_method=="market_rent"' in src, "market rent remains selectable")
check('rent_setting_method="gross_yield"' in src, "gross yield remains the fallback")

print()
if FAIL:
    print("[NG] PATCH_005 self-check FAILED:")
    for f in FAIL:
        print("   -", f)
    raise SystemExit(1)
print("PATCH_005_REVENUE_BASIS_DISCLOSURE_PASS")
