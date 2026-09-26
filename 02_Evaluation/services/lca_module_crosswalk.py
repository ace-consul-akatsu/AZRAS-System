from __future__ import annotations

from typing import Any


def _f(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def build_lca_module_crosswalk(summary: dict[str, Any]) -> dict[str, Any]:
    """Crosswalk existing AZRAS Module 4 totals to common building-LCA module labels.

    Important:
    AZRAS currently calculates several impacts as aggregated lifecycle buckets.
    This function does NOT invent a more detailed A1/A2/A3/A4/A5 or C1/C2/C3/C4 split.
    It only maps already-calculated totals to the closest aggregate module group for
    explanation and export.
    """
    initial_co2 = _f(summary.get("initial_embodied_co2_kg"))
    operational_co2 = _f(summary.get("operational_co2_kg"))
    renewal_co2 = _f(summary.get("renewal_embodied_co2_kg"))
    demolition_co2 = _f(summary.get("demolition_co2_kg"))
    credit_co2 = _f(summary.get("reuse_recycling_credit_kg"))

    initial_energy = _f(summary.get("initial_embodied_energy_MJ"))
    operational_energy = _f(summary.get("operational_energy_MJ"))
    renewal_energy = _f(summary.get("renewal_embodied_energy_MJ"))
    demolition_energy = _f(summary.get("demolition_energy_MJ"))

    rows = [
        {
            "module_group": "A1-A5",
            "stage_ja": "製品・輸送・施工（初期建設の集約値）",
            "stage_en": "Product / transport / construction (aggregated initial construction)",
            "co2_kg": initial_co2,
            "energy_MJ": initial_energy,
            "source_key_co2": "summary.initial_embodied_co2_kg",
            "source_key_energy": "summary.initial_embodied_energy_MJ",
            "resolution": "aggregate_only",
            "note_ja": "A1-A3/A4/A5を個別分離していません。既存の初期Embodied値をA1-A5集約として表示します。",
        },
        {
            "module_group": "B4-B5 proxy",
            "stage_ja": "交換・更新・改修（更新イベントの集約値）",
            "stage_en": "Replacement / renewal / refurbishment (aggregated renewal-event proxy)",
            "co2_kg": renewal_co2,
            "energy_MJ": renewal_energy,
            "source_key_co2": "summary.renewal_embodied_co2_kg",
            "source_key_energy": "summary.renewal_embodied_energy_MJ",
            "resolution": "planning_proxy",
            "note_ja": "Module 3更新イベントをB4/B5相当の企画比較用集約値として対応付けます。正式なB4/B5個別算定ではありません。",
        },
        {
            "module_group": "B6",
            "stage_ja": "運用エネルギー",
            "stage_en": "Operational energy use",
            "co2_kg": operational_co2,
            "energy_MJ": operational_energy,
            "source_key_co2": "summary.operational_co2_kg",
            "source_key_energy": "summary.operational_energy_MJ",
            "resolution": "direct_crosswalk",
            "note_ja": "Module 2の年間エネルギーを200年系列へ展開した運用段階です。",
        },
        {
            "module_group": "C1-C4",
            "stage_ja": "解体・廃棄（集約値）",
            "stage_en": "End of life / demolition / waste processing (aggregated)",
            "co2_kg": demolition_co2,
            "energy_MJ": demolition_energy,
            "source_key_co2": "summary.demolition_co2_kg",
            "source_key_energy": "summary.demolition_energy_MJ",
            "resolution": "aggregate_only",
            "note_ja": "C1/C2/C3/C4を個別分離していません。既存の解体・廃棄影響をC1-C4集約として表示します。",
        },
        {
            "module_group": "D",
            "stage_ja": "システム境界外の再使用・リサイクル便益",
            "stage_en": "Benefits beyond the system boundary: reuse / recycling",
            "co2_kg": -credit_co2,
            "energy_MJ": None,
            "source_key_co2": "summary.reuse_recycling_credit_kg (displayed as negative benefit)",
            "source_key_energy": None,
            "resolution": "co2_credit_only",
            "note_ja": "現在のAZRASではD相当の控除はCO₂クレジットとして計上し、エネルギークレジットは独立算定していません。",
        },
    ]

    mapped_co2 = sum(_f(r.get("co2_kg")) for r in rows)
    mapped_energy = sum(_f(r.get("energy_MJ")) for r in rows if r.get("energy_MJ") is not None)
    target_co2 = _f(summary.get("net_lifecycle_co2_kg"))
    target_energy = _f(summary.get("total_lifecycle_energy_MJ"))

    return {
        "mapping_version": "1.0",
        "mapping_status": "planning_crosswalk_not_module_resolved_lca",
        "rows": rows,
        "reconciliation": {
            "mapped_net_co2_kg": mapped_co2,
            "module4_net_lifecycle_co2_kg": target_co2,
            "co2_difference_kg": mapped_co2 - target_co2,
            "mapped_total_energy_MJ": mapped_energy,
            "module4_total_lifecycle_energy_MJ": target_energy,
            "energy_difference_MJ": mapped_energy - target_energy,
        },
        "limitations_ja": [
            "既存AZRAS計算値の説明用クロスウォークであり、A1/A2/A3/A4/A5等を新規に個別算定する機能ではありません。",
            "A1-A5とC1-C4は現行計算の集約値です。",
            "更新影響はB4/B5相当の企画比較用proxyであり、正式なB4/B5個別分類ではありません。",
            "Dは現行の再使用・リサイクルCO2クレジットのみを表示し、エネルギー便益は独立計上していません。",
            "正式提出には適用規格、EPD、PCR、システム境界、データ品質等を別途確認してください。",
        ],
    }
