
from __future__ import annotations

from typing import Any
import math
import pandas as pd


def _f(value: Any, default: float = 0.0) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    return number if math.isfinite(number) else default


def calculate_pv_energy(
    hourly: pd.DataFrame,
    annual_building_electricity_kwh: float,
    annual_other_equipment_kwh: float,
    heating_cop: float,
    cooling_cop: float,
    roof_area_m2: float,
    settings: dict[str, Any],
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Planning-level hourly PV and electricity-balance calculation.

    Uses horizontal global solar radiation (GHI) from the weather file.
    Roof tilt, azimuth, detailed shading, module temperature, snow, dirt and
    long-term degradation are not included in V9.4.1.
    """
    enabled = bool(settings.get("pv_enabled", True))
    roof_utilization = max(
        0.0, min(100.0, _f(settings.get("roof_utilization_percent"), 80.0))
    )
    panel_eff = max(
        0.0, min(100.0, _f(settings.get("panel_efficiency_percent"), 22.0))
    ) / 100.0
    pcs_eff = max(
        0.0, min(100.0, _f(settings.get("pcs_efficiency_percent"), 97.0))
    ) / 100.0
    self_use_cap = max(
        0.0, min(100.0, _f(settings.get("self_consumption_percent"), 80.0))
    ) / 100.0
    currency=str(settings.get("currency") or "UNSET").upper()
    purchase_price = max(
        0.0, _f(
            settings.get("purchase_price_local_currency_per_kWh"),
            _f(settings.get("purchase_price_JPY_per_kWh"),30.0) if currency=="JPY" else 0.0
        )
    )
    export_price = max(
        0.0, _f(
            settings.get("export_price_local_currency_per_kWh"),
            _f(settings.get("export_price_JPY_per_kWh"),16.0) if currency=="JPY" else 0.0
        )
    )
    co2_factor = max(
        0.0, _f(settings.get("electricity_co2_kg_per_kWh"), 0.43)
    )

    roof_area = max(0.0, _f(roof_area_m2))
    pv_area = roof_area * roof_utilization / 100.0 if enabled else 0.0

    out = hourly.copy()
    ghi = (
        pd.to_numeric(out.get("ghi_Wm2", 0.0), errors="coerce")
        .replace([float("inf"), float("-inf")], 0.0)
        .fillna(0.0)
        .clip(lower=0.0)
    )

    out["pv_generation_kWh"] = (
        ghi / 1000.0 * pv_area * panel_eff * pcs_eff
        if enabled else 0.0
    )

    heating = (
        pd.to_numeric(out.get("heating_load_kWh", 0.0), errors="coerce")
        .replace([float("inf"), float("-inf")], 0.0)
        .fillna(0.0)
        .clip(lower=0.0)
    )
    cooling = (
        pd.to_numeric(out.get("cooling_load_kWh", 0.0), errors="coerce")
        .replace([float("inf"), float("-inf")], 0.0)
        .fillna(0.0)
        .clip(lower=0.0)
    )

    hvac_electricity = (
        heating / max(_f(heating_cop, 3.5), 0.1)
        + cooling / max(_f(cooling_cop, 3.2), 0.1)
    )
    equipment_hourly = max(0.0, _f(annual_other_equipment_kwh)) / max(len(out), 1)
    out["building_electricity_kWh"] = hvac_electricity + equipment_hourly

    technical_self_use = pd.concat(
        [out["pv_generation_kWh"], out["building_electricity_kWh"]], axis=1
    ).min(axis=1)

    annual_generation = float(out["pv_generation_kWh"].sum())
    technical_total = float(technical_self_use.sum())
    target_total = annual_generation * self_use_cap
    adopted_total = min(technical_total, target_total)
    scale = adopted_total / technical_total if technical_total > 0 else 0.0

    out["pv_self_consumption_kWh"] = technical_self_use * scale
    out["pv_export_kWh"] = (
        out["pv_generation_kWh"] - out["pv_self_consumption_kWh"]
    ).clip(lower=0.0)
    out["grid_import_kWh"] = (
        out["building_electricity_kWh"] - out["pv_self_consumption_kWh"]
    ).clip(lower=0.0)

    self_use = float(out["pv_self_consumption_kWh"].sum())
    export = float(out["pv_export_kWh"].sum())
    grid_import = float(out["grid_import_kWh"].sum())
    building_electricity = max(0.0, _f(annual_building_electricity_kwh))

    self_sufficiency = (
        self_use / building_electricity * 100.0
        if building_electricity > 0 else 0.0
    )
    realized_self_consumption = (
        self_use / annual_generation * 100.0
        if annual_generation > 0 else 0.0
    )

    cost_saving = self_use * purchase_price
    export_revenue = export * export_price
    co2_reduction = self_use * co2_factor

    summary = {
        "version": "9.4.1",
        "model": "Hourly GHI horizontal-plane PV planning model",
        "pv_enabled": enabled,
        "roof_area_m2": roof_area,
        "roof_utilization_percent": roof_utilization,
        "pv_area_m2": pv_area,
        "panel_efficiency_percent": panel_eff * 100.0,
        "pcs_efficiency_percent": pcs_eff * 100.0,
        "self_consumption_target_percent": self_use_cap * 100.0,
        "realized_self_consumption_percent": realized_self_consumption,
        "annual_generation_kWh": annual_generation,
        "annual_self_consumption_kWh": self_use,
        "annual_export_kWh": export,
        "annual_grid_import_kWh": grid_import,
        "electricity_self_sufficiency_percent": self_sufficiency,
        "currency": currency,
        "tariff_status": str(settings.get("tariff_status") or ("user_input_local_currency" if currency!="UNSET" else "currency_unresolved")),
        "purchase_price_local_currency_per_kWh": purchase_price,
        "export_price_local_currency_per_kWh": export_price,
        "annual_cost_saving_local_currency": cost_saving,
        "annual_export_revenue_local_currency": export_revenue,
        "annual_total_economic_benefit_local_currency": cost_saving + export_revenue,
        "purchase_price_JPY_per_kWh": purchase_price if currency=="JPY" else None,
        "export_price_JPY_per_kWh": export_price if currency=="JPY" else None,
        "annual_cost_saving_JPY": cost_saving if currency=="JPY" else None,
        "annual_export_revenue_JPY": export_revenue if currency=="JPY" else None,
        "annual_total_economic_benefit_JPY": (cost_saving + export_revenue) if currency=="JPY" else None,
        "annual_co2_reduction_kg": co2_reduction,
        "net_operational_CO2_kg_per_year": max(
            0.0, building_electricity * co2_factor - co2_reduction
        ),
        "calculation_status": "provisional_planning_comparison",
        "requires_confirmation": True,
        "disclaimer": (
            "Horizontal GHI is used without roof tilt, azimuth, detailed "
            "shading, module temperature, snow, dirt or degradation correction."
        ),
    }
    return out, summary
