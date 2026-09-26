from __future__ import annotations

import copy
import json
import os
import shutil
import tempfile
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCHEMA_VERSION = "3.0"
PLATFORM_VERSION = "9.4.0"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _common_defaults() -> dict[str, Any]:
    return {
        # Backward-compatible flat common fields used by Modules 0-9.
        "project_name": "",
        "azras_project_number": "",
        "country": "Japan",
        "city": "",
        "address": "",
        "latitude": "",
        "longitude": "",
        "google_coordinate_source": "",
        "building_use": "Residential",
        "storeys": 0,
        "floor_areas_m2": [],
        "scale_gfa_m2": 0.0,
        "roof_area_m2": 0.0,
        "exterior_wall_area_m2": 0.0,
        "window_area_m2": 0.0,
        "north_window_area_m2": 0.0,
        "east_window_area_m2": 0.0,
        "south_window_area_m2": 0.0,
        "west_window_area_m2": 0.0,
        "north_rotation_deg": None,
        # Structured V9.4 common sections. These are the stable interface for
        # future PV calculations and the separate Comparison Platform.
        "project_identity": {
            "project_name": "",
            "azras_project_number": "",
            "project_language": "ja",
            "currency": "JPY",
        },
        "location": {
            "country": "Japan",
            "city": "",
            "address": "",
            "latitude": "",
            "longitude": "",
            "google_coordinate_raw": "",
            "weather_file": "",
            "weather_source": {},
        },
        "building": {
            "use": "Residential",
            "storeys": 0,
            "floor_areas_m2": [],
            "gross_floor_area_m2": 0.0,
            "roof_area_m2": 0.0,
            "exterior_wall_area_m2": 0.0,
            "window_area_m2": 0.0,
            "window_area_by_orientation_m2": {
                "north": 0.0, "east": 0.0, "south": 0.0, "west": 0.0
            },
            "north_rotation_deg": None,
            "source_module": "module1",
            "requires_confirmation": True,
        },
        "thermal": {
            "ua_W_m2K": None,
            "average_u_value_W_m2K": None,
            "effective_thermal_capacity_MJ_K": None,
            "heating_cop": None,
            "cooling_cop": None,
            "heat_recovery_efficiency_percent": None,
            "ventilation_ach": None,
            "source_module": "module2",
        },
        "renewable_energy": {
            "pv_enabled": False,
            "roof_utilization_percent": 80.0,
            "pv_area_m2": 0.0,
            "panel_efficiency_percent": 22.0,
            "pcs_efficiency_percent": 97.0,
            "self_consumption_percent": 80.0,
            "currency": "JPY",
            "purchase_price_local_currency_per_kWh": 30.0,
            "export_price_local_currency_per_kWh": 16.0,
            "purchase_price_JPY_per_kWh": 30.0,
            "export_price_JPY_per_kWh": 16.0,
            "annual_generation_kWh": 0.0,
            "annual_self_consumption_kWh": 0.0,
            "annual_export_kWh": 0.0,
            "annual_grid_import_kWh": 0.0,
            "annual_cost_saving_local_currency": 0.0,
            "annual_export_revenue_local_currency": 0.0,
            "annual_cost_saving_JPY": 0.0,
            "annual_export_revenue_JPY": 0.0,
            "annual_co2_reduction_kg": 0.0,
            "calculation_status": "not_calculated",
        },
        "analysis_mode": "lite",
        "detailed_configuration": {
            "building_system": "general",
            "general": {
                "structure": "",
                "method": "",
            },
            "azras": {
                "core_structure": "rc",
                "core_method": "cast_in_place",
                "infill_structure": "wood_frame",
                "infill_method": "2x6",
                "outfill_wall_structure": "wood",
                "outfill_wall_method": "timber_cladding",
                "outfill_roof_structure": "wood",
                "outfill_roof_method": "timber_truss",
                "prefabrication_type": "none",
                "prefabrication": False,
            },
            "assemblies": {
                "interior_substrate": "",
                "interior_partition": "",
                "insulation_position": "",
                "exterior_finish": "",
                "interior_finish": "",
                "notes": "",
            },
            "status": "not_configured",
        },
        "comparison_interface": {
            "schema_version": "1.0",
            "export_ready": True,
            "fixed_common_conditions": [
                "building_use", "storeys", "floor_areas_m2",
                "scale_gfa_m2", "country", "latitude", "longitude",
                "weather_file", "north_rotation_deg"
            ],
        },
    }


