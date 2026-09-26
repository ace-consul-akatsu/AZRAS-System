
from __future__ import annotations
from copy import deepcopy
from typing import Any

EQUIPMENT_MAP = {
    "lighting": "equipment_lighting",
    "outlets": "equipment_outlets",
    "air_conditioning": "equipment_hvac",
    "ventilation": "equipment_ventilation",
    "refrigerator": "equipment_refrigerator",
}

INFILL_COMPONENTS = ["infill_layout", "infill_exterior", "insulation", "windows", "roof"]

def _year_series(cycle: int, period: int) -> list[int]:
    if cycle <= 0:
        return []
    return list(range(cycle, period + 1, cycle))

def _component_name(component: dict[str, Any], language: str) -> str:
    return str(component.get("ja" if language == "ja" else "en", ""))

def _layout_description(year: int, policy: str, language: str) -> str:
    phase = "future"
    if year <= 50:
        phase = "near"
    elif year <= 100:
        phase = "middle"
    elif year <= 150:
        phase = "long"
    if language == "ja":
        table = {
            "adaptive": {
                "near":"世帯構成・働き方の変化に対応する間取りへ更新",
                "middle":"可変間仕切りと設備集約型の間取りへ更新",
                "long":"高齢者・AI・遠隔医療対応を含む柔軟な間取りへ更新",
                "future":"用途は維持し、将来需要に合わせて全面的に間取りを再設計"
            },
            "accessibility": {
                "near":"段差解消・水回り改善・移動幅確保",
                "middle":"介助・見守り・遠隔医療対応へ更新",
                "long":"高齢者・多世代共生型へ更新",
                "future":"用途・規模を維持し、完全バリアフリーへ再設計"
            },
            "flexible": {
                "near":"可動間仕切りと設備配管ゾーンを導入",
                "middle":"住戸分割・統合に対応する間取りへ更新",
                "long":"多用途・在宅勤務・短期利用に対応",
                "future":"用途・規模を維持し、完全可変型へ再設計"
            }
        }
    else:
        table = {
            "adaptive": {
                "near":"Renew the layout for changing household structures and work styles.",
                "middle":"Renew as a flexible-partition layout with consolidated services.",
                "long":"Renew for ageing, AI systems and remote healthcare.",
                "future":"Keep use and scale while redesigning the entire layout for future demand."
            },
            "accessibility": {
                "near":"Remove level differences and improve circulation and wet areas.",
                "middle":"Renew for assistance, monitoring and remote healthcare.",
                "long":"Renew for ageing and multi-generation living.",
                "future":"Keep use and scale while redesigning as fully accessible."
            },
            "flexible": {
                "near":"Introduce movable partitions and service zones.",
                "middle":"Renew for unit subdivision and combination.",
                "long":"Support mixed use, remote work and short-term occupancy.",
                "future":"Keep use and scale while redesigning as fully flexible."
            }
        }
    return table.get(policy, table["adaptive"])[phase]

