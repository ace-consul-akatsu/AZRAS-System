from __future__ import annotations

import copy
import json
import os
import re
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from batch_analysis.engine import build_case, _epw_climate
from core.project_coordinator import module_output_is_current
from regional_analysis.hourly_comparison_engine import calculate_hourly_snapshot


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _slug(text: str) -> str:
    value = re.sub(r"[^0-9A-Za-z_\-]+", "_", str(text).strip())
    return value.strip("_") or "Region"


def _project_label(project: dict[str, Any], fallback: str) -> str:
    common = project.get("common") or {}
    identity = common.get("project_identity") or {}
    return (
        common.get("project_name")
        or identity.get("project_name")
        or fallback
    )


def _structure_label(project: dict[str, Any]) -> str:
    common = project.get("common") or {}
    detailed = common.get("detailed_configuration") or {}
    if detailed.get("building_system") == "azras":
        azras = detailed.get("azras") or {}
        values = [
            azras.get("core_structure"),
            azras.get("infill_structure"),
            azras.get("infill_method"),
        ]
        suffix = "_".join(str(x) for x in values if x)
        return f"AZRAS_{suffix}" if suffix else "AZRAS"

    general = detailed.get("general") or {}
    values = [general.get("structure"), general.get("method")]
    label = "_".join(str(x) for x in values if x)
    return label or str(
        common.get("construction_method_name_en")
        or common.get("construction_method_name_ja")
        or "Structure"
    )


def _unique_target(folder: Path, preferred_name: str, overwrite: bool) -> Path:
    target = folder / preferred_name
    if overwrite or not target.exists():
        return target

    stem = target.stem
    suffix = target.suffix
    index = 2
    while True:
        candidate = folder / f"{stem}_{index}{suffix}"
        if not candidate.exists():
            return candidate
        index += 1


