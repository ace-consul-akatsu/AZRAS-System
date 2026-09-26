
#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AZRAS専用・動的熱負荷モデル（3ノードRCネットワーク）

目的:
- 8760時間の気象データ（EPWまたはCSV）を読み込み
- 外断熱されたRC壁と厚いベタ基礎の蓄熱効果を考慮
- 年間暖房負荷・冷房負荷・一次エネルギー・運用時CO2を算出

注意:
- EnergyPlus/BESTの代替ではなく、比較検討用の縮約モデルです。
- 研究発表・確認申請等に使う場合は、詳細シミュレーションとの照合が必要です。
"""

from __future__ import annotations

import argparse
import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Tuple

import numpy as np
import pandas as pd


RHO_AIR = 1.20       # kg/m3
CP_AIR = 1006.0      # J/(kg K)


@dataclass
class ModelConfig:
    # Geometry
    conditioned_floor_area_m2: float
    footprint_area_m2: float
    conditioned_volume_m3: float
    rc_exterior_area_m2: float
    light_exterior_area_m2: float
    roof_area_m2: float
    slab_area_m2: float
    window_area_m2: float
    door_area_m2: float

    # U-values / thermal bridges
    u_rc_wall_W_m2K: float
    u_light_wall_W_m2K: float
    u_roof_W_m2K: float
    u_window_W_m2K: float
    u_door_W_m2K: float
    u_slab_to_ground_W_m2K: float
    thermal_bridge_W_K: float

    # Thermal mass
    concrete_density_kg_m3: float
    concrete_cp_J_kgK: float
    total_concrete_volume_m3: float
    rc_wall_mass_volume_m3: float
    slab_mass_volume_m3: float
    active_fraction_wall: float
    active_fraction_slab: float
    air_capacitance_multiplier: float

    # Coupling coefficients
    h_inside_wall_W_m2K: float
    h_inside_slab_W_m2K: float

    # Ventilation / gains
    ach_1_h: float
    heat_recovery_efficiency: float
    window_shgc: float
    solar_shading_factor: float
    solar_to_air_fraction: float
    solar_to_wall_fraction: float
    solar_to_slab_fraction: float
    internal_gain_W_m2_day: float
    internal_gain_W_m2_night: float

    # HVAC
    heating_setpoint_C: float
    cooling_setpoint_C: float
    heating_cop: float
    cooling_cop: float
    primary_energy_factor_MJ_per_kWh: float
    electricity_co2_kg_per_kWh: float

    # Ground temperature approximation
    ground_annual_mean_C: float
    ground_amplitude_C: float
    ground_phase_day: float

    # Passive thermal strategies
    thermal_mass_enabled: bool = True
    external_insulation_enabled: bool = True
    external_insulation_reference_u_multiplier: float = 3.0
    night_heat_release_enabled: bool = False
    night_release_start_hour: int = 22
    night_release_end_hour: int = 6
    night_release_conductance_W_K: float = 0.0
    natural_night_ventilation_enabled: bool = False
    night_ventilation_ach: float = 3.0
    night_ventilation_delta_C: float = 2.0

    # Numerics
    timestep_minutes: int = 5

    @staticmethod
    def from_json(path: str | Path) -> "ModelConfig":
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        return ModelConfig(**data)


def read_weather(path: str | Path) -> pd.DataFrame:
    """
    EPW or CSV reader.

    CSV required columns:
      datetime, dry_bulb_C, ghi_Wm2
    Optional:
      ground_temp_C
    """
    path = Path(path)
    if path.suffix.lower() == ".epw":
        cols = [
            "year", "month", "day", "hour", "minute", "data_source",
            "dry_bulb_C", "dew_point_C", "rh_pct", "pressure_Pa",
            "etr_horiz", "etr_direct", "hir_sky", "ghi_Wm2",
            "dni_Wm2", "dhi_Wm2"
        ]
        raw = pd.read_csv(path, skiprows=8, header=None)
        if raw.shape[1] < 16:
            raise ValueError("EPW形式として列数が不足しています。")
        raw = raw.iloc[:, :16]
        raw.columns = cols
        # EPW hour is 1-24; timestamp represents end of hour.
        hour = raw["hour"].clip(1, 24) - 1
        dt = pd.to_datetime(
            dict(year=raw["year"], month=raw["month"], day=raw["day"], hour=hour),
            errors="coerce"
        )
        weather = pd.DataFrame({
            "datetime": dt,
            "dry_bulb_C": pd.to_numeric(raw["dry_bulb_C"], errors="coerce"),
            "ghi_Wm2": pd.to_numeric(raw["ghi_Wm2"], errors="coerce").clip(lower=0),
        })
    else:
        weather = pd.read_csv(path)
        required = {"datetime", "dry_bulb_C", "ghi_Wm2"}
        missing = required - set(weather.columns)
        if missing:
            raise ValueError(f"CSVに不足列があります: {sorted(missing)}")
        weather["datetime"] = pd.to_datetime(weather["datetime"], errors="coerce")

    weather = weather.dropna(subset=["datetime", "dry_bulb_C", "ghi_Wm2"]).copy()
    weather = weather.sort_values("datetime").reset_index(drop=True)

    if len(weather) < 8760:
        raise ValueError(f"年間計算には原則8760行以上必要です。現在 {len(weather)} 行です。")
    return weather.iloc[:8760].copy()


def ground_temperature(dt: pd.Timestamp, cfg: ModelConfig) -> float:
    day = dt.dayofyear
    # Surface-seasonal wave, simplified and attenuated.
    return cfg.ground_annual_mean_C + cfg.ground_amplitude_C * math.sin(
        2.0 * math.pi * (day - cfg.ground_phase_day) / 365.0
    )


def internal_gain_W(dt: pd.Timestamp, cfg: ModelConfig) -> float:
    hour = dt.hour
    # Residential schedule: higher mornings/evenings, lower daytime/night.
    if 6 <= hour < 9 or 17 <= hour < 23:
        w_m2 = cfg.internal_gain_W_m2_day
    else:
        w_m2 = cfg.internal_gain_W_m2_night
    return w_m2 * cfg.conditioned_floor_area_m2


def simulate(weather: pd.DataFrame, cfg: ModelConfig) -> Tuple[pd.DataFrame, dict]:
    dt_s = cfg.timestep_minutes * 60
    n_sub = int(3600 / dt_s)
    if 3600 % dt_s != 0:
        raise ValueError("timestep_minutes は60を割り切る値にしてください。")

    # Thermal capacitances
    C_air = (
        RHO_AIR * CP_AIR * cfg.conditioned_volume_m3
        * cfg.air_capacitance_multiplier
    )
    mass_factor = 1.0 if cfg.thermal_mass_enabled else 0.01
    C_wall = mass_factor * (
        cfg.rc_wall_mass_volume_m3 * cfg.active_fraction_wall
        * cfg.concrete_density_kg_m3 * cfg.concrete_cp_J_kgK
    )
    C_slab = mass_factor * (
        cfg.slab_mass_volume_m3 * cfg.active_fraction_slab
        * cfg.concrete_density_kg_m3 * cfg.concrete_cp_J_kgK
    )

    # Conductances
    u_mult = 1.0 if cfg.external_insulation_enabled else max(1.0, cfg.external_insulation_reference_u_multiplier)
    G_rc_out = cfg.u_rc_wall_W_m2K * u_mult * cfg.rc_exterior_area_m2
    G_light = cfg.u_light_wall_W_m2K * u_mult * cfg.light_exterior_area_m2
    G_roof = cfg.u_roof_W_m2K * u_mult * cfg.roof_area_m2
    G_win = cfg.u_window_W_m2K * cfg.window_area_m2
    G_door = cfg.u_door_W_m2K * cfg.door_area_m2
    G_slab_ground = cfg.u_slab_to_ground_W_m2K * cfg.slab_area_m2
    G_vent = (
        RHO_AIR * CP_AIR * cfg.conditioned_volume_m3 * cfg.ach_1_h / 3600.0
        * (1.0 - cfg.heat_recovery_efficiency)
    )
    H_aw = cfg.h_inside_wall_W_m2K * cfg.rc_exterior_area_m2
    H_as = cfg.h_inside_slab_W_m2K * cfg.slab_area_m2

    # Initial temperatures
    T_air = 22.0
    T_wall = 22.0
    T_slab = 22.0

    rows = []

    for _, w in weather.iterrows():
        ts = pd.Timestamp(w["datetime"])
        Tout = float(w["dry_bulb_C"])
        ghi = max(0.0, float(w["ghi_Wm2"]))
        Tg = (
            float(w["ground_temp_C"])
            if "ground_temp_C" in weather.columns and pd.notna(w.get("ground_temp_C"))
            else ground_temperature(ts, cfg)
        )

        heat_Wh = 0.0
        cool_Wh = 0.0

        for _sub in range(n_sub):
            Qint = internal_gain_W(ts, cfg)
            Qsolar = (
                ghi * cfg.window_area_m2 * cfg.window_shgc
                * cfg.solar_shading_factor
            )
            Qsolar_air = Qsolar * cfg.solar_to_air_fraction
            Qsolar_wall = Qsolar * cfg.solar_to_wall_fraction
            Qsolar_slab = Qsolar * cfg.solar_to_slab_fraction

            hour = ts.hour
            in_night_window = (hour >= cfg.night_release_start_hour or hour < cfg.night_release_end_hour)
            night_release = (cfg.night_heat_release_enabled and in_night_window)
            q_wall_release = 0.0
            q_slab_release = 0.0
            if night_release and Tout < T_wall:
                q_wall_release = cfg.night_release_conductance_W_K * (Tout - T_wall) * 0.6
            if night_release and Tout < T_slab:
                q_slab_release = cfg.night_release_conductance_W_K * (Tout - T_slab) * 0.4

            extra_vent = 0.0
            if (cfg.natural_night_ventilation_enabled and in_night_window
                    and Tout <= T_air - cfg.night_ventilation_delta_C
                    and Tout > cfg.heating_setpoint_C - 2.0):
                extra_vent = (RHO_AIR * CP_AIR * cfg.conditioned_volume_m3
                              * cfg.night_ventilation_ach / 3600.0)

            # Wall and slab node fluxes
            q_wall = G_rc_out * (Tout - T_wall) + H_aw * (T_air - T_wall) + Qsolar_wall + q_wall_release
            q_slab = G_slab_ground * (Tg - T_slab) + H_as * (T_air - T_slab) + Qsolar_slab + q_slab_release

            # Air node excluding HVAC
            q_air_other = (
                (G_light + G_roof + G_win + G_door + cfg.thermal_bridge_W_K + G_vent + extra_vent)
                * (Tout - T_air)
                + H_aw * (T_wall - T_air)
                + H_as * (T_slab - T_air)
                + Qint + Qsolar_air
            )

            # Ideal-load control for current substep
            q_hvac = 0.0
            T_free = T_air + q_air_other * dt_s / C_air

            if T_free < cfg.heating_setpoint_C:
                q_hvac = C_air * (cfg.heating_setpoint_C - T_air) / dt_s - q_air_other
                q_hvac = max(0.0, q_hvac)
                heat_Wh += q_hvac * dt_s / 3600.0
            elif T_free > cfg.cooling_setpoint_C:
                q_hvac = C_air * (cfg.cooling_setpoint_C - T_air) / dt_s - q_air_other
                q_hvac = min(0.0, q_hvac)
                cool_Wh += (-q_hvac) * dt_s / 3600.0

            # Explicit integration with small substeps
            T_wall += q_wall * dt_s / C_wall
            T_slab += q_slab * dt_s / C_slab
            T_air += (q_air_other + q_hvac) * dt_s / C_air

        rows.append({
            "datetime": ts,
            "outdoor_C": Tout,
            "ground_C": Tg,
            "zone_air_C": T_air,
            "rc_wall_C": T_wall,
            "slab_C": T_slab,
            "heating_load_kWh": heat_Wh / 1000.0,
            "cooling_load_kWh": cool_Wh / 1000.0,
            "ghi_Wm2": ghi,
        })

    out = pd.DataFrame(rows)

    heating_kWh = out["heating_load_kWh"].sum()
    cooling_kWh = out["cooling_load_kWh"].sum()
    heating_elec_kWh = heating_kWh / cfg.heating_cop
    cooling_elec_kWh = cooling_kWh / cfg.cooling_cop
    hvac_elec_kWh = heating_elec_kWh + cooling_elec_kWh

    # Peak metadata. Hourly load [kWh] is numerically equal to the average kW
    # during that one-hour interval. Peak duration is the annual cumulative
    # number of hours at or above 90% of the annual maximum.
    peak_heat = float(out["heating_load_kWh"].max()) if len(out) else 0.0
    peak_cool = float(out["cooling_load_kWh"].max()) if len(out) else 0.0
    peak_heat_dt = None
    peak_cool_dt = None
    if peak_heat > 0:
        peak_heat_dt = pd.Timestamp(out.loc[out["heating_load_kWh"].idxmax(), "datetime"])
    if peak_cool > 0:
        peak_cool_dt = pd.Timestamp(out.loc[out["cooling_load_kWh"].idxmax(), "datetime"])
    peak_heat_hours = float((out["heating_load_kWh"] >= peak_heat * 0.90).sum()) if peak_heat > 0 else 0.0
    peak_cool_hours = float((out["cooling_load_kWh"] >= peak_cool * 0.90).sum()) if peak_cool > 0 else 0.0

    summary = {
        "model": "Generic 3-node dynamic thermal model with passive strategies",
        "hours": int(len(out)),
        "conditioned_floor_area_m2": cfg.conditioned_floor_area_m2,
        "heating_load_kWh_per_year": heating_kWh,
        "cooling_load_kWh_per_year": cooling_kWh,
        "heating_electricity_kWh_per_year": heating_elec_kWh,
        "cooling_electricity_kWh_per_year": cooling_elec_kWh,
        "hvac_electricity_kWh_per_year": hvac_elec_kWh,
        "primary_energy_MJ_per_year": hvac_elec_kWh * cfg.primary_energy_factor_MJ_per_kWh,
        "operational_CO2_kg_per_year": hvac_elec_kWh * cfg.electricity_co2_kg_per_kWh,
        "peak_heating_kW": peak_heat,
        "peak_cooling_kW": peak_cool,
        "peak_heating_datetime": peak_heat_dt.isoformat() if peak_heat_dt is not None else None,
        "peak_cooling_datetime": peak_cool_dt.isoformat() if peak_cool_dt is not None else None,
        "peak_heating_duration_hours_90pct": peak_heat_hours,
        "peak_cooling_duration_hours_90pct": peak_cool_hours,
        "total_concrete_heat_capacity_MJ_per_K": (
            cfg.total_concrete_volume_m3
            * cfg.concrete_density_kg_m3
            * cfg.concrete_cp_J_kgK / 1e6
        ),
        "effective_dynamic_heat_capacity_MJ_per_K": (C_wall + C_slab) / 1e6,
        "passive_strategy_status": {
            "thermal_mass": bool(cfg.thermal_mass_enabled),
            "external_insulation": bool(cfg.external_insulation_enabled),
            "night_heat_release": bool(cfg.night_heat_release_enabled),
            "natural_night_ventilation": bool(cfg.natural_night_ventilation_enabled),
        },
        "notes": [
            "一次エネルギー・CO2は空調分のみ。",
            "給湯・照明・家電・調理は含まない。",
            "RC壁面積、屋根U値、窓SHGC等はconfigで変更可能。",
        ],
    }
    return out, summary


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--weather", required=True, help="Nagoya EPW or hourly CSV")
    parser.add_argument("--config", default="azras_config.json")
    parser.add_argument("--output-dir", default="results")
    args = parser.parse_args()

    cfg = ModelConfig.from_json(args.config)
    weather = read_weather(args.weather)
    hourly, summary = simulate(weather, cfg)

    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    hourly.to_csv(out_dir / "azras_hourly_results.csv", index=False, encoding="utf-8-sig")
    (out_dir / "azras_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