def generate_scenario(project: dict[str, Any], component_db: dict[str, Any],
                      profile_db: dict[str, Any], profile_key: str,
                      period_years: int = 200, language: str = "ja",
                      layout_policy: str = "adaptive",
                      keep_same_use_scale: bool = True) -> dict[str, Any]:
    module1 = project.get("module_outputs", {}).get("module1")
    if not module1:
        raise ValueError("Module 1 output is required.")
    profile = deepcopy(profile_db["profiles"][profile_key])
    components = deepcopy(component_db["components"])
    events: list[dict[str, Any]] = []

    # Which equipment was actually configured in Module 1?
    configured = {
        str(x.get("name")) for x in
        module1.get("building_performance", {}).get("equipment", {}).get("items", [])
    }
    equipment_components = [
        comp for name, comp in EQUIPMENT_MAP.items()
        if not configured or name in configured
    ]

    full_rebuild_years = sorted({
        int(y) for y in profile.get("full_rebuild_years", [])
        if 0 < int(y) <= period_years
    })

    # Inspection and repair events.
    active_components = list(dict.fromkeys(
        [profile["skeleton_component"]] + INFILL_COMPONENTS + equipment_components
    ))
    for comp_key in active_components:
        comp = components[comp_key]
        for year in _year_series(int(comp["inspection_years"]), period_years):
            if year in full_rebuild_years:
                continue
            events.append({
                "year": year, "action": "inspection", "component_key": comp_key,
                "component": _component_name(comp, language), "scope": "partial",
                "retained_fraction": 1.0, "removed_fraction": 0.0,
                "reused_fraction": 0.0, "recycled_fraction": 0.0,
                "layout_change": "", "basis": "inspection_cycle"
            })
        for year in _year_series(int(comp["repair_years"]), period_years):
            if year in full_rebuild_years:
                continue
            action = "skeleton_repair" if comp["category"] == "skeleton" else "repair"
            events.append({
                "year": year, "action": action, "component_key": comp_key,
                "component": _component_name(comp, language), "scope": "partial",
                "retained_fraction": 0.90, "removed_fraction": 0.10,
                "reused_fraction": 0.02,
                "recycled_fraction": 0.10 * float(comp["recyclable_fraction"]),
                "layout_change": "", "basis": "repair_cycle"
            })

    # Equipment replacement.
    for comp_key in equipment_components:
        comp = components[comp_key]
        for year in _year_series(int(comp["renewal_years"]), period_years):
            if year in full_rebuild_years:
                continue
            events.append({
                "year": year, "action": "replace_equipment", "component_key": comp_key,
                "component": _component_name(comp, language), "scope": "all",
                "retained_fraction": 0.0, "removed_fraction": 1.0,
                "reused_fraction": float(comp["reusable_fraction"]),
                "recycled_fraction": float(comp["recyclable_fraction"]),
                "layout_change": "", "basis": "equipment_life"
            })

    # Infill replacement, including skeleton-infill contents.
    for comp_key in INFILL_COMPONENTS:
        comp = components[comp_key]
        for year in _year_series(int(comp["renewal_years"]), period_years):
            if year in full_rebuild_years:
                continue
            layout = _layout_description(year, layout_policy, language) if comp_key == "infill_layout" else ""
            events.append({
                "year": year, "action": "replace_infill", "component_key": comp_key,
                "component": _component_name(comp, language), "scope": "all",
                "retained_fraction": 0.0, "removed_fraction": 1.0,
                "reused_fraction": float(comp["reusable_fraction"]),
                "recycled_fraction": float(comp["recyclable_fraction"]),
                "layout_change": layout, "basis": "infill_life"
            })

    # Full rebuild or AZRAS long-life skeleton retention.
    skeleton_key = profile["skeleton_component"]
    skeleton = components[skeleton_key]
    if profile_key == "AZRAS":
        # At 100 years renew all infill/equipment but retain the RC core.
        for year in [100, 200]:
            if year > period_years:
                continue
            events.append({
                "year": year, "action": "retain_skeleton", "component_key": skeleton_key,
                "component": _component_name(skeleton, language), "scope": "all",
                "retained_fraction": 0.90, "removed_fraction": 0.10,
                "reused_fraction": 0.90,
                "recycled_fraction": 0.10 * float(skeleton["recyclable_fraction"]),
                "layout_change": _layout_description(year, layout_policy, language),
                "basis": "azras_skeleton_infill_strategy"
            })
            events.append({
                "year": year, "action": "partial_demolition", "component_key": "all_infill",
                "component": "全インフィル" if language == "ja" else "All Infill",
                "scope": "all", "retained_fraction": 0.0, "removed_fraction": 1.0,
                "reused_fraction": 0.10, "recycled_fraction": 0.65,
                "layout_change": _layout_description(year, layout_policy, language),
                "basis": "azras_infill_replacement"
            })
    else:
        for year in full_rebuild_years:
            events.append({
                "year": year, "action": "full_rebuild", "component_key": "whole_building",
                "component": "建物全体" if language == "ja" else "Whole Building",
                "scope": "all", "retained_fraction": 0.0, "removed_fraction": 1.0,
                "reused_fraction": float(skeleton["reusable_fraction"]),
                "recycled_fraction": float(skeleton["recyclable_fraction"]),
                "layout_change": _layout_description(year, layout_policy, language),
                "basis": "profile_rebuild_cycle",
                "same_use_scale": bool(keep_same_use_scale)
            })

    # Sort and assign event IDs.
    priority = {
        "inspection": 1, "repair": 2, "skeleton_repair": 3,
        "replace_equipment": 4, "replace_infill": 5,
        "partial_demolition": 6, "retain_skeleton": 7, "full_rebuild": 8
    }
    events.sort(key=lambda e: (e["year"], priority.get(e["action"], 99), e["component"]))
    for index, event in enumerate(events, 1):
        event["event_id"] = f"M3-{index:04d}"

    counts = {
        "events_count": len(events),
        "inspections": sum(e["action"] == "inspection" for e in events),
        "repairs": sum(e["action"] == "repair" for e in events),
        "equipment_updates": sum(e["action"] == "replace_equipment" for e in events),
        "infill_updates": sum(e["action"] == "replace_infill" for e in events),
        "skeleton_repairs": sum(e["action"] == "skeleton_repair" for e in events),
        "partial_demolitions": sum(e["action"] == "partial_demolition" for e in events),
        "full_rebuilds": sum(e["action"] == "full_rebuild" for e in events),
        "skeleton_retention_events": sum(e["action"] == "retain_skeleton" for e in events)
    }
    final_retained_fraction = 0.90 if profile_key == "AZRAS" else (
        0.0 if full_rebuild_years and max(full_rebuild_years) <= period_years else 1.0
    )
    return {
        "version": "9.2",
        "module": "module3",
        "period_years": period_years,
        "construction_profile": profile_key,
        "profile_definition": profile,
        "same_use_scale_after_rebuild": bool(keep_same_use_scale),
        "original_use": project.get("common", {}).get("building_use", ""),
        "original_scale_gfa_m2": project.get("common", {}).get("scale_gfa_m2", 0),
        "layout_policy": layout_policy,
        "events": events,
        "summary": {
            **counts,
            "final_skeleton_retained_fraction": final_retained_fraction,
            "event_years": sorted({e["year"] for e in events})
        },
        "handoff": {
            "module4_environment_200": {
                "uses": ["removed_fraction", "reused_fraction", "recycled_fraction",
                         "component_key", "year", "action"]
            },
            "module7_repair_demolition_cost": {
                "uses": ["component_key", "year", "action", "scope", "removed_fraction"]
            }
        },
        "status": "provisional_planning_scenario"
    }