def _update_module0_location(project: dict[str, Any], city: dict[str, Any]) -> None:
    common = project.setdefault("common", {})
    identity = common.setdefault("project_identity", {})
    location = common.setdefault("location", {})

    country = str(city.get("country") or "")
    city_name = str(city.get("name") or city.get("ja") or "")
    address = str(city.get("address") or f"{city_name}, {country}".strip(", "))
    latitude = city.get("latitude", "")
    longitude = city.get("longitude", "")

    # Flat Module 0 fields.
    common.update({
        "country": country,
        "city": city_name,
        "address": address,
        # PATCH 632: project_location is the authoritative "都市・所在地" field
        # read by Module 0 and by Module 10's legend/label logic
        # (build_module10_snapshot checks project_location before city).
        # It was previously left unset here, so every regional JSON kept the
        # base project's original address and Module 10 showed the same
        # label for all cities even though the underlying calculations
        # correctly differed per region.
        "project_location": address,
        "latitude": latitude,
        "longitude": longitude,
        "google_coordinate_source": f"{latitude}, {longitude}",
    })

    # Structured Module 0 location fields.
    location.update({
        "status": "regional_project_generated",
        "source": "Module 9 Regional Project Generator",
        "country": country,
        "city": city_name,
        "address": address,
        "display_name": address,
        "latitude": latitude,
        "longitude": longitude,
        "google_coordinate_raw": f"{latitude}, {longitude}",
        "coordinate_source": "module9_city_database",
        "propagated_to_modules": list(range(11)),
        "applied_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    })

    identity["project_language"] = identity.get("project_language", "ja")

    # Preserve a Module 0 snapshot for later independent use.
    outputs = project.setdefault("module_outputs", {})
    previous = outputs.get("module0") if isinstance(outputs.get("module0"), dict) else {}
    outputs["module0"] = {
        **previous,
        "version": "3.4.2",
        "location": {
            "country": country,
            "city": city_name,
            "address": address,
            "latitude": latitude,
            "longitude": longitude,
            "coordinate_source": "module9_city_database",
        },
        "regional_project_generated": True,
        "updated_at": _now(),
    }



def _f(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _recursive_number(obj: Any, keys: tuple[str, ...]) -> float | None:
    if isinstance(obj, dict):
        for key in keys:
            if key in obj:
                try:
                    return float(obj[key])
                except (TypeError, ValueError):
                    pass
        for value in obj.values():
            found = _recursive_number(value, keys)
            if found is not None:
                return found
    elif isinstance(obj, list):
        for value in obj:
            found = _recursive_number(value, keys)
            if found is not None:
                return found
    return None


def _weights(values: list[float], fallback: list[float] | None = None) -> list[float]:
    clean = [max(0.0, _f(value)) for value in values]
    total = sum(clean)
    if total > 0.0:
        return [value / total for value in clean]
    if fallback is not None and len(fallback) == len(clean):
        fallback_total = sum(fallback)
        if fallback_total > 0.0:
            return [value / fallback_total for value in fallback]
    return [1.0 / len(clean)] * len(clean) if clean else []


def _module2_settings(project: dict[str, Any]) -> dict[str, Any]:
    """Return Module 2 settings from current and legacy Project JSON layouts.

    Current saves store the input settings under module2._input_snapshot.settings.
    Older builds may store them directly as module2.settings or floor_thermal.
    """
    outputs = project.get("module_outputs") or {}
    module2 = outputs.get("module2") or {}
    if not isinstance(module2, dict):
        return {}

    candidates = [
        ((module2.get("_input_snapshot") or {}).get("settings") or {}),
        (module2.get("settings") or {}),
    ]
    for candidate in candidates:
        if isinstance(candidate, dict) and candidate:
            settings = dict(candidate)
            if not settings.get("floor_thermal") and isinstance(module2.get("floor_thermal"), dict):
                settings["floor_thermal"] = dict(module2["floor_thermal"])
            return settings

    floor = module2.get("floor_thermal")
    if isinstance(floor, dict) and floor:
        return {"floor_thermal": dict(floor)}
    return {}


def build_module10_snapshot(project: dict[str, Any], city: dict[str, Any] | None = None) -> dict[str, Any]:
    """Build Module 10 data from one deterministic 8760-hour calculation.

    Fixed monthly allocation arrays are not used. Each monthly result is the
    sum of EPW hourly calculations using the drawing-derived orientations and
    window areas plus the thermal values currently stored by Module 2.
    """
    common = project.get("common") or {}
    outputs = project.get("module_outputs") or {}
    module2 = outputs.get("module2") or {}
    city = city or {}

    # PATCH 376: a retained stale Module 2 result must never seed a new
    # regional/Module 10 snapshot.  Regional calculations are downstream of
    # current thermal/PV assumptions even though the old result remains in
    # Project JSON for audit reference.
    if not module_output_is_current(project, "module2"):
        raise ValueError(
            "Module 2 result is stale. Recalculate and save Module 2 before generating regional comparison data."
        )

    settings = _module2_settings(project)

    weather_path = str(
        city.get("epw_path")
        or (project.get("regional_analysis") or {}).get("weather_file")
        or (project.get("regional_derivation") or {}).get("epw_path")
        or ((common.get("location") or {}).get("weather_file"))
        or common.get("weather_file")
        or module2.get("weather_file")
        or ""
    )
    if not weather_path:
        raise ValueError("地域比較に使用するEPWファイルが設定されていません。")

    regional = project.get("regional_analysis") or {}
    grid_factor = _f(
        city.get("electricity_co2_kg_per_kwh"),
        _f(regional.get("electricity_co2_kg_per_kwh"), _f(settings.get("electricity_co2"), 0.45)),
    )
    try:
        calculated = calculate_hourly_snapshot(project, weather_path, settings, grid_factor)
    except ValueError as exc:
        # AI-first projects may legitimately have total wall/window quantities while
        # directional N/E/S/W allocation is still unresolved. Do not fabricate a
        # directional split and do not block Module 9 project generation. Preserve a
        # machine-readable pending snapshot so Module 10 can explain what is missing.
        message = str(exc)
        if "方位別外壁・窓データ" in message:
            return {
                "schema_version": "2.0",
                "status": "pending_directional_surface_data",
                "analysis_status": "pending",
                "reason": message,
                "missing_requirements": [
                    "directional_exterior_wall_area_by_azimuth",
                    "directional_window_area_by_azimuth",
                ],
                "evidence_policy": "do_not_invent_directional_distribution",
                "annual": {},
                "monthly": [],
                "source": "Module 9 / Module 1 AI takeoff linkage",
            }
        raise

    # Keep the complete EPW monthly weather fields used by the Module 10 EPW table.
    try:
        climate = _epw_climate(weather_path)
        weather_monthly = climate.get("monthly_temperature_estimates") or []
        if isinstance(weather_monthly, list) and len(weather_monthly) == 12:
            for index, row in enumerate(calculated["monthly"]):
                full_weather = dict(weather_monthly[index]) if isinstance(weather_monthly[index], dict) else {}
                full_weather.update(row.get("weather") or {})
                row["weather"] = full_weather
    except (OSError, ValueError, TypeError):
        pass

    annual = dict(calculated["annual"])
    initial_co2 = _recursive_number(outputs, (
        "initial_embodied_co2_kg", "construction_co2_kg",
        "initial_construction_co2_kg", "embodied_co2_kg",
    )) or 0.0
    annual["initial_construction_co2_kg"] = round(initial_co2, 4)
    annual["electricity_co2_factor_kg_per_kWh"] = round(grid_factor, 6)

    city_name = str(common.get("project_location") or common.get("city") or city.get("name") or city.get("ja") or "")
    annual_co2 = _f(annual.get("operational_co2_kg"))
    return {
        "schema_version": "2.0",
        "generated_by": "Module 9 Regional Project Generator",
        "generated_at": _now(),
        "calculation_level": calculated["calculation_level"],
        "city": city_name,
        "weather_file": weather_path,
        "annual": annual,
        "monthly": calculated["monthly"],
        "co2_timeline": {
            str(year): round(initial_co2 + annual_co2 * year, 4)
            for year in (0, 50, 100, 150, 200)
        },
        "epw_metadata": calculated.get("epw_metadata") or {},
        "model_config": calculated.get("model_config") or {},
        "calculation_scope": calculated.get("calculation_scope") or {},
        # PATCH_529: machine-readable handoff contract for Compare. Module 10
        # now uses the exact same dynamic thermal solver as Module 2, eliminating
        # the independent regional solver that had drifted from the Module 2
        # passive-strategy equations.
        "thermal_input_contract": {
            "version": "PATCH_529",
            "source": "module_outputs.module2._input_snapshot.settings",
            "thermal_solver": "services.dynamic_thermal_model_v9.simulate",
            "same_solver_as_module2": True,
            "thermal_mass_enabled": bool(settings.get("thermal_mass_enabled", True)),
            "external_insulation_enabled": bool(settings.get("external_insulation_enabled", True)),
            "night_heat_release_enabled": bool(settings.get("night_heat_release_enabled", False)),
            "night_release_conductance_W_K": _f(settings.get("night_release_conductance_W_K"), 0.0),
            "natural_night_ventilation_enabled": bool(settings.get("natural_night_ventilation_enabled", False)),
            "night_ventilation_ach": _f(settings.get("night_ventilation_ach"), 3.0),
            "night_ventilation_delta_C": _f(settings.get("night_ventilation_delta_C"), 2.0),
            "solver_effective_heat_capacity_MJ_K": _f(
                (calculated.get("thermal_solver_contract") or {}).get(
                    "effective_dynamic_heat_capacity_MJ_per_K"
                ),
                0.0,
            ),
            "component_bridge_policy": ((calculated.get("thermal_mass_breakdown") or {}).get("thermal_mass_source_policy")
                                        if isinstance(calculated.get("thermal_mass_breakdown"), dict) else None),
        },
        "notice_ja": (
            "固定月別ウェイトは使用していません。登録EPWの8760時間値、図面から取得した方位別窓面積・方位、"
            "Module 2に保存されたU値・SHGC・熱容量・COP等をModule 2と同一の8760時間熱計算ソルバーへ入力し、月別値は時刻別結果の合計です。"
        ),
    }

def create_regional_project(
    base_project: dict[str, Any],
    base_project_path: str | Path,
    city: dict[str, Any],
    database: dict[str, Any],
    required_years: int = 100,
    overwrite: bool = True,
) -> tuple[dict[str, Any], Path]:
    base_path = Path(base_project_path)
    folder = base_path.parent

    # PATCH 376: fail before deriving any regional data when the base
    # environmental result has been explicitly invalidated.
    if not module_output_is_current(base_project, "module2"):
        raise ValueError(
            "Module 2 result is stale. Recalculate and save Module 2 before generating regional projects."
        )

    # Reuse the existing location-sensitive planning calculation.
    derived = build_case(base_project, city, str(base_path))
    derived = copy.deepcopy(derived)

    _update_module0_location(derived, city)

    city_name = str(city.get("name") or city.get("ja") or "Region")
    structure = _structure_label(base_project)
    base_label = _project_label(base_project, base_path.stem)
    project_name = f"{base_label} - {city_name}"

    common = derived.setdefault("common", {})
    identity = common.setdefault("project_identity", {})
    common["project_name"] = project_name
    identity["project_name"] = project_name

    regional = derived.setdefault("regional_analysis", {})
    regional["comparison_purpose"] = "same_method_regional_energy_and_lifecycle_co2"
    regional["base_location_role"] = "derived_independent_project"
    regional["location_database_version"] = database.get("version")
    regional["electricity_co2_kg_per_kwh"] = city.get("electricity_co2_kg_per_kwh", 0.45)
    regional["climate_code"] = city.get("climate", "")
    regional["climate_name_ja"] = city.get("climate_name_ja", "")
    regional["climate_name_en"] = city.get("climate_name_en", "")
    regional["weather_file"] = city.get("epw_path", "")
    regional["weather_station"] = city.get("epw_station", "")
    regional["weather_source_type"] = "EPW"
    regional["regional_coefficients"] = copy.deepcopy(city.get("regional_coefficients") or {})
    regional["regional_coefficient_evaluation_level"] = (city.get("regional_coefficients") or {}).get("evaluation_level", "D")
    regional.pop("current_region_result", None)

    original_project_id = base_project.get("project_id", "")

    preferred = f"{_slug(structure)}_{_slug(city_name)}.json"
    target = _unique_target(folder, preferred, overwrite)

    # When the same city is regenerated, keep the independent project's
    # identity and creation timestamp. This makes repeated registration a safe
    # update rather than a new unrelated project. Invalid old JSON is ignored.
    existing = None
    if target.exists() and overwrite:
        try:
            candidate = json.loads(target.read_text(encoding="utf-8"))
            if isinstance(candidate, dict):
                existing = candidate
        except (OSError, ValueError, TypeError):
            existing = None
    derived["project_id"] = str((existing or {}).get("project_id") or uuid.uuid4())
    derived["created_at"] = str((existing or {}).get("created_at") or _now())
    derived["updated_at"] = _now()
    derived["save_revision"] = int((existing or {}).get("save_revision") or 0) + 1
    derived["last_saved_by"] = "Module 9 Regional Project Generator"

    derived["regional_derivation"] = {
        "schema_version": "1.0",
        "is_derived_project": True,
        "independent_project": True,
        "base_project_id": original_project_id,
        "base_project_file": base_path.name,
        "base_project_path": str(base_path),
        "derived_project_file": target.name,
        "derived_country": city.get("country", ""),
        "derived_city": city_name,
        "derived_latitude": city.get("latitude", ""),
        "derived_longitude": city.get("longitude", ""),
        "structure_label": structure,
        "generated_by": "Module 9 Regional Project Generator",
        "generated_at": _now(),
        "location_fields_replaced": True,
        "module0_location_replaced": True,
        "regional_calculation_status": "epw_weather_based_comparison",
        "climate_code": city.get("climate", ""),
        "climate_name_ja": city.get("climate_name_ja", ""),
        "climate_name_en": city.get("climate_name_en", ""),
        "epw_path": city.get("epw_path", ""),
        "epw_station": city.get("epw_station", ""),
        "regional_coefficients": copy.deepcopy(city.get("regional_coefficients") or {}),
        "regional_coefficient_evaluation_level": (city.get("regional_coefficients") or {}).get("evaluation_level", "D"),
        "notice_ja": (
            "このJSONは各地域で建設する場合の独立Projectです。"
            "地域気候と月別気温は登録EPWを使用します。冷暖房計算は同一建物性能を地域気候へ適用した比較値です。"
            "建設費、修繕費、事業収支の正式値は現地単価・賃料・税・保険等で再計算してください。"
        ),
    }

    regional["module10_snapshot"] = build_module10_snapshot(derived, city)

    # Atomic replace: a failed calculation or write never destroys the last
    # valid regional JSON. The temporary file is created in the same folder so
    # os.replace remains atomic on Windows as well.
    folder.mkdir(parents=True, exist_ok=True)
    derived.setdefault("metadata", {}).update({
        "canonical_language": "en",
        "canonical_schema_version": "2.6",
        "project_data_standard": "English Canonical",
        "presentation_language_policy": "independent from canonical data",
        "drawing_language_policy": "preserve source drawing language",
    })
    payload = json.dumps(derived, ensure_ascii=False, indent=2)
    temp_path = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=folder,
            prefix=f".{target.stem}_", suffix=".tmp", delete=False,
        ) as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
            temp_path = Path(handle.name)
        # Validate the complete temporary JSON before replacing the old file.
        json.loads(temp_path.read_text(encoding="utf-8"))
        os.replace(temp_path, target)
        temp_path = None
    finally:
        if temp_path is not None:
            try:
                temp_path.unlink(missing_ok=True)
            except OSError:
                pass
    return derived, target


def generate_selected_projects(
    base_project: dict[str, Any],
    base_project_path: str | Path,
    rows: list[dict[str, Any]],
    database: dict[str, Any],
    required_years: int = 100,
    overwrite: bool = True,
) -> list[dict[str, Any]]:
    generated = []
    for row in rows:
        if not row.get("enabled", True):
            continue
        project, path = create_regional_project(
            base_project=base_project,
            base_project_path=base_project_path,
            city=row,
            database=database,
            required_years=required_years,
            overwrite=overwrite,
        )
        generated.append({
            "city": row.get("name") or row.get("ja"),
            "country": row.get("country", ""),
            "latitude": row.get("latitude", ""),
            "longitude": row.get("longitude", ""),
            "file": path.name,
            "path": str(path),
            "project_id": project.get("project_id", ""),
            "generated_at": _now(),
            "independent_project": True,
            "climate": row.get("climate", ""),
            "climate_name_ja": row.get("climate_name_ja", ""),
            "climate_name_en": row.get("climate_name_en", ""),
            "epw_path": row.get("epw_path", ""),
            "epw_station": row.get("epw_station", ""),
            "regional_coefficient_evaluation_level": (row.get("regional_coefficients") or {}).get("evaluation_level", "D"),
            "regional_coefficients": copy.deepcopy(row.get("regional_coefficients") or {}),
        })
    return generated
