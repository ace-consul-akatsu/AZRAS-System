
from __future__ import annotations
from typing import Any

MATERIAL_HEAT_CAPACITY_MJ_M3K = {
    "concrete": 2.10,
    "reinforcing_steel": 3.80,
    "structural_steel": 3.80,
    "dimension_lumber": 1.20,
    "clt": 1.30,
    "gypsum_board": 0.85,
}

DEFAULT_LAMBDA_W_MK = {
    "Phenolic foam": 0.020,
    "XPS": 0.028,
    "Glass wool": 0.038,
    "Rock wool": 0.038,
}

def _f(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default

def calculate_performance(profile: dict[str, Any], takeoff: dict[str, Any],
                          equipment: list[dict[str, Any]]) -> dict[str, Any]:
    assemblies = profile.get("assemblies", {})
    surfaces = profile.get("surfaces", [])
    geometry = profile.get("geometry", {})
    construction = profile.get("construction", {})

    envelope_area = 0.0
    ua_sum = 0.0
    insulation_details = []

    # PATCH_416: preserve PATCH_404 current RC exterior-surface key after final integration.
    rc_area = _f(construction.get("exterior_rc_interior_surface_m2"))
    if rc_area <= 0.0:
        rc_area = _f(construction.get("rc_wall_area_m2"))
    light_area = _f(construction.get("light_wall_area_m2"))
    roof_area = _f(geometry.get("roof_area_m2"))
    slab_area = _f(geometry.get("slab_area_m2"))
    parts = [
        ("rc_wall", rc_area),
        ("light_wall", light_area),
        ("roof", roof_area),
        ("slab", slab_area),
    ]
    construction_method_id = str(profile.get("construction_method_id", ""))
    unresolved_parts = []
    for key, area in parts:
        asm = assemblies.get(key, {})
        material = str(asm.get("material", ""))
        thickness_mm = _f(asm.get("thickness_mm"))
        resolved = bool(asm.get("resolved", True))
        # AZRAS and conventional RC profiles are defined as externally insulated.
        # Some PDF-analysis paths previously overwrote the RC-wall insulation with 0 mm.
        # Restore the canonical profile value only for an actual RC exterior wall.
        if (
            key == "rc_wall"
            and area > 0
            and thickness_mm <= 0
            and construction_method_id in {"azras", "rc_frame"}
        ):
            thickness_mm = 150.0
            material = material or "Phenolic foam"
        thickness_m = thickness_mm / 1000.0
        if not resolved:
            unresolved_parts.append(key)
            insulation_details.append({
                "part": key, "area_m2": area, "material": material or "unresolved",
                "thickness_mm": thickness_mm,
                "u_value_W_m2K": None,
                "resolved": False,
            })
            continue
        conductivity = DEFAULT_LAMBDA_W_MK.get(material, 0.035)
        r_ins = thickness_m / conductivity if thickness_m > 0 else 0.0
        # Includes a conservative non-insulation resistance allowance.
        u = 1.0 / max(0.10, r_ins + 0.17)
        envelope_area += area
        ua_sum += u * area
        insulation_details.append({
            "part": key, "area_m2": area, "material": material,
            "thickness_mm": thickness_m * 1000.0,
            "u_value_W_m2K": u,
            "resolved": True,
        })

    window_area = sum(_f(s.get("window_area_m2")) for s in surfaces)
    if window_area <= 0:
        window_area = sum(_f(v) for v in (geometry.get("window_area_by_orientation_m2") or {}).values())
    if window_area <= 0:
        # PATCH_172: external AI takeoff schema carries the aggregate opening
        # area directly when orientation-specific surfaces are not yet available.
        window_area = _f(geometry.get("window_area_m2"))
    window_asm = assemblies.get("window", {}) or {}
    window_u = _f(
        profile.get("window", {}).get("u_value_W_m2K")
        or window_asm.get("u_value_W_m2K")
        or window_asm.get("u_value"),
        1.4
    )
    envelope_area += window_area
    ua_sum += window_u * window_area

    door_area = sum(_f(s.get("door_area_m2")) for s in surfaces)
    if door_area <= 0:
        door_area = sum(_f(v) for v in (geometry.get("door_area_by_orientation_m2") or {}).values())
    if door_area <= 0:
        door_area = _f(geometry.get("door_area_m2"))
    door_asm = assemblies.get("door", {}) or {}
    door_u = _f(
        profile.get("door", {}).get("u_value_W_m2K")
        or door_asm.get("u_value_W_m2K")
        or door_asm.get("u_value"),
        1.5
    )
    envelope_area += door_area
    ua_sum += door_u * door_area

    indicative_ua = ua_sum / max(envelope_area, 1.0)

    accepted = {
        str(r.get("item")): _f(r.get("accepted_quantity", r.get("quantity")))
        for r in takeoff.get("rows", [])
    }
    thermal_capacity = 0.0
    thermal_breakdown = []

    # New method-neutral quantity rows can carry material_key so future
    # RC/timber/steel/masonry adapters do not depend on Japanese item names.
    # PATCH_527: summary rows such as "AZRAS total RC concrete" duplicate
    # detailed component rows. Keep the detailed physical components as the
    # thermal-mass source of truth; use a summary row only when no detailed row
    # exists for that material key.
    def _is_summary_item(row):
        name=str(row.get("item") or "").strip().lower()
        return any(token in name for token in ("total", "subtotal", "合計", "小計"))

    detailed_keys=set()
    for _r in takeoff.get("rows", []):
        _key=str(_r.get("material_key") or "")
        _qty=_f(_r.get("accepted_quantity",_r.get("quantity")))
        if _key and _qty>0 and not _is_summary_item(_r):
            detailed_keys.add(_key)

    keyed_materials=set()
    for r in takeoff.get("rows", []):
        key=str(r.get("material_key") or "")
        qty=_f(r.get("accepted_quantity",r.get("quantity")))
        unit=str(r.get("unit") or "")
        if not key or qty<=0:
            continue
        if _is_summary_item(r) and key in detailed_keys:
            continue
        keyed_materials.add(key)
        if unit=="t":
            volume=qty/7.85
        elif unit=="m2":
            thickness_m=_f(r.get("material_thickness_m"))
            volume=qty*thickness_m
        else:
            volume=qty
        capacity=volume*MATERIAL_HEAT_CAPACITY_MJ_M3K.get(key,0.0)
        thermal_capacity+=capacity
        thermal_breakdown.append({
            "material":key,"source_item":str(r.get("item") or ""),
            "quantity":qty,"effective_volume_m3":volume,
            "heat_capacity_MJ_K":capacity,
        })

    # PATCH_527: some current RC takeoff rows are English-canonical structure
    # rows without material_key.  After Module 1 synchronizes final physical
    # component volumes into profile.construction, use that component ledger as
    # the full (not active-fraction) material heat-capacity basis.  This keeps
    # Module 1's displayed material capacity complete while Module 2 separately
    # applies exterior/partition/frame/slab active fractions for the 8760 solver.
    if "concrete" not in keyed_materials:
        component_volume = sum(max(0.0,_f(construction.get(k))) for k in (
            "exterior_rc_volume_m3","partition_rc_volume_m3","frame_rc_volume_m3",
            "ground_slab_volume_m3","upper_slab_volume_m3","foundation_rc_volume_m3"
        ))
        if component_volume>0.0:
            capacity=component_volume*MATERIAL_HEAT_CAPACITY_MJ_M3K["concrete"]
            thermal_capacity+=capacity
            thermal_breakdown.append({
                "material":"concrete","source_item":"Module 1 final RC component ledger",
                "quantity":component_volume,"effective_volume_m3":component_volume,
                "heat_capacity_MJ_K":capacity,
            })
            keyed_materials.add("concrete")

    material_map = [
        ("コンクリート合計", "concrete", "m3"),
        ("鉄筋", "reinforcing_steel", "t"),
        ("構造用鉄骨", "structural_steel", "t"),
        ("2×6・一般構造木材", "dimension_lumber", "m3"),
        ("CLT・Mass Timber", "clt", "m3"),
        ("石膏ボード13mm", "gypsum_board", "m2"),
    ]
    for label, key, unit in material_map:
        if key in keyed_materials:
            continue
        qty = accepted.get(label, 0.0)
        if qty <= 0:
            continue
        if unit == "t":
            # Approximate volume for thermal-capacity accounting.
            volume = qty / 7.85
        elif unit == "m2":
            volume = qty * 0.013
        else:
            volume = qty
        capacity = volume * MATERIAL_HEAT_CAPACITY_MJ_M3K.get(key, 0.0)
        thermal_capacity += capacity
        thermal_breakdown.append({
            "material": key, "source_item": label, "quantity": qty,
            "effective_volume_m3": volume, "heat_capacity_MJ_K": capacity
        })

    equipment_rows = []
    total_equipment_kwh = 0.0
    nominal_hvac_kwh = 0.0
    for item in equipment:
        rated_kw = _f(item.get("rated_kw"))
        quantity = _f(item.get("quantity"), 1.0)
        hours = _f(item.get("annual_hours"))
        load_factor = _f(item.get("load_factor"), 1.0)
        efficiency = max(_f(item.get("efficiency"), 1.0), 0.01)
        annual_kwh = rated_kw * quantity * hours * load_factor / efficiency
        # Space-conditioning energy is calculated dynamically in Module 2.
        # Do not add the nominal air-conditioning entry again as other equipment.
        if str(item.get("name", "")) == "air_conditioning":
            nominal_hvac_kwh += annual_kwh
        else:
            total_equipment_kwh += annual_kwh
        row = dict(item)
        row["annual_energy_kwh"] = annual_kwh
        equipment_rows.append(row)

    return {
        "status": ("incomplete_envelope_specification" if unresolved_parts else "provisional_planning_value"),
        "envelope": {
            "indicative_ua_W_m2K": indicative_ua,
            "envelope_area_m2": envelope_area,
            "insulation_details": insulation_details,
            "window_area_m2": window_area,
            "window_u_W_m2K": window_u,
            "door_area_m2": door_area,
            "door_u_W_m2K": door_u,
            "unresolved_parts": unresolved_parts,
            "is_complete": len(unresolved_parts)==0,
        },
        "thermal_mass": {
            "effective_heat_capacity_MJ_K": thermal_capacity,
            "breakdown": thermal_breakdown
        },
        "equipment": {
            "annual_electricity_kwh": total_equipment_kwh,
            "annual_other_equipment_electricity_kwh": total_equipment_kwh,
            "annual_nominal_hvac_reference_kwh": nominal_hvac_kwh,
            "input_basis": "per_dwelling",
            "items": equipment_rows
        },
        "disclaimer": "Provisional planning comparison only."
    }
