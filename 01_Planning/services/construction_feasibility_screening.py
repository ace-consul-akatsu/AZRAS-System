from __future__ import annotations

from math import asin, cos, radians, sin, sqrt
from pathlib import Path
from typing import Any
import json
import os
import urllib.parse
import urllib.request
from services.regulatory_hazard_rule_engine import apply_regulatory_hazard_rules

STATUS_ORDER = ["Candidate", "Conditional", "Excluded", "Unknown"]

def _f(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default

def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371.0088
    p1, p2 = radians(lat1), radians(lat2)
    dp = radians(lat2 - lat1)
    dl = radians(lon2 - lon1)
    a = sin(dp / 2) ** 2 + cos(p1) * cos(p2) * sin(dl / 2) ** 2
    return 2 * r * asin(sqrt(a))

def _proxy_quality(distance_km: float) -> str:
    if distance_km <= 75:
        return "high"
    if distance_km <= 200:
        return "medium"
    if distance_km <= 500:
        return "low"
    return "none"

def _labels(method_profiles):
    return {
        str(row.get("id")): {"ja": str(row.get("ja") or row.get("id") or ""), "en": str(row.get("en") or row.get("id") or "")}
        for row in method_profiles
        if isinstance(row, dict) and row.get("id")
    }

def load_screening_master(root_dir: str | Path):
    root = Path(root_dir)
    suitability = json.loads((root / "data" / "regional_suitability_database_v1.json").read_text(encoding="utf-8"))
    methods = json.loads((root / "data" / "construction_method_profiles.json").read_text(encoding="utf-8"))
    return suitability, methods


def _osm_method_key(value: str) -> str | None:
    v = str(value or "").strip().lower().replace("-", "_").replace(" ", "_")
    if not v:
        return None
    if any(x in v for x in ("reinforced_concrete", "concrete", "rcc", "rc_frame")):
        return "rc"
    if any(x in v for x in ("steel", "metal_frame", "metal")):
        return "steel"
    if any(x in v for x in ("timber", "wood", "wood_frame", "wooden")):
        return "wood_frame"
    if any(x in v for x in ("masonry", "masonary", "brick", "stone", "block", "cmu")):
        return "masonry"
    if any(x in v for x in ("adobe", "earth", "rammed_earth", "cob")):
        return "earth"
    return None


def parse_osm_local_evidence(payload: dict[str, Any], latitude: float, longitude: float) -> dict[str, Any]:
    structure_counts: dict[str, int] = {}
    facade_counts: dict[str, int] = {}
    mapped_method_counts: dict[str, int] = {}
    concrete_plants: list[dict[str, Any]] = []

    for element in payload.get("elements") or []:
        tags = element.get("tags") or {}
        structure = tags.get("building:structure")
        facade = tags.get("building:material")
        if structure:
            structure_counts[str(structure)] = structure_counts.get(str(structure), 0) + 1
            mk = _osm_method_key(str(structure))
            if mk:
                mapped_method_counts[mk] = mapped_method_counts.get(mk, 0) + 1
        if facade:
            facade_counts[str(facade)] = facade_counts.get(str(facade), 0) + 1

        is_plant = (
            tags.get("industrial") == "concrete_plant"
            or (
                tags.get("man_made") == "works"
                and "concrete" in str(tags.get("product") or "").lower()
            )
        )
        if is_plant:
            lat = element.get("lat")
            lon = element.get("lon")
            center = element.get("center") or {}
            if lat is None:
                lat = center.get("lat")
            if lon is None:
                lon = center.get("lon")
            distance = None
            if lat is not None and lon is not None:
                distance = haversine_km(latitude, longitude, _f(lat), _f(lon))
            concrete_plants.append({
                "name": tags.get("name") or "",
                "latitude": lat,
                "longitude": lon,
                "distance_km": distance,
                "tag_basis": (
                    "industrial=concrete_plant"
                    if tags.get("industrial") == "concrete_plant"
                    else "man_made=works + product=concrete"
                ),
            })

    concrete_plants.sort(
        key=lambda x: float("inf") if x.get("distance_km") is None else float(x["distance_km"])
    )
    return {
        "status": "ok",
        "source": "OpenStreetMap via Overpass API",
        "structure_tag_counts": structure_counts,
        "facade_material_tag_counts": facade_counts,
        "mapped_method_counts_from_structure": mapped_method_counts,
        "concrete_plants": concrete_plants,
        "nearest_concrete_plant": concrete_plants[0] if concrete_plants else None,
        "interpretation": {
            "building:structure": "positive evidence of mapped construction method; coverage may be sparse",
            "building:material": "facade/external material only; supporting evidence, not structural proof",
            "concrete_plant": "mapped facility evidence only; no mapped result does not prove absence",
        },
    }


def fetch_osm_local_evidence(
    latitude: float,
    longitude: float,
    building_radius_m: int = 15000,
    concrete_radius_m: int = 100000,
    timeout_seconds: int = 22,
) -> dict[str, Any]:
    endpoint = os.environ.get(
        "AZRAS_OVERPASS_URL",
        "https://overpass-api.de/api/interpreter",
    )
    query = f"""
[out:json][timeout:{int(timeout_seconds)}];
(
  nwr(around:{int(building_radius_m)},{latitude},{longitude})["building:structure"];
  nwr(around:{int(building_radius_m)},{latitude},{longitude})["building:material"];
  nwr(around:{int(concrete_radius_m)},{latitude},{longitude})["industrial"="concrete_plant"];
  nwr(around:{int(concrete_radius_m)},{latitude},{longitude})["man_made"="works"]["product"~"concrete"];
);
out tags center 2500;
"""
    request = urllib.request.Request(
        endpoint,
        data=urllib.parse.urlencode({"data": query}).encode("utf-8"),
        headers={
            "User-Agent": "AZRAS-Planning-Basic/1.0 local-construction-screening",
            "Accept": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds + 5) as response:
            payload = json.loads(response.read().decode("utf-8"))
        result = parse_osm_local_evidence(payload, latitude, longitude)
        result["endpoint"] = endpoint
        result["building_radius_m"] = int(building_radius_m)
        result["concrete_radius_m"] = int(concrete_radius_m)
        return result
    except Exception as exc:
        return {
            "status": "unavailable",
            "source": "OpenStreetMap via Overpass API",
            "endpoint": endpoint,
            "error": str(exc),
            "mapped_method_counts_from_structure": {},
            "concrete_plants": [],
            "nearest_concrete_plant": None,
            "interpretation": "Online evidence unavailable; the screening must fall back to local AZRAS proxy data and Unknown where evidence is insufficient.",
        }


def screen_construction_methods(root_dir: str | Path, latitude: float, longitude: float, project=None, use_online_evidence: bool = True):
    project = project or {}
    suitability, method_rows = load_screening_master(root_dir)
    labels = _labels(method_rows)
    city_rows = suitability.get("cities") or []
    nearest = None
    distance = None
    quality = "none"
    if city_rows:
        nearest = min(city_rows, key=lambda c: haversine_km(latitude, longitude, _f(c.get("latitude")), _f(c.get("longitude"))))
        distance = haversine_km(latitude, longitude, _f(nearest.get("latitude")), _f(nearest.get("longitude")))
        quality = _proxy_quality(distance)

    common = project.get("common") or {}
    constraints = common.get("construction_constraints") or {}
    explicit_exclusions = set(str(x) for x in (constraints.get("legal_excluded_methods") or []))
    proxy_materials = set(nearest.get("materials") or []) if nearest else set()
    proxy_workforce = set(nearest.get("workforce") or []) if nearest else set()
    online = fetch_osm_local_evidence(latitude, longitude) if use_online_evidence else {
        "status":"disabled",
        "mapped_method_counts_from_structure":{},
        "concrete_plants":[],
        "nearest_concrete_plant":None,
    }
    osm_method_counts = online.get("mapped_method_counts_from_structure") or {}
    hazard_keys = ("seismic", "wind", "flood", "snow", "fire")
    method_master = suitability.get("method_profiles") or {}
    results = []

    for method_id, profile in method_master.items():
        label = labels.get(method_id, {"ja": method_id, "en": method_id})
        material_key = str(profile.get("material_key") or method_id)
        reasons_ja = []
        reasons_en = []

        osm_key = "rc" if material_key == "rc" else material_key
        osm_positive = int(osm_method_counts.get(osm_key, 0)) > 0
        if method_id in explicit_exclusions:
            status = "Excluded"
            reasons_ja.append("Projectに明示された法規・行政上の除外条件に該当")
            reasons_en.append("Explicitly excluded by a project-supplied legal/administrative constraint")
        elif osm_positive:
            status = "Candidate"
            reasons_ja.append(f"周辺OpenStreetMapで当該構造工法の実建物タグを確認 ({osm_method_counts.get(osm_key,0)}件)")
            reasons_en.append(f"Nearby OpenStreetMap contains mapped buildings using this structural method ({osm_method_counts.get(osm_key,0)} records)")
            if material_key == "rc":
                plant = online.get("nearest_concrete_plant")
                if plant and plant.get("distance_km") is not None:
                    reasons_ja.append(f"OSM上の最寄り生コンプラント候補: 約{float(plant['distance_km']):.0f}km")
                    reasons_en.append(f"Nearest mapped concrete-plant candidate: about {float(plant['distance_km']):.0f} km")
                else:
                    reasons_ja.append("生コンプラントはOSM上で確認できないため、04で供給条件を確認")
                    reasons_en.append("No concrete plant is mapped in the queried OSM radius; verify supply in 04")
        elif quality == "none":
            status = "Unknown"
            reasons_ja.append("周辺OSM構造タグ・近傍代表都市とも根拠不足のため自動判定しない")
            reasons_en.append("Neither nearby OSM structural tags nor a sufficiently local representative-city proxy provides evidence")
        else:
            material_seen = material_key in proxy_materials
            workforce_seen = material_key in proxy_workforce
            if material_seen and workforce_seen:
                status = "Candidate"
                reasons_ja.append("近傍代表地域で材料供給と施工技能の両方が確認済み")
                reasons_en.append("Material supply and workforce are both present in the nearby proxy region")
            elif material_seen or workforce_seen:
                status = "Conditional"
                reasons_ja.append("近傍代表地域で材料または施工技能の片方のみ確認")
                reasons_en.append("Only material supply or workforce is confirmed in the nearby proxy region")
            else:
                status = "Conditional" if quality in ("high", "medium") else "Unknown"
                reasons_ja.append("近傍代表地域で当該工法の供給・技能を確認できない")
                reasons_en.append("The nearby proxy region does not confirm supply/workforce for this method")

            hazard_flags = []
            if nearest and quality in ("high", "medium"):
                for hk in hazard_keys:
                    if _f(nearest.get(hk)) > _f(profile.get(hk)):
                        hazard_flags.append(hk)
                if hazard_flags:
                    if status == "Candidate":
                        status = "Conditional"
                    reasons_ja.append("災害条件に対し追加設計・法規確認が必要: " + ", ".join(hazard_flags))
                    reasons_en.append("Additional hazard design/code verification required: " + ", ".join(hazard_flags))

            if method_id == "masonry" and nearest and quality in ("high", "medium") and _f(nearest.get("seismic")) >= 4:
                if status == "Candidate":
                    status = "Conditional"
                reasons_ja.append("高地震条件のため無筋組積造と補強組積造を分けて確認する必要あり")
                reasons_en.append("High seismic proxy: unreinforced and reinforced masonry must be assessed separately")

            if method_id == "earth" and nearest and quality in ("high", "medium") and _f(nearest.get("seismic")) >= 3:
                if status == "Candidate":
                    status = "Conditional"
                reasons_ja.append("土・Adobe系は耐震補強方式と現地法規の確認が必要")
                reasons_en.append("Earth/adobe construction requires seismic reinforcement and local-code verification")

            if material_key == "rc" and material_key not in proxy_materials:
                reasons_ja.append("生コン・RC供給網は未確認。プラント/輸送条件を04で詳細確認")
                reasons_en.append("Ready-mix/RC supply chain not confirmed; verify plant/transport conditions in 04")

        results.append({
            "method_id": method_id,
            "label_ja": label["ja"],
            "label_en": label["en"],
            "status": status,
            "material_key": material_key,
            "reasons_ja": reasons_ja,
            "reasons_en": reasons_en,
        })

    counts = {key: sum(1 for r in results if r["status"] == key) for key in STATUS_ORDER}
    result = {
        "version": "1.1",
        "stage": "01_preliminary_method_screening",
        "latitude": float(latitude),
        "longitude": float(longitude),
        "status_definitions": {
            "Candidate": "現時点で候補として残す",
            "Conditional": "条件付き候補。04で供給・技能・法規・物流を詳細確認",
            "Excluded": "明示された法規・行政条件により除外",
            "Unknown": "根拠データ不足。除外しない",
        },
        "local_construction_evidence": {
            "source": "data/regional_suitability_database_v1.json",
            "nearest_reference_city": None if not nearest else nearest.get("name"),
            "nearest_reference_country": None if not nearest else nearest.get("country"),
            "distance_km": distance,
            "proxy_quality": quality,
            "materials_observed_in_proxy": sorted(proxy_materials) if quality != "none" else [],
            "workforce_observed_in_proxy": sorted(proxy_workforce) if quality != "none" else [],
            "online_osm_evidence": online,
            "limitations": [
                "Representative-city data are a proxy, not proof of the exact site's current supply chain.",
                "Absence from the proxy database is not proof that a material or trade is unavailable.",
                "No method is legally excluded unless an explicit legal_excluded_methods rule is supplied.",
                "Remote locations beyond 500 km from a reference city default to Unknown unless positive local OSM structural evidence exists.",
                "OSM building:structure is positive mapped evidence but coverage is incomplete.",
                "OSM building:material describes facade/external material and is not treated as structural proof.",
                "No mapped concrete plant is never interpreted as proof that ready-mix concrete is unavailable."
            ],
        },
        "methods": results,
        "counts": counts,
        "next_step": "regional supply/logistics/legal/workforce verification",
    }
    return apply_regulatory_hazard_rules(root_dir, result, project)
