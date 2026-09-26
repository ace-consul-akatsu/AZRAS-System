
from __future__ import annotations
import csv
import json
from pathlib import Path
from typing import Any



def _f(value: Any, default: float = 0.0) -> float:
    try:
        if value is None or value == "":
            return float(default)
        return float(value)
    except (TypeError, ValueError):
        return float(default)

def _row(category: str, item: str, quantity: float, unit: str, confidence: float,
         source_mode: str, formula: str, evidence: str, editable: bool = True) -> dict[str, Any]:
    return {
        "category": category,
        "item": item,
        "quantity": round(float(quantity), 6),
        "unit": unit,
        "confidence": round(max(0.0, min(1.0, confidence)), 3),
        "source_mode": source_mode,
        "formula": formula,
        "evidence": evidence,
        "editable": editable,
        "accepted_quantity": round(float(quantity), 6),
    }


def _roof_data(profile: dict[str, Any]) -> tuple[float, float, list[dict[str, Any]]]:
    roof_model = profile.get("roof_model", {})
    planes = roof_model.get("planes", [])
    roof_area = sum(_f(p.get("area_m2")) for p in planes)
    if roof_area <= 0:
        roof_area = _f(profile.get("geometry", {}).get("roof_area_m2"))
    skylights = [s for p in planes for s in p.get("skylights", [])]
    skylight_area = sum(_f(s.get("area_m2")) for s in skylights)
    return roof_area, skylight_area, planes


