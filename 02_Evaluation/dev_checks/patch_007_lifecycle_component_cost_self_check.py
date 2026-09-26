# -*- coding: utf-8 -*-
"""PATCH_007 self-check (02 Evaluation, Module 7).

Lifecycle components must be priced from the Module 5 breakdown that contains
them, so that identical equipment and finishes cost the same whatever the
structure.  A component with no priced source falls back to the legacy share
method and is listed as such.
"""
import copy
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from services import repair_demolition_cost_engine_v9_6 as M7  # noqa: E402

FAIL = []


def check(ok, label, detail=""):
    if ok:
        print(f"  [OK]   {label}")
    else:
        FAIL.append(f"{label} :: {detail}")
        print(f"  [NG]   {label} :: {detail}")


DB = json.loads((ROOT / "data" / "repair_demolition_cost_assumptions_v9_6.json").read_text(encoding="utf-8"))


def m5(structure_cost, total_markup=1.4, hvac=2_836_560.0, electrical=1_482_855.0, glass=4_272_000.0,
       extra_lines=None):
    lines = [{"cost_item_key": "concrete", "line_total_after_conditions": structure_cost},
             {"cost_item_key": "glass", "line_total_after_conditions": glass},
             {"cost_item_key": "roofing", "line_total_after_conditions": 1_178_871.0}]
    lines += extra_lines or []
    direct = sum(x["line_total_after_conditions"] for x in lines)
    equip = hvac + electrical
    return {"cost_lines": lines,
            "equipment_packages": [{"package_key": "hvac", "cost": hvac, "include": True},
                                   {"package_key": "electrical", "cost": electrical, "include": True}],
            "summary": {"direct_construction_cost": direct, "additional_equipment_cost": equip,
                        "total_construction_cost": (direct + equip) * total_markup},
            "currency": "JPY"}


def project(m5out, component_keys):
    events = [{"event_id": f"e{i}", "year": 10, "action": "replace_equipment" if k.startswith("equipment")
               else "replace_infill", "component_key": k, "component": k, "scope": "all"}
              for i, k in enumerate(component_keys)]
    return {"common": {"scale_gfa_m2": 245.1},
            "module_outputs": {"module3": {"period_years": 200, "events": events}, "module5": m5out}}


def cost(res, key):
    for e in res["event_costs"]:
        if e["component_key"] == key:
            return e["component_new_cost"], e.get("component_cost_basis")
    return None, None


KEYS = ["equipment_hvac", "equipment_ventilation", "equipment_lighting", "equipment_outlets",
        "windows", "roof", "equipment_refrigerator", "whole_building"]

print("PATCH_007 self-check")
print("-- 1. identical equipment costs the same whatever the structure costs")
cheap = M7.calculate(project(m5(3_000_000.0), KEYS), DB, {})
dear = M7.calculate(project(m5(30_000_000.0), KEYS), DB, {})
for k in ("equipment_hvac", "equipment_ventilation", "equipment_lighting", "equipment_outlets", "windows", "roof"):
    a, ba = cost(cheap, k)
    b, bb = cost(dear, k)
    check(abs(a - b) < 1e-6, f"{k}: same new cost with a 10x structure cost", f"{a:,.0f} vs {b:,.0f}")
    check(ba == bb and not str(ba).startswith("legacy"), f"{k}: priced from the Module 5 breakdown", str(ba))

print("-- 2. package splits and markup")
h, _ = cost(cheap, "equipment_hvac")
v, _ = cost(cheap, "equipment_ventilation")
check(abs((h + v) - 2_836_560.0 * 1.4) < 1e-3, "hvac + ventilation equal the hvac package on the total basis",
      f"{h + v:,.2f}")
check(abs(h / v - 0.055 / 0.02) < 1e-9, "the package is split in the ratio of the component shares", f"{h / v:.4f}")
w, _ = cost(cheap, "windows")
check(abs(w - 4_272_000.0 * 1.4) < 1e-3, "windows use the glass line on the total basis", f"{w:,.2f}")

print("-- 3. whole-building rebuild still follows the total (legitimately structure-dependent)")
a, ba = cost(cheap, "whole_building")
b, bb = cost(dear, "whole_building")
check(ba == "module5_total_construction_cost" and b > a, "whole_building = total construction cost", f"{a:,.0f} {b:,.0f}")

print("-- 4. no priced source -> method-neutral fallback, and it is listed")
r, br = cost(cheap, "equipment_refrigerator")
check(br == "method_neutral_share_of_nonstructural_reference",
      "a component without a Module 5 source uses the method-neutral reference", str(br))
check("equipment_refrigerator" in cheap["summary"]["method_neutral_fallback_components"],
      "the fallback component is listed in method_neutral_fallback_components")
r2, _ = cost(dear, "equipment_refrigerator")
check(abs(r - r2) < 1e-6, "the fallback does NOT scale with a 10x structure cost", f"{r:,.0f} vs {r2:,.0f}")
ref = cheap["summary"]["nonstructural_reference_cost"]
check(abs(r - 0.01 * ref) < 1e-6, "fallback = share x reference", f"{r:,.2f} vs {0.01 * ref:,.2f}")
no_glass = M7.calculate(project(m5(3_000_000.0, glass=0.0), ["windows", "equipment_hvac"]), DB, {})
_, bw = cost(no_glass, "windows")
check(bw == "method_neutral_share_of_nonstructural_reference",
      "a group whose lines are all unpriced also takes the method-neutral fallback", str(bw))