def new_project() -> dict[str, Any]:
    now = _now()
    return {
        "schema_version": SCHEMA_VERSION,
        "platform_version": PLATFORM_VERSION,
        "project_id": str(uuid.uuid4()),
        "created_at": now,
        "updated_at": now,
        "save_revision": 0,
        "last_saved_by": "",
        "common": _common_defaults(),
        "module_status": {},
        "audit_log": [],
        "validation": {"warnings": [], "errors": []},
        "linkage": {},
        "module_outputs": {f"module{i}": None for i in (1, 2, 5)},
        "pro_handoff": {
            "source": "",
            "generated_from_combined_pdf": False,
            "quantity_and_equipment_estimates": {},
            "drawing_inventory": [],
            "handoff": {},
            "notice": "",
        },
        "comparison_export": {
            "schema_version": "1.0",
            "generated_at": None,
            "common_building": {},
            "module_result_refs": {},
        },
    }


def _merge_defaults(target: dict[str, Any], defaults: dict[str, Any]) -> dict[str, Any]:
    for key, value in defaults.items():
        if key not in target:
            target[key] = copy.deepcopy(value)
        elif isinstance(value, dict) and isinstance(target.get(key), dict):
            _merge_defaults(target[key], value)
    return target



def _module_output_is_current_for_export(project: dict[str, Any], module_key: str) -> bool:
    """Return whether a saved current-format module output is valid for canonical export.

    Backward compatibility with pre-current Project JSON is intentionally not
    supported.  Only current-format outputs with explicit freshness metadata
    participate in canonical export.
    """
    output = (project.get("module_outputs") or {}).get(module_key)
    if not isinstance(output, dict) or not output:
        return False
    meta = output.get("_meta") if isinstance(output.get("_meta"), dict) else {}
    if meta.get("is_current") is False:
        return False
    status_info = (project.get("module_status") or {}).get(module_key)
    if isinstance(status_info, dict):
        status = str(status_info.get("status") or "")
        if status in {"recalculation_pending", "error", "stale"}:
            return False
    return True

