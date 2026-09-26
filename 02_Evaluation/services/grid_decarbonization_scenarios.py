from __future__ import annotations
from typing import Any

GRID_DECARBONIZATION_SCENARIOS: dict[str, dict[str, Any]] = {
    "low": {"annual_change_pct": -0.25, "label_ja": "低位（-0.25%/年）", "label_en": "Low (-0.25%/year)"},
    "standard": {"annual_change_pct": -0.50, "label_ja": "標準（-0.50%/年）", "label_en": "Standard (-0.50%/year)"},
    "high": {"annual_change_pct": -1.00, "label_ja": "高位（-1.00%/年）", "label_en": "High (-1.00%/year)"},
    "custom": {"annual_change_pct": None, "label_ja": "任意設定", "label_en": "Custom"},
}

def resolve_grid_decarbonization_scenario(scenario_key: str | None, custom_annual_change_pct: float) -> tuple[str, float]:
    key = str(scenario_key or "custom").strip().lower()
    if key not in GRID_DECARBONIZATION_SCENARIOS:
        key = "custom"
    configured = GRID_DECARBONIZATION_SCENARIOS[key]["annual_change_pct"]
    return key, float(custom_annual_change_pct if configured is None else configured)

def scenario_metadata(scenario_key: str, annual_change_pct: float) -> dict[str, Any]:
    row = GRID_DECARBONIZATION_SCENARIOS.get(scenario_key) or GRID_DECARBONIZATION_SCENARIOS["custom"]
    return {
        "scenario_key": scenario_key,
        "annual_change_pct": float(annual_change_pct),
        "label_ja": row["label_ja"],
        "label_en": row["label_en"],
        "interpretation": "planning_sensitivity_not_forecast",
    }
