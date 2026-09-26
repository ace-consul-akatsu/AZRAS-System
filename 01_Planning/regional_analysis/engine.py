from __future__ import annotations
import math
from typing import Any

def _f(v: Any, d: float = 0.0) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return d

def method_key(project: dict[str, Any]) -> str:
    common = project.get("common") or {}
    detailed = common.get("detailed_configuration") or {}
    if detailed.get("building_system") == "azras":
        return "azras"
    general = detailed.get("general") or {}
    return str(general.get("structure") or "other")

def score_location(project: dict[str, Any], city: dict[str, Any], db: dict[str, Any], required_years: int = 100) -> dict[str, Any]:
    key = method_key(project)
    profile = (db.get("method_profiles") or {}).get(key) or (db.get("method_profiles") or {}).get("other", {})

    hazard_keys = ["seismic","wind","flood","snow","fire"]
    hazard_scores = []
    hazard_details = []
    for h in hazard_keys:
        demand = _f(city.get(h))
        capacity = _f(profile.get(h))
        if demand <= 0:
            score = 100.0
        else:
            score = max(0.0, min(100.0, 100.0 - max(0.0, demand-capacity)*25.0))
        hazard_scores.append(score)
        hazard_details.append({"hazard":h,"demand":demand,"capacity":capacity,"score":round(score,1)})

    resilience = sum(hazard_scores)/len(hazard_scores)

    climate = str(city.get("climate") or "")
    climates = profile.get("climates") or []
    climate_score = 100.0 if "all" in climates or climate in climates else 65.0

    durability = _f(profile.get("durability_years"))
    durability_score = min(100.0, durability/max(required_years,1)*100.0)

    material_key = str(profile.get("material_key") or "")
    materials = city.get("materials") or []
    workforce = city.get("workforce") or []
    availability = (50.0 if material_key in materials else 0.0) + (50.0 if material_key in workforce else 0.0)

    legal_data = _f(city.get("legal_data"))
    legal_score = legal_data/5.0*100.0

    outputs = project.get("module_outputs") or {}
    pro = outputs.get("pro_module2") or {}
    quality = pro.get("data_quality") or {}
    data_conf = _f(quality.get("overall_confidence"), 0.55)*100.0
    if not pro:
        data_conf = 45.0

    batch = project.get("batch_location_analysis") or {}
    if batch:
        loc_conf = _f((batch.get("location_analysis") or {}).get("confidence"),0.46)*100.0
        data_conf = (data_conf+loc_conf)/2.0

    common = project.get("common") or {}
    renewable = common.get("renewable_energy") or {}
    pv = _f(renewable.get("annual_generation_kWh"))
    gfa = _f(common.get("scale_gfa_m2"), _f((common.get("building") or {}).get("gross_floor_area_m2")))
    energy_score = min(100.0, 50.0 + (pv/max(gfa,1))*0.5)

    environment = 0.55*energy_score + 0.45*(100.0-_f(city.get("electricity_co2_kg_per_kwh"),0.45)*100.0)
    environment = max(0.0,min(100.0,environment))

    axes = {
        "environment": round(environment,1),
        "resilience": round(resilience,1),
        "climate_fit": round(climate_score,1),
        "durability": round(durability_score,1),
        "local_availability": round(availability,1),
        "legal_readiness": round(legal_score,1),
        "data_confidence": round(data_conf,1),
    }
    weights = {
        "environment":0.25,
        "resilience":0.20,
        "climate_fit":0.15,
        "durability":0.15,
        "local_availability":0.10,
        "legal_readiness":0.05,
        "data_confidence":0.10,
    }
    total = sum(axes[k]*weights[k] for k in weights)
    blockers = []
    if min(hazard_scores) < 50:
        blockers.append("hazard_performance_insufficient")
    if durability < required_years:
        blockers.append("required_durability_not_met")
    if availability < 50:
        blockers.append("local_material_or_workforce_unverified")
    if legal_score < 60:
        blockers.append("legal_verification_required")
    if data_conf < 60:
        blockers.append("data_confidence_below_threshold")

    recommendation = "recommended" if not blockers and total >= 75 else ("conditional" if total >= 55 else "not_recommended")
    return {
        "method_key":key,
        "city":city,
        "required_durability_years":required_years,
        "axes":axes,
        "weights":weights,
        "overall_score":round(total,1),
        "recommendation":recommendation,
        "blockers":blockers,
        "hazard_details":hazard_details,
        "method_profile":profile,
        "notice_ja":"本判定は企画比較用です。耐震・法規・材料供給・施工者の正式適合は現地専門家・行政・供給者による確認が必要です。",
    }
