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
        "module_outputs": {f"module{i}": None for i in range(1, 8)},
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
    if scale:
        c["storeys"] = int(scale.get("storeys") or c.get("storeys") or 0)
        c["floor_areas_m2"] = scale.get("floor_areas_m2") or c.get("floor_areas_m2") or []
        c["scale_gfa_m2"] = float(scale.get("gross_floor_area_m2") or c.get("scale_gfa_m2") or 0)
        c["roof_area_m2"] = float(scale.get("roof_area_m2") or c.get("roof_area_m2") or 0)
        building.update({
            "storeys": c["storeys"],
            "floor_areas_m2": c["floor_areas_m2"],
            "gross_floor_area_m2": c["scale_gfa_m2"],
            "roof_area_m2": c["roof_area_m2"],
        })

    m2 = project.get("module_outputs", {}).get("module2") or {}
    snapshot = m2.get("_input_snapshot") or {}
    settings = snapshot.get("settings") or m2.get("settings") or {}
    thermal = c["thermal"]
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

    project["comparison_export"] = {
        "schema_version": "1.0",
        "generated_at": _now(),
        "common_building": {
            "use": c.get("building_use"),
            "storeys": c.get("storeys"),
            "floor_areas_m2": c.get("floor_areas_m2"),
            "gross_floor_area_m2": c.get("scale_gfa_m2"),
            "roof_area_m2": c.get("roof_area_m2"),
            "country": c.get("country"),
            "latitude": c.get("latitude"),
            "longitude": c.get("longitude"),
            "weather_file": location.get("weather_file"),
            "north_rotation_deg": c.get("north_rotation_deg"),
        },
        "module_result_refs": {
            f"module{i}": bool(project.get("module_outputs", {}).get(f"module{i}"))
            for i in range(1, 8)
        },
    }


def migrate_project(data: dict[str, Any]) -> dict[str, Any]:
    data = copy.deepcopy(data)
    data.setdefault("project_id", str(uuid.uuid4()))
    data.setdefault("created_at", _now())
    data.setdefault("updated_at", _now())
    data.setdefault("save_revision", 0)
    data.setdefault("last_saved_by", "")
    data.setdefault("common", {})
    # PATCH_208: retired 04 Feasibility adjustments are not part of AZRAS v2.0.0.
    # Remove the stale active field so no later code path can accidentally reuse it.
    data["common"].pop("accepted_feasibility_adjustment", None)
    _merge_defaults(data["common"], _common_defaults())
    data.setdefault("module_outputs", {})
    for i in range(1, 8):
        data["module_outputs"].setdefault(f"module{i}", None)
    data.setdefault("module_status", {})
    data.setdefault("audit_log", [])
    data.setdefault("validation", {"warnings": [], "errors": []})
    data.setdefault("linkage", {})
    data["schema_version"] = SCHEMA_VERSION
    data["platform_version"] = PLATFORM_VERSION
    _synchronize_common(data)
    from core.project_coordinator import ensure_project_structure
    return ensure_project_structure(data)


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


# PATCH_008: comparison copies created by 03 Compare (same marker as
# 01 Planning PATCH_043).  In 02 Evaluation only Modules 6 and 7 may be
# recalculated and saved on a copy; Modules 3 and 4 depend only on inputs that
# must stay identical to the source Project.
COMPARISON_COPY_SCHEMA="AZRAS_COMPARISON_COPY_V1"


def comparison_copy_block_reason(project, action: str, language: str = "ja"):
    """PATCH_008: why ``action`` (a module key) is not allowed on a copy, or None."""
    info = project.get("comparison_copy") if isinstance(project, dict) else None
    if not (isinstance(info, dict) and str(info.get("schema") or "") == COMPARISON_COPY_SCHEMA):
        return None
    allowed = set(info.get("allowed_modules") or {"module5", "module6", "module7"})
    if action in allowed:
        return None
    source = str(info.get("source_project_path") or info.get("source_project_name") or "")
    if language == "ja":
        return ("これは 03 Compare が作成した比較用コピーです。02 Evaluation で変更・保存できるのは "
                "Module 6（事業性）と Module 7（更新・解体費）だけです。Module 3/4 は元Projectと同じ結果を"
                "保つ必要があるため、このコピーでは保存できません。"
                + (f"\n元Project: {source}" if source else ""))
    return ("This is a comparison copy created by 03 Compare. In 02 Evaluation only Module 6 (business) and "
            "Module 7 (renewal and demolition cost) may be changed and saved. Modules 3/4 must keep the source "
            "Project's results, so they cannot be saved on this copy."
            + (f"\nSource Project: {source}" if source else ""))


def save_project(
    project: dict[str, Any],
    path: str | Path,
    saved_by: str = "AZRAS Platform",
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
