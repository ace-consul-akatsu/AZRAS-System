from __future__ import annotations

import math
from dataclasses import asdict
from pathlib import Path
from typing import Any

import pandas as pd

from services.environment_engine_v9_1 import build_config
from services.dynamic_thermal_model_v9 import simulate

RHO_AIR = 1.2
CP_AIR = 1006.0
ALBEDO = 0.20


def _f(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _read_epw(path: str | Path) -> tuple[pd.DataFrame, dict[str, float]]:
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"EPWが見つかりません: {path}")
    if path.suffix.lower() != ".epw":
        raise ValueError("地域比較の時刻別計算はEPWファイルを必要とします。")

    header = path.read_text(encoding="utf-8", errors="ignore").splitlines()[0].split(",")
    if len(header) < 9 or header[0].strip().upper() != "LOCATION":
        raise ValueError("EPW LOCATIONヘッダーを読み取れません。")
    meta = {
        "latitude": _f(header[6]),
        "longitude": _f(header[7]),
        "timezone": _f(header[8]),
        "elevation": _f(header[9]) if len(header) > 9 else 0.0,
    }

    raw = pd.read_csv(path, skiprows=8, header=None)
    if raw.shape[1] < 22:
        raise ValueError("EPW形式として必要列が不足しています。")
    hour = pd.to_numeric(raw.iloc[:, 3], errors="coerce").clip(1, 24) - 1
    dt = pd.to_datetime(
        {
            "year": pd.to_numeric(raw.iloc[:, 0], errors="coerce"),
            "month": pd.to_numeric(raw.iloc[:, 1], errors="coerce"),
            "day": pd.to_numeric(raw.iloc[:, 2], errors="coerce"),
            "hour": hour,
        },
        errors="coerce",
    )
    weather = pd.DataFrame(
        {
            "datetime": dt,
            "dry_bulb_C": pd.to_numeric(raw.iloc[:, 6], errors="coerce"),
            "ghi_Wm2": pd.to_numeric(raw.iloc[:, 13], errors="coerce").clip(lower=0),
            "dni_Wm2": pd.to_numeric(raw.iloc[:, 14], errors="coerce").clip(lower=0),
            "dhi_Wm2": pd.to_numeric(raw.iloc[:, 15], errors="coerce").clip(lower=0),
        }
    ).dropna()
    weather = weather.sort_values("datetime").reset_index(drop=True)
    if len(weather) < 8760:
        raise ValueError(f"EPWの有効行数が不足しています: {len(weather)}")
    return weather.iloc[:8760].copy(), meta


def _solar_position(ts: pd.Timestamp, latitude: float, longitude: float, timezone: float) -> tuple[float, float]:
    """Return solar altitude and azimuth in radians.

    Azimuth is clockwise from north. EPW hour represents the end of the hour;
    the calculation uses the midpoint of that hourly interval.
    """
    n = ts.dayofyear
    local_hour = ts.hour + 0.5
    b = math.radians(360.0 * (n - 81) / 364.0)
    eot_min = 9.87 * math.sin(2 * b) - 7.53 * math.cos(b) - 1.5 * math.sin(b)
    standard_meridian = 15.0 * timezone
    solar_time = local_hour + (4.0 * (longitude - standard_meridian) + eot_min) / 60.0
    hour_angle = math.radians(15.0 * (solar_time - 12.0))
    decl = math.radians(23.45 * math.sin(math.radians(360.0 * (284 + n) / 365.0)))
    lat = math.radians(latitude)

    sin_alt = math.sin(lat) * math.sin(decl) + math.cos(lat) * math.cos(decl) * math.cos(hour_angle)
    alt = math.asin(max(-1.0, min(1.0, sin_alt)))
    if alt <= 0:
        return alt, 0.0

    cos_alt = max(math.cos(alt), 1e-9)
    sin_az = -math.cos(decl) * math.sin(hour_angle) / cos_alt
    cos_az = (math.sin(decl) - math.sin(alt) * math.sin(lat)) / (cos_alt * max(math.cos(lat), 1e-9))
    az = math.atan2(sin_az, cos_az)
    if az < 0:
        az += 2 * math.pi
    return alt, az