def _synchronize_common(project: dict[str, Any]) -> None:
    c = project["common"]
    identity = c["project_identity"]
    location = c["location"]
    building = c["building"]

    # Flat fields remain authoritative for the existing UI.
    identity.update({
        "project_name": c.get("project_name", ""),
        "azras_project_number": c.get("azras_project_number", ""),
    })
    location.update({
        "country": c.get("country", "Japan"),
        "city": c.get("city", ""),
        "address": c.get("address", ""),
        "latitude": c.get("latitude", ""),
        "longitude": c.get("longitude", ""),
        "google_coordinate_raw": c.get("google_coordinate_source", "")
            or location.get("google_coordinate_raw", ""),
    })
    building.update({
        "use": c.get("building_use", "Residential"),
        "storeys": c.get("storeys", 0),
        "floor_areas_m2": c.get("floor_areas_m2", []),
        "gross_floor_area_m2": c.get("scale_gfa_m2", 0.0),
        "roof_area_m2": c.get("roof_area_m2", building.get("roof_area_m2", 0.0)),
        "exterior_wall_area_m2": c.get("exterior_wall_area_m2", 0.0),
        "window_area_m2": c.get("window_area_m2", 0.0),
        "north_rotation_deg": c.get("north_rotation_deg"),
    })
    building["window_area_by_orientation_m2"].update({
        "north": c.get("north_window_area_m2", 0.0),
        "east": c.get("east_window_area_m2", 0.0),
        "south": c.get("south_window_area_m2", 0.0),
        "west": c.get("west_window_area_m2", 0.0),
    })

    # Mirror useful saved results into the stable V9.4 common interface.
    m1 = project.get("module_outputs", {}).get("module1") or {}
    scale = m1.get("building_scale") or {}
    profile = m1.get("profile") or {}
    geometry = profile.get("geometry") or {}
    surfaces = profile.get("surfaces") or []

    if scale or geometry:
        c["storeys"] = int(
            scale.get("storeys") or geometry.get("storeys") or c.get("storeys") or 0
        )
        c["floor_areas_m2"] = (
            scale.get("floor_areas_m2") or geometry.get("floor_areas_m2")
            or c.get("floor_areas_m2") or []
        )
        c["scale_gfa_m2"] = float(
            scale.get("gross_floor_area_m2") or geometry.get("floor_area_m2")
            or c.get("scale_gfa_m2") or 0
        )
        c["roof_area_m2"] = float(
            scale.get("roof_area_m2") or geometry.get("roof_area_m2")
            or geometry.get("footprint_m2") or c.get("roof_area_m2") or 0
        )

    # PATCH 07: Module 1 is authoritative for drawing-derived envelope/opening
    # geometry. Mirror it into the stable common interface so downstream modules
    # and Compare never keep stale zero values after Module 1 has been saved.
    if surfaces:
        # PATCH_529: facade records produced by AI re-check may intentionally
        # contain only directional opening areas while gross/opaque facade area
        # stays unresolved.  The previous mirror logic converted missing opaque
        # area to zero and then wrote (window + door) as exterior wall area; for
        # the sample projects this corrupted 205.848 m2 into 62.07 m2.
        #
        # Window totals may be synchronized independently.  Exterior-wall area
        # is updated from surfaces only when at least one surface has an actual
        # gross/opaque wall-area value.  Otherwise preserve the authoritative
        # Module 1 aggregate geometry value.
        surface_wall_area = 0.0
        has_surface_wall_area = False
        window_area = 0.0
        door_area = 0.0
        door_by_orientation = {"north": 0.0, "east": 0.0, "south": 0.0, "west": 0.0}
        exact_window_surfaces = []

        for surface in surfaces:
            if not isinstance(surface, dict):
                continue
            windows = float(surface.get("window_area_m2") or 0.0)
            doors = float(surface.get("door_area_m2") or 0.0)
            window_area += windows
            door_area += doors

            gross_raw = surface.get("gross_wall_area_m2")
            opaque_raw = surface.get("opaque_area_m2")
            gross = None
            try:
                if gross_raw not in (None, "") and float(gross_raw) > 0.0:
                    gross = float(gross_raw)
                    has_surface_wall_area = True
                elif opaque_raw not in (None, "") and float(opaque_raw) > 0.0:
                    gross = float(opaque_raw) + windows + doors
                    has_surface_wall_area = True
            except (TypeError, ValueError):
                gross = None
            if gross is not None:
                surface_wall_area += gross

            local_azimuth = float(
                surface.get("local_azimuth_deg")
                if surface.get("local_azimuth_deg") is not None
                else 0.0
            ) % 360.0
            true_azimuth = float(
                surface.get("true_azimuth_deg")
                if surface.get("true_azimuth_deg") is not None
                else surface.get("azimuth_deg") or 0.0
            ) % 360.0
            # Preserve the directional door split when azimuth is canonical.
            cardinal = None
            if abs(local_azimuth - 0.0) < 1e-6: cardinal = "north"
            elif abs(local_azimuth - 90.0) < 1e-6: cardinal = "east"
            elif abs(local_azimuth - 180.0) < 1e-6: cardinal = "south"
            elif abs(local_azimuth - 270.0) < 1e-6: cardinal = "west"
            if cardinal is not None:
                door_by_orientation[cardinal] += doors

            exact_window_surfaces.append({
                "name": surface.get("name", ""),
                "local_azimuth_deg": round(local_azimuth, 6),
                "true_azimuth_deg": round(true_azimuth, 6),
                "window_area_m2": round(windows, 6),
                "door_area_m2": round(doors, 6),
                "gross_wall_area_m2": round(gross, 6) if gross is not None else None,
            })

        if has_surface_wall_area:
            c["exterior_wall_area_m2"] = round(surface_wall_area, 6)
        else:
            aggregate_wall = geometry.get("exterior_wall_area_m2")
            if aggregate_wall in (None, ""):
                aggregate_wall = profile.get("exterior_wall_area_m2")
            # Current Module 1 geometry stores the authoritative net/opaque
            # exterior-wall area by orientation.  Use its sum when no single
            # aggregate field is present.  Do NOT add openings; the stable
            # common exterior_wall_area_m2 contract is the net wall area used
            # by Module 2, while windows/doors are separate fields.
            if aggregate_wall in (None, ""):
                opaque_by_orientation = geometry.get("opaque_wall_area_by_orientation_m2") or {}
                if isinstance(opaque_by_orientation, dict):
                    opaque_sum = sum(
                        float(v or 0.0) for v in opaque_by_orientation.values()
                        if v not in (None, "")
                    )
                    if opaque_sum > 0.0:
                        aggregate_wall = opaque_sum
            try:
                if aggregate_wall not in (None, "") and float(aggregate_wall) > 0.0:
                    c["exterior_wall_area_m2"] = round(float(aggregate_wall), 6)
            except (TypeError, ValueError):
                pass
        c["window_area_m2"] = round(window_area, 6)
        building["door_area_m2"] = round(door_area, 6)
        building["door_area_by_orientation_m2"] = {
            key: round(value, 6) for key, value in door_by_orientation.items()
        }
        building["window_surfaces_by_azimuth"] = exact_window_surfaces

    building.update({
        "storeys": c.get("storeys", 0),
        "floor_areas_m2": c.get("floor_areas_m2", []),
        "gross_floor_area_m2": c.get("scale_gfa_m2", 0.0),
        "roof_area_m2": c.get("roof_area_m2", 0.0),
        "exterior_wall_area_m2": c.get("exterior_wall_area_m2", 0.0),
        "window_area_m2": c.get("window_area_m2", 0.0),
    })
    building["window_area_by_orientation_m2"].update({
        "north": c.get("north_window_area_m2", 0.0),
        "east": c.get("east_window_area_m2", 0.0),
        "south": c.get("south_window_area_m2", 0.0),
        "west": c.get("west_window_area_m2", 0.0),
    })

    m2 = project.get("module_outputs", {}).get("module2") or {}
    m2_current = _module_output_is_current_for_export(project, "module2")
    snapshot = m2.get("_input_snapshot") or {}
    settings = snapshot.get("settings") or m2.get("settings") or {}
    thermal = c["thermal"]

    # PATCH 375: common.thermal/location.weather_file are a canonical mirror
    # of Module 2.  Clear the mirror before rebuilding it so that an explicitly
    # stale retained Module 2 output cannot leak old energy/HVAC values to
    # Compare or other external consumers after save/reload.
    for key in (
        "ua_W_m2K", "average_u_value_W_m2K",
        "effective_thermal_capacity_MJ_K", "heating_cop", "cooling_cop",
        "heat_recovery_efficiency_percent", "ventilation_ach",
    ):
        thermal[key] = None
    if not m2_current:
        location["weather_file"] = ""
    else:
        field_map = {
            "heating_cop": "heating_cop",
            "cooling_cop": "cooling_cop",
            "heat_recovery_efficiency_percent": "heat_recovery_efficiency_percent",
            "ventilation_ach": "ventilation_ach",
        }
        for source, target in field_map.items():
            if settings.get(source) is not None:
                thermal[target] = settings[source]
        capacity = m2.get("effective_thermal_capacity_MJ_K")
        if capacity is None:
            capacity = m2.get("effective_dynamic_heat_capacity_MJ_per_K")
        if capacity is not None:
            thermal["effective_thermal_capacity_MJ_K"] = capacity
        average_u = m2.get("average_u_value_W_m2K")
        if average_u is not None:
            thermal["average_u_value_W_m2K"] = average_u
            thermal["ua_W_m2K"] = average_u
        weather = snapshot.get("weather_file") or m2.get("weather_file")
        if weather:
            location["weather_file"] = weather

    pv = c["renewable_energy"]
    roof_area = float(c.get("roof_area_m2") or 0.0)
    utilization = float(pv.get("roof_utilization_percent") or 80.0)
    pv["pv_area_m2"] = roof_area * utilization / 100.0

    # PATCH 377: calculated PV fields are a mirror of the current Module 2
    # result, never an independent cache.  Clear the derived fields before
    # rebuilding them so repeated save/load cycles cannot preserve an older
    # common PV result when a current/legacy Module 2 object has no PV summary.
    pv_derived_keys = (
        "annual_generation_kWh",
        "annual_self_consumption_kWh",
        "annual_export_kWh",
        "annual_grid_import_kWh",
        "annual_cost_saving_JPY",
        "annual_export_revenue_JPY",
        "annual_co2_reduction_kg",
    )
    for key in pv_derived_keys:
        pv[key] = 0.0
    pv["calculation_status"] = "not_calculated"

    if not m2_current:
        pv["calculation_status"] = "stale_recalculation_required"
    else:
        pv_summary = m2.get("pv") if isinstance(m2.get("pv"), dict) else {}
        if pv_summary:
            # Rebuild calculated values from the current Module 2 object so
            # common remains a deterministic mirror across round trips.
            for key in (*pv_derived_keys, "calculation_status"):
                if key in pv_summary:
                    pv[key] = pv_summary[key]

    project["comparison_export"] = {
        "schema_version": "1.0",
        "generated_at": _now(),
        "common_building": {
            "use": c.get("building_use"),
            "storeys": c.get("storeys"),
            "floor_areas_m2": c.get("floor_areas_m2"),
            "gross_floor_area_m2": c.get("scale_gfa_m2"),
            "roof_area_m2": c.get("roof_area_m2"),
            "exterior_wall_area_m2": c.get("exterior_wall_area_m2"),
            "window_area_m2": c.get("window_area_m2"),
            "window_area_by_orientation_m2": {
                "north": c.get("north_window_area_m2"),
                "east": c.get("east_window_area_m2"),
                "south": c.get("south_window_area_m2"),
                "west": c.get("west_window_area_m2"),
            },
            "window_surfaces_by_azimuth": building.get("window_surfaces_by_azimuth", []),
            "country": c.get("country"),
            "latitude": c.get("latitude"),
            "longitude": c.get("longitude"),
            "weather_file": location.get("weather_file"),
            "north_rotation_deg": c.get("north_rotation_deg"),
        },
        # PATCH 374: comparison/export interfaces must advertise only current
        # module results.  A stale result may remain in module_outputs for audit
        # reference, but it is not a valid downstream/export reference.
        "module_result_refs": {
            f"module{i}": _module_output_is_current_for_export(project, f"module{i}")
            for i in sorted(int(k[6:]) for k in project.get("module_outputs", {}) if k.startswith("module") and k[6:].isdigit())
        },
    }



