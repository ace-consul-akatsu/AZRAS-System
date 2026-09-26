
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

    # PATCH_182: optional AI-resolved facade/window orientation surfaces.
    # Each surface may contain true_azimuth_deg, window_area_m2 and shading_factor.
    orientation_surfaces: tuple = ()

    # PATCH_189: opaque-roof solar gain in the reduced model.  The model
    # previously applied outdoor-air conduction to the roof but omitted solar
    # heating of the opaque roof surface entirely, which understated summer
    # cooling loads.  Use a planning sol-air approximation until detailed
    # EnergyPlus/BEST validation replaces this reduced-order treatment.
    roof_solar_absorptance: float = 0.55
    outside_surface_h_W_m2K: float = 20.0

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
    # PATCH: mirror regional_analysis/hourly_comparison_engine._read_epw()'s
    # existence check. Without this, a missing weather file reached
    # pandas/open() directly and surfaced as a raw, untranslated
    # FileNotFoundError/OSError instead of an actionable message.
    if not path.exists():
        raise ValueError(
            f"気象ファイルが見つかりません: {path}\n"
            "地域/気象データ設定画面で該当地点の気象データを再取得するか、"
            "気象ファイルを手動で指定し直してください。"
        )
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
        # PATCH_182: retain DNI/DHI and EPW location metadata so facade-specific
        # vertical irradiance can be calculated from true azimuth.
        lat = lon = tz = float("nan")
        try:
            first = path.open("r", encoding="utf-8", errors="ignore").readline().strip().split(",")
            if len(first) >= 9 and first[0].strip().upper() == "LOCATION":
                lat = float(first[6]); lon = float(first[7]); tz = float(first[8])
        except Exception:
            pass
        weather = pd.DataFrame({
            "datetime": dt,
            "dry_bulb_C": pd.to_numeric(raw["dry_bulb_C"], errors="coerce"),
            "ghi_Wm2": pd.to_numeric(raw["ghi_Wm2"], errors="coerce").clip(lower=0),
            "dni_Wm2": pd.to_numeric(raw["dni_Wm2"], errors="coerce").clip(lower=0),
            "dhi_Wm2": pd.to_numeric(raw["dhi_Wm2"], errors="coerce").clip(lower=0),
            "latitude_deg": lat,
            "longitude_deg": lon,
            "timezone_hours": tz,
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


def _solar_alt_azimuth(dt: pd.Timestamp, latitude_deg: float, longitude_deg: float, timezone_hours: float) -> tuple[float, float]:
    """Approximate solar altitude and azimuth (degrees, azimuth clockwise from north)."""
    lat = math.radians(latitude_deg)
    n = dt.dayofyear
    hour = dt.hour + dt.minute / 60.0 + 0.5
    gamma = 2.0 * math.pi / 365.0 * (n - 1 + (hour - 12.0) / 24.0)
    eqtime = 229.18 * (0.000075 + 0.001868*math.cos(gamma) - 0.032077*math.sin(gamma)
                       - 0.014615*math.cos(2*gamma) - 0.040849*math.sin(2*gamma))
    decl = (0.006918 - 0.399912*math.cos(gamma) + 0.070257*math.sin(gamma)
            - 0.006758*math.cos(2*gamma) + 0.000907*math.sin(2*gamma)
            - 0.002697*math.cos(3*gamma) + 0.00148*math.sin(3*gamma))
    time_offset = eqtime + 4.0*longitude_deg - 60.0*timezone_hours
    tst = hour*60.0 + time_offset
    ha = math.radians((tst/4.0) - 180.0)
    cosz = math.sin(lat)*math.sin(decl) + math.cos(lat)*math.cos(decl)*math.cos(ha)
    cosz = max(-1.0, min(1.0, cosz))
    zen = math.acos(cosz)
    alt = math.pi/2.0 - zen
    if alt <= 0:
        return math.degrees(alt), 0.0
    # atan2 form; convert south-based result to north-clockwise azimuth.
    az = math.atan2(math.sin(ha), math.cos(ha)*math.sin(lat) - math.tan(decl)*math.cos(lat))
    az_deg = (math.degrees(az) + 180.0) % 360.0
    return math.degrees(alt), az_deg


def _directional_window_solar_W(w, cfg: ModelConfig) -> float | None:
    """Return facade-specific incident solar through windows before SHGC, or None for fallback."""
    surfaces = list(cfg.orientation_surfaces or ())
    valid=[]
    for sf in surfaces:
        if not isinstance(sf, dict):
            continue
        try:
            area=float(sf.get("window_area_m2"))
            az=float(sf.get("true_azimuth_deg") if sf.get("true_azimuth_deg") is not None else sf.get("azimuth_deg"))
        except (TypeError, ValueError):
            continue
        if area > 0:
            try: shade=float(sf.get("shading_factor",1.0) or 1.0)
            except Exception: shade=1.0
            valid.append((area, az % 360.0, max(0.0, shade)))
    if not valid:
        return None
    try:
        lat=float(w.get("latitude_deg")); lon=float(w.get("longitude_deg")); tz=float(w.get("timezone_hours"))
        dni=max(0.0,float(w.get("dni_Wm2"))); dhi=max(0.0,float(w.get("dhi_Wm2"))); ghi=max(0.0,float(w.get("ghi_Wm2")))
        if not all(math.isfinite(x) for x in (lat,lon,tz,dni,dhi,ghi)):
            return None
    except Exception:
        return None
    alt_deg, sun_az = _solar_alt_azimuth(pd.Timestamp(w["datetime"]), lat, lon, tz)
    if alt_deg <= 0:
        return 0.0
    alt=math.radians(alt_deg)
    total=0.0
    for area, saz, shade in valid:
        cos_inc=max(0.0, math.cos(alt)*math.cos(math.radians(sun_az-saz)))
        beam=dni*cos_inc
        diffuse=dhi*0.5
        ground=ghi*0.2*0.5
        total += (beam + diffuse + ground) * area * shade
    return total


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

        # PATCH_176: hourly heat-balance diagnostics.  Positive values mean
        # heat entering the zone/node; negative values mean heat leaving it.
        diag_Wh = {
            "direct_envelope": 0.0,
            "rc_wall_to_zone": 0.0,
            "slab_to_zone": 0.0,
            "ground_to_slab": 0.0,
            "ventilation": 0.0,
            "internal_gain": 0.0,
            "window_solar_total": 0.0,
            "window_solar_to_air": 0.0,
            "opaque_roof_solar": 0.0,
        }

        for _sub in range(n_sub):
            Qint = internal_gain_W(ts, cfg)
            directional_incident = _directional_window_solar_W(w, cfg)
            if directional_incident is None:
                # Legacy fallback when AI/source drawings have not resolved facade windows.
                Qsolar = ghi * cfg.window_area_m2 * cfg.window_shgc * cfg.solar_shading_factor
            else:
                # surface shading is already included; retain global Module 2 shading as an
                # additional user-controlled factor for trees/blinds/etc.
                Qsolar = directional_incident * cfg.window_shgc * cfg.solar_shading_factor
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

            # Air node excluding HVAC.  Keep each contribution separate for
            # PATCH_176 diagnostic review; the sum is identical to the model
            # equation used before this patch.
            # PATCH_189: sol-air approximation for absorbed solar on the
            # opaque roof.  This term was absent before PATCH_189.  It is
            # intentionally separate from window solar and from outdoor-air
            # conduction so the diagnostic can audit it independently.
            h_out = max(1.0, float(cfg.outside_surface_h_W_m2K))
            roof_abs = max(0.0, min(1.0, float(cfg.roof_solar_absorptance)))
            q_opaque_roof_solar = G_roof * (roof_abs * ghi / h_out)
            q_direct_envelope = ((G_light + G_roof + G_win + G_door + cfg.thermal_bridge_W_K)
                                 * (Tout - T_air) + q_opaque_roof_solar)
            q_ventilation = (G_vent + extra_vent) * (Tout - T_air)
            q_rc_wall_to_zone = H_aw * (T_wall - T_air)
            q_slab_to_zone = H_as * (T_slab - T_air)
            q_ground_to_slab = G_slab_ground * (Tg - T_slab)
            q_air_other = (
                q_direct_envelope
                + q_ventilation
                + q_rc_wall_to_zone
                + q_slab_to_zone
                + Qint + Qsolar_air
            )

            wh_factor = dt_s / 3600.0
            diag_Wh["direct_envelope"] += q_direct_envelope * wh_factor
            diag_Wh["rc_wall_to_zone"] += q_rc_wall_to_zone * wh_factor
            diag_Wh["slab_to_zone"] += q_slab_to_zone * wh_factor
            diag_Wh["ground_to_slab"] += q_ground_to_slab * wh_factor
            diag_Wh["ventilation"] += q_ventilation * wh_factor
            diag_Wh["internal_gain"] += Qint * wh_factor
            diag_Wh["window_solar_total"] += Qsolar * wh_factor
            diag_Wh["window_solar_to_air"] += Qsolar_air * wh_factor
            diag_Wh["opaque_roof_solar"] += q_opaque_roof_solar * wh_factor

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
            # PATCH_176 hourly heat-balance terms (kWh during the hour).
            "direct_envelope_kWh": diag_Wh["direct_envelope"] / 1000.0,
            "rc_wall_to_zone_kWh": diag_Wh["rc_wall_to_zone"] / 1000.0,
            "slab_to_zone_kWh": diag_Wh["slab_to_zone"] / 1000.0,
            "ground_to_slab_kWh": diag_Wh["ground_to_slab"] / 1000.0,
            "ventilation_kWh": diag_Wh["ventilation"] / 1000.0,
            "internal_gain_kWh": diag_Wh["internal_gain"] / 1000.0,
            "window_solar_total_kWh": diag_Wh["window_solar_total"] / 1000.0,
            "window_solar_to_air_kWh": diag_Wh["window_solar_to_air"] / 1000.0,
            "opaque_roof_solar_kWh": diag_Wh["opaque_roof_solar"] / 1000.0,
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