def _vertical_irradiance(
    ts: pd.Timestamp,
    surface_azimuth_deg: float,
    ghi: float,
    dni: float,
    dhi: float,
    latitude: float,
    longitude: float,
    timezone: float,
) -> float:
    alt, solar_az = _solar_position(ts, latitude, longitude, timezone)
    if alt <= 0:
        return 0.0
    surf_az = math.radians(surface_azimuth_deg % 360.0)
    # Vertical plane: cos(theta) = cos(altitude) * cos(solar azimuth - surface azimuth)
    cos_incidence = max(0.0, math.cos(alt) * math.cos(solar_az - surf_az))
    beam = max(0.0, dni) * cos_incidence
    sky = max(0.0, dhi) * 0.5
    ground = max(0.0, ghi) * ALBEDO * 0.5
    return beam + sky + ground


def _surface_data(project: dict[str, Any]) -> list[dict[str, float]]:
    """Return the canonical directional window surfaces for hourly solar gains.

    PATCH_353 stabilization: older Module 10 code only accepted
    ``module1.profile.surfaces``.  Module 1 now also persists its reconciled
    N/E/S/W takeoff into ``common.building.window_area_by_orientation_m2`` and
    the drawing geometry.  Treat those current canonical fields as an equivalent
    interface instead of falsely reporting the project as unresolved.  No equal
    distribution or invented orientation is permitted.
    """
    module1 = (project.get("module_outputs") or {}).get("module1") or {}
    profile = module1.get("profile") or ((module1.get("drawing_analysis") or {}).get("profile") or {})
    surfaces = profile.get("surfaces") or []
    result = []
    for surface in surfaces:
        if not isinstance(surface, dict):
            continue
        true_az = surface.get("true_azimuth_deg")
        if true_az in (None, ""):
            true_az = surface.get("azimuth_deg")
        if true_az in (None, ""):
            continue
        result.append(
            {
                "azimuth_deg": _f(true_az),
                "window_area_m2": max(0.0, _f(surface.get("window_area_m2"))),
                "shading_factor": max(0.0, _f(surface.get("shading_factor"), 1.0)),
            }
        )
    if result:
        return result

    # Current Module 1 save contract: reconciled directional opening quantities
    # are synchronized to common.building.  Use them only when the drawing
    # geometry supplies a real north rotation or directional wall evidence.
    common = project.get("common") or {}
    building = common.get("building") or {}
    geom = profile.get("geometry") or {}
    win = building.get("window_area_by_orientation_m2") or {}
    if not isinstance(win, dict) or not win:
        win = {
            "north": common.get("north_window_area_m2"),
            "east": common.get("east_window_area_m2"),
            "south": common.get("south_window_area_m2"),
            "west": common.get("west_window_area_m2"),
        }
    opaque = geom.get("opaque_wall_area_by_orientation_m2") or {}
    north_raw = geom.get("north_rotation_deg")
    if north_raw in (None, ""):
        north_raw = common.get("north_rotation_deg")
    has_directional_evidence = (
        isinstance(opaque, dict) and any(_f(v) > 0 for v in opaque.values())
    ) or any(v not in (None, "") for v in win.values())
    if north_raw not in (None, "") and has_directional_evidence:
        rotation = _f(north_raw) % 360.0
        local_azimuth = {"north": 0.0, "east": 90.0, "south": 180.0, "west": 270.0}
        return [
            {
                "azimuth_deg": (az + rotation) % 360.0,
                "window_area_m2": max(0.0, _f(win.get(name))),
                "shading_factor": 1.0,
            }
            for name, az in local_azimuth.items()
        ]

    raise ValueError(
        "Module 1の方位別開口データまたは真北回転角が未確定です。"
    )


