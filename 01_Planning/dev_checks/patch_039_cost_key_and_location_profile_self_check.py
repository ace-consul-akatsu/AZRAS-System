# -*- coding: utf-8 -*-
"""PATCH_039 self-check.

Two defects are covered.

(1) Cost-key coverage.  Module 1 quantified eight envelope/finish scopes that
    Module 5 had no way to price, so they stayed permanently red in the
    quantity/cost coverage audit and were never included in the AI Cost
    Provider request.  Four of them are genuine monetary owners and now have
    registered cost keys; the other four are physically inside an already
    priced control area and now resolve to that parent instead of being
    reported as independent gaps.

(2) Regional profile honesty.  A project city that is not one of the
    registered representative cities fell back to the country reference city
    with no record that it had done so, and that reference city was then
    written into the AI response as the project's own planning region.
"""
import json, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import services.construction_cost_engine_v9_4 as E  # noqa: E402

FAIL = []


def check(ok, label, detail=""):
    if ok:
        print(f"  [OK]   {label}")
    else:
        FAIL.append(f"{label} :: {detail}")
        print(f"  [NG]   {label} :: {detail}")


print("PATCH_039 self-check")
print("-- 1. new cost keys are registered consistently")
DB = json.loads((ROOT / "data" / "construction_cost_database_v9_4.json").read_text(encoding="utf-8"))
base = DB["base_unit_costs_jpy"]
for key, unit in (("ceiling_insulation_area", "m2"), ("parapet_coping", "m"), ("rainwater_gutter", "m")):
    check(key in base, f"{key} present in base_unit_costs_jpy")
    check(str(base.get(key, {}).get("unit")) == unit,
          f"{key} base unit is {unit}", str(base.get(key, {}).get("unit")))
    check(E.COST_KEY_CANONICAL_UNIT.get(key) == unit,
          f"{key} canonical unit is {unit}", str(E.COST_KEY_CANONICAL_UNIT.get(key)))
    check(key in E._method_allowed_keys("general"), f"{key} allowed for the general method")
    check(bool(base.get(key, {}).get("en")), f"{key} has an English canonical name for AI exchange")

print("-- 2. whole-scope control rows bridge to a cost key")
for item, unit, expect in (
    ("外部窓ガラス area 合計", "m2", "glass"),
    ("Ceiling glass wool insulation area", "m2", "ceiling_insulation_area"),
    ("Parapet coping length on north, south and west faces", "m", "parapet_coping"),
    ("Eaves gutter length on east face", "m", "rainwater_gutter"),
):
    got = E._takeoff_cost_key({"item": item, "unit": unit})
    check(got == expect, f"{item!r} -> {expect}", str(got))

print("-- 3. per-mark detail rows must NOT become a second monetary owner")
for item, unit in (
    ("AW-1 窓（現在PDF内仕様）", "m2"),
    ("AW-2 窓（現在PDF内仕様）", "m2"),
    ("ガラス仕様未確定 窓 area", "m2"),
):
    got = E._takeoff_cost_key({"item": item, "unit": unit})
    check(got is None, f"{item!r} has no direct cost key", str(got))

print("-- 4. layers inside a priced control area resolve to their parent")
for item, unit, cat, expect in (
    ("ビニル床シート系", "m2", "floor finish", "interior_finish"),
    ("Suspended gypsum acoustic ceiling board area", "m2", "architecture", "interior_finish"),
    ("K-type GL-color steel spandrel cladding area on north facade", "m2", "architecture", "external_finish"),
    ("SS-1 シャッター（仕様未確定）", "pcs", "建具", "doors"),
    ("PT-1 steel partition count", "pcs", "architecture", "doors"),
    ("Rainwater downpipe count", "pcs", "architecture", "rainwater_gutter"),
):
    got = E._quantity_cost_parent_scope({"item": item, "unit": unit, "category": cat})
    check(got == expect, f"{item!r} parent -> {expect}", str(got))

print("-- 5. ceiling insulation has exactly one monetary owner")
project = {"common": {"construction_method_id": "general", "scale_gfa_m2": 100.0}}
module1 = {"quantity_takeoff": {"rows": [
    {"item": "天井グラスウール 体積", "unit": "m3", "quantity": 10.0,
     "accepted_quantity": 10.0, "downstream_quantity_eligible": True},
    {"item": "Ceiling glass wool insulation area", "unit": "m2", "quantity": 100.0,
     "accepted_quantity": 100.0, "downstream_quantity_eligible": True},
]}}
q, prov, exc = E.extract_quantities(project, module1, {})
check("ceiling_glass_wool" in q, "volume key survives when both bases are present")
check("ceiling_insulation_area" not in q,
      "area key is dropped when the volume key exists", str(sorted(q)))
check(any(str(x.get("cost_item_key")) == "ceiling_insulation_area" for x in exc),
      "dropped area key is recorded in excluded_quantities, not silently deleted")

module1_area_only = {"quantity_takeoff": {"rows": [
    {"item": "Ceiling glass wool insulation area", "unit": "m2", "quantity": 100.0,
     "accepted_quantity": 100.0, "downstream_quantity_eligible": True},
]}}
q2, _, _ = E.extract_quantities(project, module1_area_only, {})
check(abs(float(q2.get("ceiling_insulation_area") or 0.0) - 100.0) < 1e-9,
      "area key is used when no volume row exists", str(sorted(q2)))

print("-- 6. regional profile reports how it was reached")
locations = DB.get("locations") or {}
il = {"common": {"country": "United States",
                 "city": "IND HEAD PARK, イリノイ州 60525 アメリカ合衆国",
                 "project_location": "IND HEAD PARK, イリノイ州 60525 アメリカ合衆国"}}
r = E.resolve_location_profile_from_project(il, DB)
check(r.get("match_level") == "country_reference_fallback",
      "unregistered US city is reported as a country reference fallback", str(r.get("match_level")))
check(r.get("profile_is_country_fallback") is True and r.get("profile_is_project_city") is False,
      "fallback flags are set for an unregistered city")
check(r.get("location_key") in locations,
      "a usable profile is still selected so Module 5 keeps working", str(r.get("location_key")))

jp = {"common": {"country": "Japan", "city": "名古屋", "project_location": "愛知県春日井市"}}
rj = E.resolve_location_profile_from_project(jp, DB)
check(rj.get("match_level") == "matched_city",
      "a registered city is still reported as a real city match", str(rj.get("match_level")))
check(rj.get("profile_is_project_city") is True and rj.get("profile_is_country_fallback") is False,
      "matched-city flags are set for a registered city")

print("-- 7. Module 5 no longer labels the reference city as the planning region")
m5 = (ROOT / "module5" / "app.py").read_text(encoding="utf-8")
check('"planning_region":"{planning_region}"' in m5,
      "AI request planning_region comes from the authoritative project address")
check('"representative_cost_profile":"{region}"' in m5,
      "representative profile is returned in its own field")
check("_cost_profile_match_basis" in m5 and "_cost_profile_proxy_notice" in m5,
      "profile basis and proxy notice helpers exist")

print()
if FAIL:
    print("[NG] PATCH_039 self-check FAILED:")
    for f in FAIL:
        print("   -", f)
    raise SystemExit(1)
print("PATCH_039_COST_KEY_AND_LOCATION_PROFILE_PASS")