def _normalize_module_freshness_state(project: dict[str, Any]) -> None:
    """Normalize freshness for the current Project JSON contract only.

    PATCH 517: legacy Project JSON compatibility is retired.  Outputs that do
    not carry the current explicit freshness contract, or that are marked with
    the former legacy_current / legacy_readable states, are discarded during
    load/migration and treated as not calculated.  Current stale outputs are
    still retained so normal upstream-change invalidation continues to work.
    """
    outputs = project.setdefault("module_outputs", {})
    statuses = project.setdefault("module_status", {})
    stale_statuses = {"recalculation_pending", "error", "stale"}
    retired_legacy_statuses = {"legacy_current", "legacy_readable"}

    # PATCH_608: Planning owns freshness only for Modules 1, 2 and 5.
    # Evaluation-owned outputs (3, 4, 6, 7) may coexist in the same Project JSON
    # and must survive a Planning open/save cycle unchanged.
    for i in (1, 2, 5):
        key = f"module{i}"
        output = outputs.get(key)
        status_info = statuses.get(key)
        if not isinstance(status_info, dict):
            status_info = {
                "status": "not_calculated",
                "updated_at": None,
                "save_mode": None,
                "source_modules": [],
                "message": "",
            }
            statuses[key] = status_info

        status = str(status_info.get("status") or "")
        meta = output.get("_meta") if isinstance(output, dict) and isinstance(output.get("_meta"), dict) else None

        # Retire the former legacy compatibility path completely.  A current
        # output must prove freshness explicitly with _meta.is_current.
        is_retired_legacy = status in retired_legacy_statuses or status_info.get("save_mode") == "legacy_import"
        missing_current_contract = isinstance(output, dict) and bool(output) and not isinstance(meta, dict)
        missing_freshness_flag = isinstance(meta, dict) and "is_current" not in meta
        if is_retired_legacy or missing_current_contract or missing_freshness_flag:
            outputs[key] = None
            statuses[key] = {
                "status": "not_calculated",
                "updated_at": None,
                "save_mode": None,
                "source_modules": [],
                "message": "",
            }
            continue

        explicit_meta_stale = isinstance(meta, dict) and meta.get("is_current") is False
        explicit_status_stale = status in stale_statuses

        if explicit_status_stale and isinstance(output, dict) and output:
            meta = output.setdefault("_meta", {})
            meta["is_current"] = False
            meta.setdefault("stale_reason", "Project status marks this module output as stale or pending recalculation.")

        if explicit_meta_stale and not explicit_status_stale:
            status_info["status"] = "stale"
            if not status_info.get("message"):
                status_info["message"] = "Saved output is stale and requires recalculation."

        if not (isinstance(output, dict) and output):
            if status not in {"", "not_calculated"} and status not in stale_statuses:
                status_info["status"] = "not_calculated"
                status_info["save_mode"] = None
                status_info["source_modules"] = []
                status_info["message"] = "No saved module output is present."


