#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""AZRAS common envelope insulation + thermal-mass planning model v1.

This module is intentionally a reduced-order planning model.  It provides a
single material/lambda/position vocabulary for roof, light wall, RC wall,
floor/slab and foundation.  Final thermal calculations continue to use the
8760-hour dynamic solver; this module only resolves scenario U-values and the
fraction of heavy mass that remains thermally coupled to the conditioned zone.
"""
from __future__ import annotations

from typing import Any

# Representative design defaults only.  Product declared values always take
# precedence when the user/AI supplies lambda_W_mK explicitly.
MATERIALS = {
    "Phenolic foam": 0.020,
    "PIR": 0.024,
    "PUR": 0.026,
    "XPS": 0.028,
    "EPS": 0.036,
    "Glass wool 16K": 0.038,
    "Glass wool 10K": 0.050,
    "Rock wool": 0.038,
    "Cellulose fiber": 0.040,
    "Wood fiber": 0.045,
    "Custom": None,
}

MATERIAL_LABELS_JA = {
    "Phenolic foam": "フェノールフォーム",
    "PIR": "PIR（ポリイソシアヌレート）",
    "PUR": "PUR（硬質ウレタン）",
    "XPS": "XPS（押出法ポリスチレン）",
    "EPS": "EPS（ビーズ法ポリスチレン）",
    "Glass wool 16K": "グラスウール16K",
    "Glass wool 10K": "グラスウール10K",
    "Rock wool": "ロックウール",
    "Cellulose fiber": "セルロースファイバー",
    "Wood fiber": "木質繊維断熱材",
    "Custom": "その他／実製品値",
}

# Reduced-order fraction of structural thermal mass that is directly useful to
# indoor temperature moderation.  These are not material standards; they are
# explicit AZRAS planning-model coupling assumptions and are returned in the
# calculation evidence so that they can be reviewed/replaced later.
POSITION_MASS_COUPLING = {
    "exterior": 1.00,
    "interior": 0.20,
    "cavity": 0.55,
    "none": 1.00,
    "other": 0.50,
}

POSITION_LABELS_JA = {
    "exterior": "外断熱",
    "interior": "内断熱",
    "cavity": "充填断熱",
    "none": "無断熱",
    "other": "その他",
}

COMPONENTS = ("roof", "light_wall", "rc_wall", "slab")
COMPONENT_LABELS_JA = {
    "roof": "屋根",
    "light_wall": "外壁（軽量壁）",
    "rc_wall": "RC壁",
    "slab": "床・土間・ベタ基礎",
}


def f(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def lambda_for(material: str, explicit: Any = None) -> float | None:
    val = f(explicit, -1.0)
    if val > 0:
        return val
    raw = MATERIALS.get(str(material or ""))
    return float(raw) if raw else None


def insulation_r(thickness_mm: Any, lambda_W_mK: Any) -> float:
    t = max(0.0, f(thickness_mm)) / 1000.0
    lam = f(lambda_W_mK, 0.0)
    return t / lam if t > 0 and lam > 0 else 0.0


def scenario_u_from_baseline(
    baseline_u: Any,
    baseline_thickness_mm: Any,
    baseline_lambda_W_mK: Any,
    scenario_thickness_mm: Any,
    scenario_lambda_W_mK: Any,
) -> float | None:
    """Replace only the insulation-layer resistance while preserving all other
    baseline assembly resistance.

    This avoids inventing unknown structure/finish layers.  If the baseline U
    is unresolved the function returns None instead of fabricating a U-value.
    """
    u0 = f(baseline_u, 0.0)
    if u0 <= 0:
        return None
    r_total0 = 1.0 / u0
    r_ins0 = insulation_r(baseline_thickness_mm, baseline_lambda_W_mK)
    r_other = max(0.01, r_total0 - r_ins0)
    r_ins1 = insulation_r(scenario_thickness_mm, scenario_lambda_W_mK)
    return 1.0 / max(0.01, r_other + r_ins1)


def mass_coupling(position: str) -> float:
    return float(POSITION_MASS_COUPLING.get(str(position or "other"), 0.50))


def normalize_position(value: Any) -> str:
    raw = str(value or "").strip().lower()
    aliases = {
        "外断熱": "exterior", "external insulation": "exterior", "external": "exterior",
        "内断熱": "interior", "internal insulation": "interior", "internal": "interior",
        "充填断熱": "cavity", "cavity insulation": "cavity", "cavity": "cavity",
        "無断熱": "none", "no insulation": "none", "none": "none",
    }
    return aliases.get(raw, raw if raw in POSITION_MASS_COUPLING else "other")
