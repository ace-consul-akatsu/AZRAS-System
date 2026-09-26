from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import Any

from services.dynamic_thermal_model_v9 import read_weather, simulate
from services.environment_engine_v9_1 import build_config


def _f(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def warming_delta_C(year: int, delta_100_C: float, delta_200_C: float) -> float:
    """Piecewise-linear planning sensitivity from present -> year 100 -> year 200."""
    y = max(0, int(year))
    if y <= 100:
        return delta_100_C * (y / 100.0)
    return delta_100_C + (delta_200_C - delta_100_C) * ((min(y, 200) - 100) / 100.0)


def _interpolate(points: dict[int, float], year: int) -> float:
    years = sorted(points)
    if not years:
        return 1.0
    if year <= years[0]:
        return points[years[0]]
    if year >= years[-1]:
        return points[years[-1]]
    for left, right in zip(years, years[1:]):
        if left <= year <= right:
            if right == left:
                return points[left]
            r = (year - left) / (right - left)
            return points[left] + (points[right] - points[left]) * r
    return points[years[-1]]


def calculate_future_climate_8760(
    project: dict[str, Any],
    module2: dict[str, Any],
    period_years: int,
    enabled: bool = False,
    delta_100_C: float = 0.0,
    delta_200_C: float = 0.0,
    milestone_interval_years: int = 20,
) -> dict[str, Any]:
    """Re-run the stored 8760-hour dynamic thermal model at future-climate milestones.

    Method:
      - Read the same EPW/CSV used by Module 2.
      - Apply a uniform dry-bulb temperature offset for each milestone.
      - Shift the model's annual mean ground temperature by the same offset.
      - Re-run all 8760 hours at each milestone.
      - Linearly interpolate annual energy factors between milestones.

    This is a transparent temperature-offset sensitivity analysis. It is not a
    replacement for a formally downscaled future weather file containing changes
    in humidity, solar radiation, wind, cloud, precipitation or extremes.
    """
    period_years = max(1, min(int(period_years), 200))
    if not enabled or (abs(delta_100_C) < 1e-12 and abs(delta_200_C) < 1e-12):
        return {
            "enabled": False,
            "method": "current_weather_repeated",
            "weather_file": str(module2.get("weather_file") or ""),
            "delta_100_C": float(delta_100_C),
            "delta_200_C": float(delta_200_C),
            "milestone_interval_years": int(milestone_interval_years),
            "milestones": [{"year": 0, "temperature_offset_C": 0.0, "energy_factor": 1.0}],
            "annual_energy_factors": [1.0] * (period_years + 1),
            "annual_temperature_offsets_C": [
                warming_delta_C(y, delta_100_C, delta_200_C) for y in range(period_years + 1)
            ],
            "status": "baseline",
        }

    weather_file = str(
        module2.get("weather_file")
        or (module2.get("_input_snapshot") or {}).get("weather_file")
        or ""
    )
    if not weather_file or not Path(weather_file).exists():
        raise ValueError(
            "将来気候8760時間計算には、Module 2で使用したEPW/CSV気象ファイルが必要です。"
        )

    settings = dict(
        (module2.get("_input_snapshot") or {}).get("settings")
        or module2.get("settings")
        or {}
    )
    outputs = project.get("module_outputs") or {}
    module1 = outputs.get("module1")
    if not module1:
        raise ValueError("将来気候8760時間計算にはModule 1出力が必要です。")

    cfg = build_config(module1, project.get("common") or {}, settings)
    weather = read_weather(weather_file)

    base_hvac = _f(module2.get("hvac_electricity_kWh_per_year"))
    base_other = _f(module2.get("other_equipment_electricity_kWh_per_year"))
    base_total = _f(module2.get("total_building_electricity_kWh_per_year"))
    if base_total <= 0:
        base_total = base_hvac + base_other
    if base_total <= 0:
        raise ValueError("Module 2の年間電力使用量が0以下のため将来気候感度を計算できません。")

    interval = max(5, min(int(milestone_interval_years or 20), 100))
    milestone_years = set(range(0, period_years + 1, interval))
    milestone_years.update({0, min(100, period_years), period_years})
    if period_years >= 200:
        milestone_years.add(200)

    factors: dict[int, float] = {0: 1.0}
    milestones = [{
        "year": 0,
        "temperature_offset_C": 0.0,
        "hvac_electricity_kWh": base_hvac,
        "other_electricity_kWh": base_other,
        "total_electricity_kWh": base_total,
        "energy_factor": 1.0,
    }]

    for year in sorted(y for y in milestone_years if y > 0):
        delta = warming_delta_C(year, delta_100_C, delta_200_C)
        morphed = weather.copy()
        morphed["dry_bulb_C"] = morphed["dry_bulb_C"] + delta
        if "ground_temp_C" in morphed.columns:
            morphed["ground_temp_C"] = morphed["ground_temp_C"] + delta
        cfg_future = replace(cfg, ground_annual_mean_C=cfg.ground_annual_mean_C + delta)
        _, thermal = simulate(morphed, cfg_future)
        hvac = _f(thermal.get("hvac_electricity_kWh_per_year"))
        total = hvac + base_other
        factor = total / base_total
        factors[year] = factor
        milestones.append({
            "year": year,
            "temperature_offset_C": delta,
            "hvac_electricity_kWh": hvac,
            "other_electricity_kWh": base_other,
            "total_electricity_kWh": total,
            "energy_factor": factor,
        })

    annual_factors = [_interpolate(factors, y) for y in range(period_years + 1)]
    annual_offsets = [warming_delta_C(y, delta_100_C, delta_200_C) for y in range(period_years + 1)]
    return {
        "enabled": True,
        "method": "morphed_epw_uniform_temperature_offset_8760_milestones_linear_interpolation",
        "weather_file": weather_file,
        "delta_100_C": float(delta_100_C),
        "delta_200_C": float(delta_200_C),
        "milestone_interval_years": interval,
        "milestones": milestones,
        "annual_energy_factors": annual_factors,
        "annual_temperature_offsets_C": annual_offsets,
        "limitations": [
            "dry_bulb_temperature_offset_only",
            "ground_mean_temperature_shifted_by_same_offset",
            "humidity_solar_wind_cloud_precipitation_extremes_unchanged",
            "planning_sensitivity_not_formal_future_weather_prediction",
        ],
        "status": "planning_sensitivity",
    }