def migrate_project(data: dict[str, Any]) -> dict[str, Any]:
    data = copy.deepcopy(data)
    data.setdefault("project_id", str(uuid.uuid4()))
    data.setdefault("created_at", _now())
    data.setdefault("updated_at", _now())
    data.setdefault("save_revision", 0)
    data.setdefault("last_saved_by", "")
    data.setdefault("common", {})
    _merge_defaults(data["common"], _common_defaults())
    data.setdefault("module_outputs", {})
    for i in (1, 2, 5):
        data["module_outputs"].setdefault(f"module{i}", None)
    data.setdefault("module_status", {})
    data.setdefault("audit_log", [])
    data.setdefault("validation", {"warnings": [], "errors": []})
    data.setdefault("linkage", {})
    data["schema_version"] = SCHEMA_VERSION
    data["platform_version"] = PLATFORM_VERSION
    from core.project_coordinator import ensure_project_structure
    ensure_project_structure(data)
    _normalize_module_freshness_state(data)
    _synchronize_common(data)
    return data


def validate_project(project: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if not isinstance(project, dict):
        return ["Project JSON root must be an object."]
    if not project.get("project_id"):
        errors.append("project_id is missing.")
    if not isinstance(project.get("common"), dict):
        errors.append("common must be an object.")
    if not isinstance(project.get("module_outputs"), dict):
        errors.append("module_outputs must be an object.")
    return errors


# PATCH_043: comparison copies.
#
# 03 Compare creates, inside its own comparison-group folder, a COPY of every
# Project it compares, with the group's common unit prices and business premises
# written into it.  A copy exists only to be re-priced (01 Planning Module 5)
# and re-evaluated (02 Evaluation Modules 6/7).  Everything upstream - drawings,
# quantities, energy, regional analysis, project information - must stay exactly
# as in the source Project, otherwise the copy stops being "the same building"
# and the comparison is no longer about the construction method alone.  Quantity
# corrections belong in the SOURCE Project, after which Compare rebuilds the copy.
COMPARISON_COPY_SCHEMA="AZRAS_COMPARISON_COPY_V1"
COMPARISON_COPY_DEFAULT_ALLOWED={"module5","module6","module7"}


def comparison_copy_info(project: dict[str, Any] | None) -> dict[str, Any] | None:
    """PATCH_043: the comparison-copy marker, or None for an ordinary Project."""
    if not isinstance(project, dict):
        return None
    info = project.get("comparison_copy")
    if isinstance(info, dict) and str(info.get("schema") or "") == COMPARISON_COPY_SCHEMA:
        return info
    return None


def comparison_copy_block_reason(project: dict[str, Any] | None, action: str, language: str = "ja") -> str | None:
    """PATCH_043: why an action is not allowed on a comparison copy (None = allowed).

    ``action`` is a module key ("module0", "module1", "module2", "module5",
    "module9", "module10", "detailed_configuration") or one of the Module 5
    price actions "module5_ai_cost_import" / "module5_manual_unit_cost_edit".
    """
    info = comparison_copy_info(project)
    if info is None:
        return None
    allowed = set(info.get("allowed_modules") or COMPARISON_COPY_DEFAULT_ALLOWED)
    source = str(info.get("source_project_path") or info.get("source_project_name") or "")
    ja = (language == "ja")
    if action in {"module5_ai_cost_import", "module5_manual_unit_cost_edit"}:
        return ("これは 03 Compare が作成した比較用コピーです。単価は比較前提表で統一されているため、"
                "このコピーでAI単価の取り込みや単価の手動変更はできません。"
                "単価を変える場合は 03 Compare で比較前提表を修正し、コピーを作り直してください。"
                if ja else
                "This is a comparison copy created by 03 Compare. Its unit prices are fixed by the comparison "
                "premise book, so AI price import and manual unit-cost edits are disabled here. To change a price, "
                "edit the premise book in 03 Compare and rebuild the copies.")
    if action in allowed:
        return None
    return (("これは 03 Compare が作成した比較用コピーです。このコピーで変更・保存できるのは "
             "Module 5（建設費）と 02 Evaluation の Module 6/7 だけです。"
             "図面・数量・エネルギー・地域解析・Project情報は元Projectで修正し、03 Compare でコピーを作り直してください。"
             + (f"\n元Project: {source}" if source else ""))
            if ja else
            ("This is a comparison copy created by 03 Compare. Only Module 5 (construction cost) and "
             "02 Evaluation Modules 6/7 may be changed and saved here. Correct drawings, quantities, energy, "
             "regional analysis or project information in the source Project, then rebuild the copies in 03 Compare."
             + (f"\nSource Project: {source}" if source else "")))


def save_project(
    project: dict[str, Any],
    path: str | Path,
    saved_by: str = "AZRAS Planning",
    create_backup: bool = True,
) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    migrated = migrate_project(project)
    project.clear()
    project.update(migrated)
    project["updated_at"] = _now()
    project["save_revision"] = int(project.get("save_revision") or 0) + 1
    project["last_saved_by"] = saved_by

    # PATCH_258: Project JSON is English-canonical regardless of UI/drawing language.
    # UI language remains a presentation preference; source drawing text may remain original.
    metadata = project.setdefault("metadata", {})
    metadata.update({
        "canonical_language": "en",
        "canonical_schema_version": "2.6",
        "project_data_standard": "English Canonical",
        "presentation_language_policy": "independent from canonical data",
        "drawing_language_policy": "preserve source drawing language",
    })
    project["audit_log"].append({
        "timestamp": project["updated_at"],
        "action": "atomic_project_save",
        "revision": project["save_revision"],
        "platform_version": PLATFORM_VERSION,
    })
    errors = validate_project(project)
    if errors:
        raise ValueError(" / ".join(errors))

    raw = json.dumps(project, ensure_ascii=False, indent=2)
    if create_backup and path.exists():
        backup = path.with_suffix(path.suffix + ".bak")
        shutil.copy2(path, backup)

    fd, temp_name = tempfile.mkstemp(
        prefix=path.stem + "_", suffix=".tmp", dir=str(path.parent)
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(raw)
            handle.flush()
            os.fsync(handle.fileno())

        # Dropbox, antivirus software and Windows Search may briefly lock either
        # the temporary file or the destination JSON. Retry the atomic replace
        # instead of immediately failing with WinError 5.
        last_error: OSError | None = None
        for attempt in range(12):
            try:
                os.replace(temp_name, path)
                last_error = None
                break
            except PermissionError as exc:
                last_error = exc
                time.sleep(0.25 + attempt * 0.10)
            except OSError as exc:
                last_error = exc
                if getattr(exc, "winerror", None) not in (5, 32):
                    raise
                time.sleep(0.25 + attempt * 0.10)

        if last_error is not None:
            # Final safe fallback. Keep the existing .bak and write through a
            # separately opened handle. This avoids os.replace when Dropbox has
            # locked the directory entry but still permits file content updates.
            try:
                with path.open("w", encoding="utf-8", newline="\n") as handle:
                    handle.write(raw)
                    handle.flush()
                    os.fsync(handle.fileno())
                last_error = None
            except OSError:
                recovery = path.with_name(
                    path.stem + "_SAVE_RECOVERY" + path.suffix
                )
                shutil.copyfile(temp_name, recovery)
                raise PermissionError(
                    f"Project JSON is locked by another program. "
                    f"A recovery copy was saved at: {recovery}"
                ) from last_error
    finally:
        if os.path.exists(temp_name):
            try:
                os.unlink(temp_name)
            except PermissionError:
                # A synchronisation process may release it shortly. It is only a
                # temporary file and can safely be removed later.
                pass


def load_project(path: str | Path) -> dict[str, Any]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return migrate_project(data)