bare = {"cost_lines": [{"cost_item_key": "concrete", "line_total_after_conditions": 5_000_000.0}],
        "equipment_packages": [],
        "summary": {"direct_construction_cost": 5_000_000.0, "additional_equipment_cost": 0.0,
                    "total_construction_cost": 7_000_000.0}, "currency": "JPY"}
leg = M7.calculate(project(bare, ["equipment_refrigerator"]), DB, {})
_, bl = cost(leg, "equipment_refrigerator")
check(str(bl).startswith("legacy_share") and "equipment_refrigerator" in leg["summary"]["legacy_share_components"],
      "only with no method-invariant component priced at all does the flagged legacy rule remain", str(bl))

print("-- 5. a human override wins")
ov = M7.calculate(project(m5(30_000_000.0), ["equipment_refrigerator", "equipment_hvac"]), DB,
                  {"component_cost_overrides": {"equipment_refrigerator": 250_000.0, "equipment_hvac": 0.0}})
r, br = cost(ov, "equipment_refrigerator")
check(r == 250_000.0 and br == "human_override", "an explicit override is used as given", f"{r} {br}")
h, bh = cost(ov, "equipment_hvac")
check(h == 0.0 and bh == "human_override", "a zero override is a real value, not 'missing'", f"{h} {bh}")

print("-- 6. structure components share one source rule")
st = M7.calculate(project(m5(5_000_000.0), ["structure_timber", "structure_rc_frame"]), DB, {})
a, ba = cost(st, "structure_timber")
b, bb = cost(st, "structure_rc_frame")
check(ba == bb == "module5_cost_lines" and abs(a - b) < 1e-6, "every structure_* key reads the structural lines")

print("-- 7. the mapping is editable data")
check(isinstance(DB.get("component_cost_sources"), dict) and "windows" in DB["component_cost_sources"],
      "component_cost_sources is stored in the assumptions JSON")
db2 = copy.deepcopy(DB)
db2["component_cost_sources"]["windows"]["cost_item_keys"] = ["roofing"]
alt = M7.calculate(project(m5(3_000_000.0), ["windows"]), db2, {})
w2, _ = cost(alt, "windows")
check(abs(w2 - 1_178_871.0 * 1.4) < 1e-3, "editing the JSON mapping changes the source", f"{w2:,.2f}")

print("-- 8. the reference uses method-invariant components only")
ins_small = M7.calculate(project(m5(3_000_000.0, extra_lines=[
    {"cost_item_key": "phenolic_foam", "line_total_after_conditions": 500_000.0}]),
    ["equipment_refrigerator", "insulation"]), DB, {})
ins_large = M7.calculate(project(m5(3_000_000.0, extra_lines=[
    {"cost_item_key": "phenolic_foam", "line_total_after_conditions": 9_000_000.0}]),
    ["equipment_refrigerator", "insulation"]), DB, {})
check(abs(ins_small["summary"]["nonstructural_reference_cost"] - ins_large["summary"]["nonstructural_reference_cost"]) < 1e-6,
      "a legitimately different insulation cost does not move the reference")
a, _ = cost(ins_small, "equipment_refrigerator")
b, _ = cost(ins_large, "equipment_refrigerator")
check(abs(a - b) < 1e-6, "and therefore does not move any fallback", f"{a:,.0f} vs {b:,.0f}")
check(set(M7.METHOD_INVARIANT_REFERENCE_COMPONENTS) ==
      {"equipment_hvac", "equipment_ventilation", "equipment_lighting", "equipment_outlets", "windows", "infill_layout"},
      "the reference set is exactly equipment + windows + interior layout")

print("-- 9. all_infill counts each amount once")
pk = m5(3_000_000.0)
pk["equipment_packages"].append({"package_key": "plumbing", "cost": 2_696_100.0, "include": True})
pk["summary"]["additional_equipment_cost"] += 2_696_100.0
pk["summary"]["total_construction_cost"] = (pk["summary"]["direct_construction_cost"]
                                            + pk["summary"]["additional_equipment_cost"]) * 1.4
comps = ["all_infill", "windows", "roof", "equipment_hvac", "equipment_ventilation",
         "equipment_lighting", "equipment_outlets", "equipment_refrigerator",
         "infill_layout", "infill_exterior", "insulation"]
ai = M7.calculate(project(pk, comps), DB, {})
audit = ai["summary"]["component_cost_basis_audit"]
nonstruct = sum(v["component_new_cost"] for k, v in audit.items() if k != "all_infill")
expected = nonstruct + 2_696_100.0 * 1.4
got, basis = cost(ai, "all_infill")
check(abs(got - expected) < 1e-3,
      "all_infill = resolved non-structural components + packages no component carries",
      f"{got:,.0f} vs {expected:,.0f}")
check(basis == "sum_of_resolved_non_structural_components", "all_infill basis is recorded", str(basis))

print("-- 10. the legacy rule can be reproduced exactly")
lg = M7.calculate(project(m5(3_000_000.0), KEYS), DB, {"component_cost_method": "legacy_total_share"})
tot = m5(3_000_000.0)["summary"]["total_construction_cost"]
ok = all(abs(cost(lg, k)[0] - tot * float(DB["component_shares"].get(k, .02))) < 1e-6 for k in KEYS)
check(ok, "component_cost_method=legacy_total_share gives total x share for every component")
check(lg["summary"]["component_cost_method"] == "legacy_total_share_selected", "the selected method is recorded")

print()
if FAIL:
    print("[NG] PATCH_007 self-check FAILED:")
    for f in FAIL:
        print("   -", f)
    raise SystemExit(1)
print("PATCH_007_LIFECYCLE_COMPONENT_COST_FROM_MODULE5_PASS")