def generate_takeoff(
    building_type: str,
    profile: dict[str, Any],
    assumptions: dict[str, Any],
    ai_result: dict[str, Any] | None = None,
    rebar_takeoff: dict[str, Any] | None = None,
) -> dict[str, Any]:
    g = profile["geometry"]
    c = profile["construction"]
    a = profile["assemblies"]
    surfaces = profile.get("surfaces", [])
    roof_area, skylight_area, roof_planes = _roof_data(profile)

    floor_area = _f(g.get("floor_area_m2"))
    footprint = _f(g.get("footprint_m2"))
    slab_area = _f(g.get("slab_area_m2"), footprint)
    wall_opaque = sum(_f(s.get("opaque_area_m2")) for s in surfaces)
    window_area = sum(_f(s.get("window_area_m2")) for s in surfaces)
    door_area = sum(_f(s.get("door_area_m2")) for s in surfaces)
    opening_takeoff = profile.get("opening_takeoff", {}) or {}
    if window_area <= 0:
        window_area = float(opening_takeoff.get("window_area_m2", 0.0) or 0.0)
    if door_area <= 0:
        door_area = float(opening_takeoff.get("door_area_m2", 0.0) or 0.0)

    cv = c.get("concrete_volume_m3", {})
    rows: list[dict[str, Any]] = []

    # Concrete – use drawing/profile values by component.
    concrete_parts = [
        ("Foundation / slab-on-grade concrete", "slab_foundation"),
        ("RC wall concrete", "rc_walls"),
        ("Column concrete", "columns"),
        ("Beam concrete", "beams"),
        ("Upper-floor / roof slab concrete", "upper_slabs"),
        ("Isolated footing / grade beam concrete", "underground_foundations"),
    ]
    for label, key in concrete_parts:
        value = _f(cv.get(key))
        if value > 0:
            rows.append(_row(
                "Structure", label, value, "m3", 0.93, "Drawing / profile",
                f"Component quantity by structure: concrete_volume_m3.{key}",
                "Drawing input or confirmed comparison-model value"
            ))
    concrete_total = _f(cv.get("total"), sum(_f(cv.get(k)) for _, k in concrete_parts))
    rows.append(_row(
        "Structure", "Total concrete", concrete_total, "m3", 0.95, "Aggregation",
        "Sum of concrete components", "Structure / material quantity profile", editable=False
    ))

    avg = assumptions["average_intensities"]
    # Rebar: structural-drawing takeoff for AZRAS when available, otherwise average intensity.
    recognized_rebar = None
    if ai_result:
        recognized_rebar = next(
            (x for x in ai_result.get("candidates", []) if x.get("field") == "reinforcing_steel_t"),
            None
        )
    if recognized_rebar:
        rebar_t = float(recognized_rebar["value"])
        rows.append(_row(
            "Structure", "Reinforcing steel", rebar_t, "t", float(recognized_rebar.get("confidence", 0.9)),
            "Structural drawing calculation", "Theoretical takeoff from structural reinforcement schedules and plans",
            "Linked AI recognition result with AZRAS detailed reinforcement takeoff"
        ))
    elif building_type == "AZRAS" and rebar_takeoff:
        rebar_t = float(rebar_takeoff["net_theoretical_rebar_t"])
        rows.append(_row(
            "Structure", "Reinforcing steel", rebar_t, "t", 0.90, "Structural drawing calculation",
            "Theoretical wall / foundation reinforcement takeoff from Takashima plan 0.pdf",
            "azras_rebar_takeoff_v6_1.json"
        ))
    else:
        intensity = float(avg["reinforcement_kg_per_m3_concrete"].get(building_type, 0.0))
        rebar_t = concrete_total * intensity / 1000.0
        rows.append(_row(
            "Structure", "Reinforcing steel", rebar_t, "t", 0.45, "Average unit intensity",
            f"{concrete_total:.3f} m3 × {intensity:.1f} kg/m3 ÷ 1000",
            "Structural drawings not provided; replace with verified quantity"
        ))

    steel_key = "Steel Frame" if building_type == "Steel Structure" else building_type
    steel_intensity = _f(avg["structural_steel_kg_per_m2_floor"].get(steel_key, 0.0))
    structural_steel_t = floor_area * steel_intensity / 1000.0
    if structural_steel_t > 0 or building_type in {"Steel Frame","Steel Structure"}:
        rows.append(_row(
            "Structure", "Structural steel", structural_steel_t, "t",
            0.42 if steel_intensity else 0.25, "Provisional general specification / designer editable",
            f"{floor_area:.3f} m2 × {steel_intensity:.1f} kg/m2 ÷ 1000",
            "Provisional general specification when total structural-steel weight cannot be confirmed from current PDFs; designer may replace with verified quantity"
        ))

    timber_building_types = {
        "2x6 Timber","2×6 Timber","Wood Post-and-Beam","Wood Framed-Wall",
        "Mass Timber","CLT","AZRAS"
    }
    lumber_intensity = float(avg["dimension_lumber_m3_per_m2_floor"].get(building_type, 0.0))
    lumber_m3 = floor_area * lumber_intensity if building_type in timber_building_types else 0.0
    if lumber_m3 > 0:
        rows.append(_row(
            "Structure", "2×6 / general structural timber", lumber_m3, "m3", 0.48, "Average unit intensity",
            f"{floor_area:.3f} m2 × {lumber_intensity:.4f} m3/m2",
            "Provisional value when timber takeoff schedule is unavailable"
        ))

    clt_intensity = float(avg["clt_m3_per_m2_floor"].get(building_type, 0.0))
    clt_m3 = floor_area * clt_intensity
    if clt_m3 > 0 or building_type == "CLT":
        rows.append(_row(
            "Structure", "CLT / Mass Timber", clt_m3, "m3", 0.45, "Average unit intensity",
            f"{floor_area:.3f} m2 × {clt_intensity:.4f} m3/m2",
            "Provisional value when CLT panel layout is unavailable"
        ))

    # Insulation by area × thickness.
    # PATCH_416: preserve PATCH_404 current RC exterior-surface key after final integration.
    rc_area = _f(c.get("exterior_rc_interior_surface_m2"))
    if rc_area <= 0.0:
        rc_area = _f(c.get("rc_wall_area_m2"))
    light_area = _f(c.get("light_wall_area_m2"))
    insulation_rows = [
        ("RC exterior-wall phenolic foam", rc_area, _f((a.get("rc_wall") or {}).get("thickness_mm")), a["rc_wall"].get("material", "")),
        ("Timber exterior-wall phenolic foam", light_area, _f((a.get("light_wall") or {}).get("thickness_mm")), a["light_wall"].get("material", "")),
        ("Roof insulation", max(0.0, roof_area - skylight_area), _f((a.get("roof") or {}).get("thickness_mm")), a["roof"].get("material", "")),
        ("Under-foundation insulation", slab_area, _f((a.get("slab") or {}).get("thickness_mm")), a["slab"].get("material", "")),
    ]
    for label, area, mm, material in insulation_rows:
        qty = area * mm / 1000.0
        if qty > 0:
            rows.append(_row(
                "Insulation", label, qty, "m3", 0.88, "Drawing-dimension calculation",
                f"{area:.3f} m2 × {mm:.1f} mm ÷ 1000",
                f"Material={material}; calculated from area and thickness"
            ))

    # Sheathing / interior finish – explicit, editable takeoff.
    explicit_plywood_area = float(c.get("structural_plywood_area_m2", 0.0) or 0.0)
    if explicit_plywood_area > 0:
        rows.append(_row(
            "Substrate / finish", "Structural plywood 12 mm", explicit_plywood_area, "m2",
            0.90, "Drawing-stated quantity", "construction.structural_plywood_area_m2",
            "Current PDF / confirmed quantity"
        ))
    elif building_type in timber_building_types:
        plywood_wall_area = light_area
        plywood_roof_area = max(0.0, roof_area - skylight_area)
        if plywood_wall_area + plywood_roof_area > 0:
            rows.append(_row(
                "Substrate / finish", "Structural plywood 12 mm", plywood_wall_area + plywood_roof_area, "m2",
                0.68, "Specification / area calculation",
                f"Exterior wall {plywood_wall_area:.3f} + roof {plywood_roof_area:.3f}",
                "Timber systems only; verify against final drawing quantities"
            ))

    # Gypsum board is a finish quantity, not a floor/roof-area surrogate for RC.
    explicit_gypsum_area = float(c.get("gypsum_board_area_m2", 0.0) or 0.0)
    if explicit_gypsum_area > 0:
        rows.append(_row(
            "Substrate / finish", "Gypsum board 13 mm", explicit_gypsum_area, "m2", 0.90,
            "Drawing-stated quantity", "construction.gypsum_board_area_m2",
            "Confirmed wall / ceiling finish area"
        ))
    elif building_type in timber_building_types:
        gypsum_area = wall_opaque + max(0.0, roof_area - skylight_area)
        if gypsum_area > 0:
            rows.append(_row(
                "Substrate / finish", "Gypsum board 13 mm", gypsum_area, "m2", 0.60,
                "Specification / area calculation",
                f"Exterior opaque wall {wall_opaque:.3f} + ceiling/roof {max(0.0, roof_area-skylight_area):.3f}",
                "Provisional timber-system value; verify interior partitions and multiple layers separately"
            ))

    # Roofing and waterproofing.
    steel_roof_area = sum(
        _f(p.get("area_m2"))
        for p in roof_planes
        if "鋼板" in str(p.get("roofing", "")) or building_type in ("AZRAS", "2x6 Timber", "Wood Post-and-Beam", "Wood Framed-Wall", "Steel Structure", "RC Wall Structure", "Other")
    )
    if steel_roof_area > 0:
        if building_type in {"Steel Frame","Steel Structure"}:
            rows.append(_row(
                "Roof", "Insulated double-skin folded-plate roof (projected area)", steel_roof_area, "m2", 0.82,
                "Current PDF roof plan / section", "Total projected roof area",
                "Current PDF specifies insulated double-skin folded plate; reconcile actual sloped area after roof pitch confirmation"
            ))
        else:
            rows.append(_row(
                "Roof", "Pre-painted steel standing-seam roofing", steel_roof_area, "m2", 0.88,
                "Roof plan / specification", "Total applicable roof area", "Aggregated from finish specified for each roof plane"
            ))
    waterproof_area = sum(
        _f(p.get("area_m2"))
        for p in roof_planes
        if "防水" in str(p.get("roofing", "")) or building_type in ("RC Frame", "RC Wall Structure")
    )
    if waterproof_area > 0:
        rows.append(_row(
            "Roof", "Exposed liquid-applied waterproofing 5 mm", waterproof_area, "m2", 0.86,
            "Roof plan / specification", "Total applicable RC roof area", "Specification includes polymer-cement / mesh substrate"
        ))

    # Openings.
    rows.append(_row(
        "Openings", "Exterior window glazing", window_area, "m2", 0.88, "Elevation / opening area",
        "Sum of window areas on exterior wall surfaces", "Orientation-based opening data"
    ))
    rows.append(_row(
        "Openings", "Exterior doors", door_area, "m2", 0.82, "Elevation / opening area",
        "Sum of door areas on exterior wall surfaces", "Entrance doors etc."
    ))
    if skylight_area > 0:
        rows.append(_row(
            "Openings", "Skylights / rooflights", skylight_area, "m2", 0.78,
            "Roof plan", "Sum of skylight areas on roof planes", "U-value and SHGC are set individually"
        ))

    # Summary and quality flags.
    low_confidence = [r["item"] for r in rows if r["confidence"] < 0.60]
    provisional = [r["item"] for r in rows if r["source_mode"] == "Average unit intensity"]
    result = {
        "version": "6.3",
        "canonical_language": "en",
        "canonical_schema_version": "1.0",
        "building_type": building_type,
        "rows": rows,
        "summary": {
            "row_count": len(rows),
            "low_confidence_items": low_confidence,
            "provisional_items": provisional,
            "overall_confidence": round(sum(r["confidence"] for r in rows) / max(1, len(rows)), 3),
            "floor_area_m2": floor_area,
            "roof_area_m2": roof_area,
            "window_area_m2": window_area,
            "door_area_m2": door_area,
            "skylight_area_m2": skylight_area,
        },
        "disclaimer": (
            "AI-assisted quantity takeoff combines drawing text, confirmed profiles, area calculations, and representative unit intensities. "
            "These quantities are for planning and comparison. Replace items marked average unit intensity, low confidence, or estimated with verified quantities from structural drawings, shop drawings, "
            "opening schedules, finish schedules, bills of quantities, or actual records. Do not use them to establish structural safety or contractual quantities."
        ),
    }
    return result


def export_takeoff_csv(result: dict[str, Any], path: str | Path) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    fields = [
        "category", "item", "accepted_quantity", "unit", "confidence",
        "source_mode", "formula", "evidence"
    ]
    with p.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        for row in result["rows"]:
            writer.writerow({k: row.get(k, "") for k in fields})


def export_takeoff_json(result: dict[str, Any], path: str | Path) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