def calculate_hourly_snapshot(
    project: dict[str, Any],
    weather_path: str | Path,
    settings: dict[str, Any],
    grid_factor: float,
    include_hourly: bool = False,
) -> dict[str, Any]:
    """Calculate Module 10 from the same 8760-hour solver used by Module 2.

    PATCH_529: Module 10 previously maintained a second hand-copied thermal
    solver.  That copy had drifted from ``dynamic_thermal_model_v9.simulate``:
    it omitted passive-strategy branches (night heat release / natural night
    ventilation), thermal-mass enable/disable handling, the external-insulation
    U-value multiplier, opaque-roof solar gain and the global solar-shading
    factor.  The drift could turn RC/AZRAS heating almost to zero while moving
    energy into cooling, so regional CO2 ranking no longer matched Module 2.

    Module 10 now delegates the thermal balance to exactly the same solver as
    Module 2 and only performs regional aggregation (monthly totals, PV, grid
    import/export and CO2).  This prevents future equation drift.
    """
    module1 = (project.get("module_outputs") or {}).get("module1") or {}
    cfg = build_config(module1, project.get("common") or {}, settings)

    # Preserve the existing strict directional-evidence check used by Module 9
    # project generation.  The shared solver itself has a legacy total-window
    # fallback, but regional comparison must not silently invent orientation.
    _surface_data(project)

    weather, epw_meta = _read_epw(weather_path)
    # dynamic_thermal_model_v9.simulate uses these EPW location columns for
    # facade-specific solar position.  Module 2's read_weather() supplies the
    # same metadata, so add them here before invoking the common solver.
    weather = weather.copy()
    weather["latitude_deg"] = epw_meta["latitude"]
    weather["longitude_deg"] = epw_meta["longitude"]
    weather["timezone_hours"] = epw_meta["timezone"]

    thermal_hourly, thermal_summary = simulate(weather, cfg)

    pv_cfg = dict((project.get("common") or {}).get("renewable_energy") or {})
    pv_cfg.update(settings.get("pv") or {})
    pv_enabled = bool(pv_cfg.get("pv_enabled", True))
    pv_area = max(0.0, _f(pv_cfg.get("pv_area_m2")))
    if pv_area <= 0.0:
        utilization = max(0.0, min(100.0, _f(pv_cfg.get("roof_utilization_percent"), 80.0)))
        pv_area = cfg.roof_area_m2 * utilization / 100.0
    panel_eff = max(0.0, _f(pv_cfg.get("panel_efficiency_percent"), 22.0)) / 100.0
    pcs_eff = max(0.0, _f(pv_cfg.get("pcs_efficiency_percent"), 97.0)) / 100.0

    equipment_annual = max(
        0.0,
        _f(
            (module1.get("building_performance") or {}).get("equipment", {}).get("annual_electricity_kwh"),
            _f(((project.get("module_outputs") or {}).get("module2") or {}).get("other_equipment_electricity_kWh_per_year")),
        ),
    )
    equipment_hourly = equipment_annual / 8760.0

    # Align weather irradiance with the thermal result by timestamp.  Both are
    # sorted 8760-row annual series, but timestamp merge makes the contract
    # explicit and robust to future preprocessing changes.
    h = thermal_hourly.copy()
    h["datetime"] = pd.to_datetime(h["datetime"], errors="coerce")
    w = weather[["datetime", "dry_bulb_C", "ghi_Wm2", "dni_Wm2", "dhi_Wm2"]].copy()
    w["datetime"] = pd.to_datetime(w["datetime"], errors="coerce")
    h = h.merge(w, on="datetime", how="left", suffixes=("", "_weather"))
    if len(h) != 8760:
        raise ValueError(f"共有8760熱計算の有効行数が不正です: {len(h)}")

    h["heating_electricity_kWh"] = pd.to_numeric(h["heating_load_kWh"], errors="coerce").fillna(0.0) / max(cfg.heating_cop, 0.1)
    h["cooling_electricity_kWh"] = pd.to_numeric(h["cooling_load_kWh"], errors="coerce").fillna(0.0) / max(cfg.cooling_cop, 0.1)
    h["other_electricity_kWh"] = equipment_hourly
    ghi = pd.to_numeric(h["ghi_Wm2"], errors="coerce").fillna(0.0).clip(lower=0.0)
    h["pv_generation_kWh"] = (ghi * pv_area * panel_eff * pcs_eff / 1000.0) if pv_enabled else 0.0
    h["total_use_kWh"] = h["heating_electricity_kWh"] + h["cooling_electricity_kWh"] + h["other_electricity_kWh"]
    h["grid_import_kWh"] = (h["total_use_kWh"] - h["pv_generation_kWh"]).clip(lower=0.0)
    h["grid_export_kWh"] = (h["pv_generation_kWh"] - h["total_use_kWh"]).clip(lower=0.0)
    h["net_energy_kWh"] = h["total_use_kWh"] - h["pv_generation_kWh"]
    h["month"] = h["datetime"].dt.month.astype(int)
    h["outdoor_C"] = pd.to_numeric(h["dry_bulb_C"], errors="coerce")

    monthly_rows = []
    for month in range(1, 13):
        part = h[h["month"] == month]
        monthly_rows.append(
            {
                "month": month,
                "heating_electricity_kWh": round(float(part["heating_electricity_kWh"].sum()), 4),
                "cooling_electricity_kWh": round(float(part["cooling_electricity_kWh"].sum()), 4),
                "other_electricity_kWh": round(float(part["other_electricity_kWh"].sum()), 4),
                "total_use_kWh": round(float(part["total_use_kWh"].sum()), 4),
                "pv_generation_kWh": round(float(part["pv_generation_kWh"].sum()), 4),
                "grid_import_kWh": round(float(part["grid_import_kWh"].sum()), 4),
                "grid_export_kWh": round(float(part["grid_export_kWh"].sum()), 4),
                "net_energy_kWh": round(float(part["net_energy_kWh"].sum()), 4),
                "weather": {
                    "mean_C": round(float(part["outdoor_C"].mean()), 4),
                    "mean_high_C": round(float(part.groupby(part["datetime"].dt.date)["outdoor_C"].max().mean()), 4),
                    "mean_low_C": round(float(part.groupby(part["datetime"].dt.date)["outdoor_C"].min().mean()), 4),
                },
            }
        )

    annual = {
        "heating_electricity_kWh": float(h["heating_electricity_kWh"].sum()),
        "cooling_electricity_kWh": float(h["cooling_electricity_kWh"].sum()),
        "other_electricity_kWh": float(h["other_electricity_kWh"].sum()),
        "total_use_kWh": float(h["total_use_kWh"].sum()),
        "pv_generation_kWh": float(h["pv_generation_kWh"].sum()),
        "grid_import_kWh": float(h["grid_import_kWh"].sum()),
        "grid_export_kWh": float(h["grid_export_kWh"].sum()),
        "net_energy_kWh": float(h["net_energy_kWh"].sum()),
    }
    annual["operational_co2_kg"] = annual["grid_import_kWh"] * grid_factor

    result = {
        "calculation_level": "epw_8760_hour_shared_module2_solver",
        "weather_file": str(weather_path),
        "epw_metadata": epw_meta,
        "model_config": asdict(cfg),
        "annual": {key: round(value, 4) for key, value in annual.items()},
        "monthly": monthly_rows,
        "thermal_solver_contract": {
            "version": "PATCH_529",
            "solver": "services.dynamic_thermal_model_v9.simulate",
            "same_solver_as_module2": True,
            "module2_heating_load_kWh_per_year": round(_f(thermal_summary.get("heating_load_kWh_per_year")), 6),
            "module2_cooling_load_kWh_per_year": round(_f(thermal_summary.get("cooling_load_kWh_per_year")), 6),
            "module2_heating_electricity_kWh_per_year": round(_f(thermal_summary.get("heating_electricity_kWh_per_year")), 6),
            "module2_cooling_electricity_kWh_per_year": round(_f(thermal_summary.get("cooling_electricity_kWh_per_year")), 6),
            "effective_dynamic_heat_capacity_MJ_per_K": round(_f(thermal_summary.get("effective_dynamic_heat_capacity_MJ_per_K")), 6),
            "passive_strategy_status": dict(thermal_summary.get("passive_strategy_status") or {}),
        },
        "calculation_scope": {
            "used_inputs": [
                "EPW hourly dry-bulb temperature",
                "EPW hourly GHI/DNI/DHI",
                "drawing-derived facade azimuths",
                "drawing-derived window areas by facade",
                "wall/roof/slab/window/door U-values",
                "window SHGC and global shading factor",
                "effective wall/slab heat capacity",
                "thermal-mass and external-insulation switches",
                "night heat release and natural night ventilation settings",
                "opaque roof solar gain",
                "ventilation and heat-recovery settings stored in Module 2",
                "heating/cooling setpoints and COP",
                "PV area and conversion efficiencies",
            ],
            "not_used_or_not_available": [
                "occupant-specific hourly schedule beyond the stored internal-gain schedule",
                "movable blind operation",
                "PV module-temperature, dirt, snow and degradation correction",
            ],
            "other_electricity_rule": "Annual other-equipment electricity is divided equally among the 8760 hours because no hourly equipment schedule is stored.",
        },
    }
    if include_hourly:
        result["hourly"] = h
    return result

