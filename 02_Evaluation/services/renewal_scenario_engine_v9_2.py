
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

def _year_series_with_resets(cycle: int, period: int, reset_years: list[int] | set[int]) -> list[int]:
    """Generate lifecycle years while resetting component age to zero at each reset year.

    Events that would fall exactly on a reset year are omitted because the reset
    intervention itself (full rebuild / all-infill refresh) dominates that year.
    """
    if cycle <= 0:
        return []

    resets = sorted({int(y) for y in reset_years if 0 < int(y) <= period})
    anchors = [0] + resets
    years: list[int] = []

    for idx, start in enumerate(anchors):
        next_reset = resets[idx] if idx < len(resets) else None
        year = start + cycle
        while year <= period and (next_reset is None or year < next_reset):
            years.append(year)
            year += cycle

    return years

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
                      keep_same_use_scale: bool = True,
                      rebuild_cycle_years: int | None = None) -> dict[str, Any]:
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

    profile_full_rebuild_years = sorted({
        int(y) for y in profile.get("full_rebuild_years", [])
        if 0 < int(y) <= period_years
    })
    profile_default_rebuild_cycle_years = max(
        int(profile.get("default_rebuild_cycle_years", 0) or 0), 0
    )
    profile_rebuild_cycle_basis = str(
        profile.get(
            "rebuild_cycle_basis_ja" if language == "ja" else "rebuild_cycle_basis_en",
            "Evaluation standard scenario"
        )
    )
    profile_rebuild_cycle_editable = bool(profile.get("rebuild_cycle_editable", profile_key != "AZRAS"))

    # User-selectable rebuild cycle for rebuild-based construction profiles.
    # AZRAS remains "no full rebuild" in Evaluation; its 100/200-year event is
    # an all-infill refresh while the RC core is retained.
    if profile_key == "AZRAS":
        applied_rebuild_cycle_years = 0
        full_rebuild_years = []
        rebuild_cycle_source = "AZRAS_no_full_rebuild"
    elif rebuild_cycle_years is not None:
        applied_rebuild_cycle_years = max(int(rebuild_cycle_years), 0)
        full_rebuild_years = (
            list(range(applied_rebuild_cycle_years, period_years + 1, applied_rebuild_cycle_years))
            if applied_rebuild_cycle_years > 0 else []
        )
        rebuild_cycle_source = "module3_user_input"
    else:
        applied_rebuild_cycle_years = profile_default_rebuild_cycle_years
        full_rebuild_years = (
            list(range(applied_rebuild_cycle_years, period_years + 1, applied_rebuild_cycle_years))
            if applied_rebuild_cycle_years > 0 else []
        )
        rebuild_cycle_source = "profile_default"

    azras_reset_years={y for y in (100,200) if y <= period_years} if profile_key=="AZRAS" else set()

    def component_reset_years(comp_key: str) -> list[int]:
        # A full rebuild renews the entire building, so every component age resets.
        if full_rebuild_years:
            return list(full_rebuild_years)

        # AZRAS all-infill refresh renews infill/finishes/equipment only.
        # The retained RC core keeps its original age and inspection clock.
        if profile_key == "AZRAS" and comp_key != profile["skeleton_component"]:
            return sorted(azras_reset_years)

        return []

    # Inspection and repair events.
    active_components = list(dict.fromkeys(
        [profile["skeleton_component"]] + INFILL_COMPONENTS + equipment_components
    ))
    for comp_key in active_components:
        comp = components[comp_key]
        for year in _year_series_with_resets(int(comp["inspection_years"]), period_years, component_reset_years(comp_key)):
            if year in full_rebuild_years:
                continue

            # AZRAS 100/200-year all-infill refresh replaces all infill,
            # finishes and equipment. Their same-year periodic inspections
            # would be absorbed by the renewal work and must not be charged
            # separately. The retained RC core is the only component that
            # keeps its independent inspection event.
            if (
                profile_key == "AZRAS"
                and year in azras_reset_years
                and comp_key != profile["skeleton_component"]
            ):
                continue

            events.append({
                "year": year, "action": "inspection", "component_key": comp_key,
                "component": _component_name(comp, language), "scope": "partial",
                "retained_fraction": 1.0, "removed_fraction": 0.0,
                "reused_fraction": 0.0, "recycled_fraction": 0.0,
                "layout_change": "", "basis": "inspection_cycle"
            })
        for year in _year_series_with_resets(int(comp["repair_years"]), period_years, component_reset_years(comp_key)):
            if year in full_rebuild_years or year in azras_reset_years:
                continue

            # Structural skeleton repairs are condition-based in Evaluation.
            # A fixed-cycle "10% removal + 10% replacement" assumption would
            # arbitrarily penalize RC, AZRAS, or timber skeletons without a
            # diagnosed deterioration quantity. Periodic inspections remain;
            # actual structural repair quantities belong in Professional once
            # detailed drawings/condition information are available.
            if comp["category"] == "skeleton":
                continue

            action = "repair"
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
        for year in _year_series_with_resets(int(comp["renewal_years"]), period_years, component_reset_years(comp_key)):
            if year in full_rebuild_years or year in azras_reset_years:
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
        for year in _year_series_with_resets(int(comp["renewal_years"]), period_years, component_reset_years(comp_key)):
            if year in full_rebuild_years or year in azras_reset_years:
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
                "retained_fraction": 1.00, "removed_fraction": 0.00,
                "reused_fraction": 0.00,
                "recycled_fraction": 0.00,
                "layout_change": _layout_description(year, layout_policy, language),
                "basis": "azras_200year_core_retention"
            })
            events.append({
                "year": year, "action": "replace_infill", "component_key": "all_infill",
                "component": "全インフィル" if language == "ja" else "All Infill",
                "scope": "all", "retained_fraction": 0.0, "removed_fraction": 1.0,
                "reused_fraction": 0.10, "recycled_fraction": 0.65,
                "layout_change": _layout_description(year, layout_policy, language),
                "basis": "azras_full_infill_refresh"
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

    # De-duplicate same-year / same-component lifecycle actions.
    # One dominant physical intervention per component and year:
    # replacement/renewal > repair > inspection.
    # State/strategy events such as retain_skeleton are intentionally excluded.
    replacement_actions = {"replace_equipment", "replace_infill"}
    repair_actions = {"repair", "skeleton_repair"}
    inspection_actions = {"inspection"}

    grouped = {}
    passthrough = []
    for event in events:
        action = event.get("action")
        if action in replacement_actions | repair_actions | inspection_actions:
            key = (int(event.get("year", 0)), str(event.get("component_key") or ""))
            grouped.setdefault(key, []).append(event)
        else:
            passthrough.append(event)

    deduplicated = []
    suppressed_same_year_component_events = []
    for key, group in grouped.items():
        actions = {e.get("action") for e in group}
        if actions & replacement_actions:
            keep_actions = replacement_actions
            kept_class = "replacement"
        elif actions & repair_actions:
            keep_actions = repair_actions
            kept_class = "repair"
        else:
            keep_actions = inspection_actions
            kept_class = "inspection"

        for event in group:
            if event.get("action") in keep_actions:
                deduplicated.append(event)
            else:
                suppressed_same_year_component_events.append({
                    "year": event.get("year"),
                    "component_key": event.get("component_key"),
                    "component": event.get("component"),
                    "suppressed_action": event.get("action"),
                    "kept_action_class": kept_class,
                    "reason": "same_year_same_component_priority"
                })

    events = passthrough + deduplicated

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
    final_retained_fraction = 1.00 if profile_key == "AZRAS" else (
        0.0 if full_rebuild_years and max(full_rebuild_years) <= period_years else 1.0
    )
    return {
        "version": "9.2",
        "module": "module3",
        "period_years": period_years,
        "construction_profile": profile_key,
        "profile_definition": profile,
        "same_use_scale_after_rebuild": bool(keep_same_use_scale),
        "rebuild_cycle": {
            "profile_default_cycle_years": profile_default_rebuild_cycle_years,
            "legacy_profile_full_rebuild_years": profile_full_rebuild_years,
            "applied_cycle_years": applied_rebuild_cycle_years,
            "generated_full_rebuild_years": full_rebuild_years,
            "source": rebuild_cycle_source,
            "basis": profile_rebuild_cycle_basis,
            "editable": profile_rebuild_cycle_editable,
            "azras_policy": "no_full_rebuild_retain_rc_core" if profile_key == "AZRAS" else None
        },
        "original_use": project.get("common", {}).get("building_use", ""),
        "original_scale_gfa_m2": project.get("common", {}).get("scale_gfa_m2", 0),
        "layout_policy": layout_policy,
        "events": events,
        "event_deduplication": {
            "policy": "same_year_same_component: replacement > repair > inspection",
            "suppressed_count": len(suppressed_same_year_component_events),
            "suppressed_events": suppressed_same_year_component_events
        },
        "cycle_reset_policy": {
            "full_rebuild_resets_all_components": True,
            "full_rebuild_years": full_rebuild_years,
            "azras_all_infill_resets_infill_and_equipment_only": profile_key == "AZRAS",
            "azras_all_infill_reset_years": sorted(azras_reset_years),
            "azras_skeleton_clock_retained": profile_key == "AZRAS",
            "rule": "component lifecycle cycles restart from zero after the applicable reset event"
        },
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
