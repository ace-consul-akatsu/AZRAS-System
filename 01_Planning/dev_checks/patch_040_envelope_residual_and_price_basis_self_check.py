# -*- coding: utf-8 -*-
"""PATCH_040 self-check.

(2-a) Envelope: a synthesized residual light-wall area must never be
      multiplied by an uninsulated assembly U-value.
(2-b) Price basis: the saved Module 5 result must state where its unit prices
      came from, so a multi-Project comparison cannot silently mix an AI
      approximate-cost session with the built-in regional database.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from services.environment_engine_v9_1 import _build_config_with_breakdown  # noqa: E402
from services.construction_cost_engine_v9_4 import _price_basis_fingerprint  # noqa: E402

FAIL = []


def check(ok, label, detail=""):
    if ok:
        print(f"  [OK]   {label}")
    else:
        FAIL.append(f"{label} :: {detail}")
        print(f"  [NG]   {label} :: {detail}")


def build(assemblies, surfaces, construction=None, settings=None):
    module1 = {
        "profile": {
            "geometry": {"roof_area_m2": 162.6, "slab_area_m2": 122.55, "footprint_m2": 122.55},
            "assemblies": assemblies,
            "surfaces": surfaces,
            "construction": construction or {},
        },
        "quantity_takeoff": {"rows": []},
        "building_performance": {"envelope": {
            "window_u_W_m2K": 0.9,
            "insulation_details": [
                {"part": part, "material": str(asm.get("material") or ""),
                 "thickness_mm": float(asm.get("thickness_mm") or 0.0),
                 "u_value_W_m2K": (5.88235294117647 if float(asm.get("thickness_mm") or 0.0) <= 0
                                    else 1.0 / (0.17 + (float(asm["thickness_mm"]) / 1000.0) / 0.02)),
                 "resolved": True}
                for part, asm in assemblies.items()
            ],
        }},
    }
    common = {"scale_gfa_m2": 245.1, "storeys": 2, "construction_method_id": "rc_frame",
              "window_area_m2": 55.74}
    base_settings = {
        "floor_thermal": {
            "ground_floor_type": "slab_on_ground",
            "insulation_position": "external",
            "slab_under_insulation": True,
            "slab_insulation_thickness_mm": 100.0,
            "slab_insulation_conductivity_W_mK": 0.028,
        }
    }
    base_settings.update(settings or {})
    return _build_config_with_breakdown(module1, common, base_settings)


RC_ASM = {
    "rc_wall": {"material": "Phenolic foam", "thickness_mm": 150.0},
    "light_wall": {"material": "Phenolic foam", "thickness_mm": 0.0},
    "roof": {"material": "Phenolic foam", "thickness_mm": 150.0},
    "slab": {"material": "XPS", "thickness_mm": 100.0},
}
SURFACES = [{"gross_wall_area_m2": 271.712, "window_area_m2": 55.74, "door_area_m2": 6.33}]

print("PATCH_040 self-check")
print("-- 1. residual light wall no longer carries a bare-wall U")
cfg, br = build(RC_ASM, SURFACES, {"exterior_rc_interior_surface_m2": 126.76335333333334})
corr = br.get("light_wall_residual_correction") or {}
check(br.get("light_wall_area_source", "").startswith("surface_opaque_area_fallback"),
      "the light-wall area is still recognised as a synthesized residual",
      str(br.get("light_wall_area_source")))
check(corr.get("applied") is True, "the correction fires on the RC residual case", str(corr))
check(corr.get("donor_assembly") == "rc_wall",
      "the building's own resolved RC assembly is adopted", str(corr.get("donor_assembly")))
check(cfg.u_light_wall_W_m2K < 1.0,
      "the resulting light-wall U is an insulated value", f"{cfg.u_light_wall_W_m2K}")
check(corr.get("uncorrected_conductance_W_K", 0) > 400 and corr.get("corrected_conductance_W_K", 0) < 20,
      "the correction removes the dominant phantom conductance term", str(corr))

print("-- 2. a genuinely reported light wall is never overridden")
cfg2, br2 = build(RC_ASM, SURFACES,
                  {"exterior_rc_interior_surface_m2": 126.76335333333334,
                   "light_wall_area_m2": 40.0})
corr2 = br2.get("light_wall_residual_correction") or {}
check(br2.get("light_wall_area_source") == "construction.light_wall_area_m2",
      "an explicit Module 1 light-wall quantity keeps its own source", str(br2.get("light_wall_area_source")))
check(corr2.get("applied") is False,
      "the correction does not fire on a reported quantity", str(corr2))
check(cfg2.u_light_wall_W_m2K > 1.0,
      "a reported uninsulated light wall stays uninsulated", f"{cfg2.u_light_wall_W_m2K}")

print("-- 3. a user envelope scenario is never overridden")
scenario = {"envelope_thermal_scenario": {"light_wall": {"enabled": True, "material": "Phenolic foam",
                                                          "thickness_mm": 0.0}}}
cfg3, br3 = build(RC_ASM, SURFACES, {"exterior_rc_interior_surface_m2": 126.76335333333334}, scenario)
check((br3.get("light_wall_residual_correction") or {}).get("applied") is False,
      "the correction defers to an enabled light-wall scenario",
      str(br3.get("light_wall_residual_correction")))

print("-- 4. nothing to adopt means nothing is invented")
BARE = {
    "rc_wall": {"material": "Phenolic foam", "thickness_mm": 0.0},
    "light_wall": {"material": "Phenolic foam", "thickness_mm": 0.0},
    "roof": {"material": "Phenolic foam", "thickness_mm": 0.0},
    "slab": {"material": "XPS", "thickness_mm": 0.0},
}
cfg4, br4 = build(BARE, SURFACES)
corr4 = br4.get("light_wall_residual_correction") or {}
check(corr4.get("applied") is False, "no resolved assembly means no correction", str(corr4))
check(corr4.get("reason") == "no_resolved_opaque_assembly_available_to_adopt",
      "the unresolved condition is recorded rather than silently passed", str(corr4.get("reason")))
check(cfg4.u_light_wall_W_m2K > 1.0, "the uncorrected U is left untouched", f"{cfg4.u_light_wall_W_m2K}")

print("-- 5. a wood-frame building with a real light wall is unaffected")
WOOD = {
    "rc_wall": {"material": "Phenolic foam", "thickness_mm": 0.0},
    "light_wall": {"material": "Phenolic foam", "thickness_mm": 190.0},
    "roof": {"material": "Phenolic foam", "thickness_mm": 190.0},
    "slab": {"material": "XPS", "thickness_mm": 100.0},
}
cfg5, br5 = build(WOOD, SURFACES)
check((br5.get("light_wall_residual_correction") or {}).get("applied") is False,
      "an already-insulated residual needs no correction")
check(abs(cfg5.u_light_wall_W_m2K - 0.10341261633919338) < 1e-9,
      "the resolved light-wall U is preserved exactly", f"{cfg5.u_light_wall_W_m2K}")

print("-- 6. price basis fingerprint")
ai_lines = [{"unit_price_source": "ai_cost_provider", "pricing_status": "ai_post_review_rechecked_provisional",
             "pricing_structure": "installed_all_in"} for _ in range(9)]
db_lines = [{"unit_price_source": "regional_dataset", "pricing_status": "planning_city_initial_estimate_2026",
             "pricing_structure": "component_split"} for _ in range(9)]
fp_ai = _price_basis_fingerprint({"pricing_mode": "ai_approximate_cost_session_local_currency"}, ai_lines)
fp_db = _price_basis_fingerprint({"pricing_mode": "automatic_city_initial_estimate"}, db_lines)
fp_mx = _price_basis_fingerprint({"pricing_mode": "automatic_city_initial_estimate"}, ai_lines + db_lines)
check(fp_ai["basis_token"] == "ai_approximate_cost_session", "all-AI project is tagged as an AI session", fp_ai["basis_token"])
check(fp_db["basis_token"] == "regional_cost_database", "all-database project is tagged as the regional database", fp_db["basis_token"])
check(fp_mx["basis_token"] == "mixed_ai_and_regional_database", "a mixed project is tagged as mixed", fp_mx["basis_token"])
check(fp_ai["basis_token"] != fp_db["basis_token"],
      "two differently-priced Projects can be told apart by basis_token alone")
check(fp_db["component_split_available"] is True and fp_ai["component_split_available"] is False,
      "the material/labor/equipment split availability is reported")
check(_price_basis_fingerprint({}, [])["basis_token"] == "no_priced_lines",
      "an unpriced project is reported rather than mislabelled")

print()
if FAIL:
    print("[NG] PATCH_040 self-check FAILED:")
    for f in FAIL:
        print("   -", f)
    raise SystemExit(1)
print("PATCH_040_ENVELOPE_RESIDUAL_AND_PRICE_BASIS_PASS")
