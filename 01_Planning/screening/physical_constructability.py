from __future__ import annotations

from math import asin, cos, radians, sin, sqrt
from pathlib import Path
from typing import Any
import json
import os
import urllib.parse
import urllib.request


def _f(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371.0088
    p1, p2 = radians(lat1), radians(lat2)
    dp = radians(lat2 - lat1)
    dl = radians(lon2 - lon1)
    a = sin(dp / 2) ** 2 + cos(p1) * cos(p2) * sin(dl / 2) ** 2
    return 2 * r * asin(sqrt(a))


def _screening(project: dict[str, Any]) -> dict[str, Any]:
    common = project.get("common") or {}
    value = common.get("construction_feasibility_screening")
    return value if isinstance(value, dict) else {}


def _coords(project: dict[str, Any]) -> tuple[float | None, float | None]:
    s = _screening(project)
    lat = s.get("latitude")
    lon = s.get("longitude")
    if lat is not None and lon is not None:
        return _f(lat), _f(lon)
    common = project.get("common") or {}
    loc = common.get("location") or {}
    lat = loc.get("latitude", common.get("latitude"))
    lon = loc.get("longitude", common.get("longitude"))
    if lat is None or lon is None:
        return None, None
    return _f(lat), _f(lon)


def fetch_osm_logistics_evidence(latitude: float, longitude: float, timeout_seconds: int = 20) -> dict[str, Any]:
    endpoint = os.environ.get("AZRAS_OVERPASS_URL", "https://overpass-api.de/api/interpreter")
    query = (
        f"[out:json][timeout:{int(timeout_seconds)}];\n(\n"
        f'  nwr(around:5000,{latitude},{longitude})["highway"];\n'
        f'  nwr(around:100000,{latitude},{longitude})["industrial"="concrete_plant"];\n'
        f'  nwr(around:100000,{latitude},{longitude})["man_made"="works"]["product"~"concrete",i];\n'
        f'  nwr(around:100000,{latitude},{longitude})["harbour"="yes"];\n'
        f'  nwr(around:100000,{latitude},{longitude})["industrial"="port"];\n'
        f'  nwr(around:100000,{latitude},{longitude})["landuse"="port"];\n'
        ");\nout tags center 3500;"
    )
    request = urllib.request.Request(
        endpoint,
        data=urllib.parse.urlencode({"data": query}).encode("utf-8"),
        headers={"User-Agent": "AZRAS-Planning-Basic/1.0 physical-constructability", "Accept": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds + 5) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except Exception as exc:
        return {
            "status": "unavailable", "source": "OpenStreetMap via Overpass API", "endpoint": endpoint,
            "error": str(exc), "roads": [], "concrete_plants": [], "ports": [],
            "warning": "Online evidence unavailable. No negative conclusion is permitted from this failure.",
        }

    roads, plants, ports = [], [], []
    for element in payload.get("elements") or []:
        tags = element.get("tags") or {}
        lat = element.get("lat")
        lon = element.get("lon")
        center = element.get("center") or {}
        if lat is None:
            lat = center.get("lat")
        if lon is None:
            lon = center.get("lon")
        distance = None
        if lat is not None and lon is not None:
            distance = _haversine_km(latitude, longitude, _f(lat), _f(lon))
        if tags.get("highway"):
            roads.append({
                "highway": tags.get("highway"), "name": tags.get("name") or "", "distance_km": distance,
                "width": tags.get("width"), "maxweight": tags.get("maxweight"), "maxheight": tags.get("maxheight"),
                "surface": tags.get("surface"), "lanes": tags.get("lanes"),
            })
        is_plant = tags.get("industrial") == "concrete_plant" or (
            tags.get("man_made") == "works" and "concrete" in str(tags.get("product") or "").lower()
        )
        if is_plant:
            plants.append({"name": tags.get("name") or "", "distance_km": distance, "latitude": lat, "longitude": lon})
        is_port = tags.get("harbour") == "yes" or tags.get("industrial") == "port" or tags.get("landuse") == "port"
        if is_port:
            ports.append({"name": tags.get("name") or "", "distance_km": distance, "latitude": lat, "longitude": lon})

    key = lambda x: float("inf") if x.get("distance_km") is None else float(x["distance_km"])
    roads.sort(key=key)
    plants.sort(key=key)
    ports.sort(key=key)
    return {
        "status": "ok", "source": "OpenStreetMap via Overpass API", "endpoint": endpoint,
        "road_search_radius_km": 5, "plant_search_radius_km": 100, "port_search_radius_km": 100,
        "roads": roads, "concrete_plants": plants, "ports": ports,
        "nearest_road": roads[0] if roads else None,
        "nearest_concrete_plant": plants[0] if plants else None,
        "nearest_port": ports[0] if ports else None,
        "limitations": [
            "Mapped roads do not prove heavy-vehicle access; width, bridge, axle/load, height and permit checks may still be required.",
            "No mapped concrete plant does not prove ready-mix concrete is unavailable.",
            "A mapped port is logistics evidence only and does not prove cargo handling capacity for the project.",
            "OSM coverage varies by region.",
        ],
    }


METHOD_REQUIREMENTS = {
    "azras": ["ready_mix", "road_access", "heavy_equipment", "skilled_labor"],
    "rc_frame": ["ready_mix", "road_access", "heavy_equipment", "skilled_labor"],
    "rc_wall": ["ready_mix", "road_access", "heavy_equipment", "skilled_labor"],
    "steel": ["road_access", "heavy_equipment", "skilled_labor"],
    "mass_timber": ["road_access", "heavy_equipment", "skilled_labor"],
    "wood_post_beam": ["road_access", "skilled_labor"],
    "wood_frame": ["road_access", "skilled_labor"],
    "masonry": ["road_access", "skilled_labor"],
    "earth": ["road_access", "skilled_labor"],
    "other": ["road_access", "skilled_labor"],
}


def _auto_dimensions(project: dict[str, Any], online: dict[str, Any]) -> dict[str, dict[str, Any]]:
    s = _screening(project)
    ev = s.get("local_construction_evidence") or {}
    materials = set(ev.get("materials_observed_in_proxy") or [])
    workforce = set(ev.get("workforce_observed_in_proxy") or [])
    prior_online = ev.get("online_osm_evidence") if isinstance(ev.get("online_osm_evidence"), dict) else {}
    plant = online.get("nearest_concrete_plant") or prior_online.get("nearest_concrete_plant")
    road = online.get("nearest_road")
    port = online.get("nearest_port")

    ready = {"status": "Unknown", "evidence": [], "source": "none"}
    if plant and plant.get("distance_km") is not None:
        ready = {"status": "Evidence", "evidence": [f"mapped concrete plant candidate ~{float(plant['distance_km']):.0f} km"], "source": "OSM"}
    elif "rc" in materials:
        ready = {"status": "Proxy", "evidence": ["RC/concrete material supply appears in 01 representative-region proxy"], "source": "01_proxy"}

    road_dim = {"status": "Unknown", "evidence": [], "source": "none"}
    if road:
        info = f"mapped road {road.get('highway') or ''} ~{float(road.get('distance_km') or 0):.1f} km"
        extras = []
        for k in ("width", "maxweight", "maxheight", "surface", "lanes"):
            if road.get(k):
                extras.append(f"{k}={road[k]}")
        if extras:
            info += " (" + ", ".join(extras) + ")"
        road_dim = {"status": "Conditional", "evidence": [info, "heavy-vehicle suitability still requires width/bridge/load/height confirmation"], "source": "OSM"}

    port_dim = {"status": "Unknown", "evidence": [], "source": "none"}
    if port and port.get("distance_km") is not None:
        port_dim = {"status": "Evidence", "evidence": [f"mapped port/harbour candidate ~{float(port['distance_km']):.0f} km"], "source": "OSM"}

    equipment = {"status": "Unknown", "evidence": ["equipment availability cannot be verified from current map evidence"], "source": "none"}
    if any(x in workforce for x in ("rc", "steel", "mass_timber")):
        equipment = {"status": "Proxy", "evidence": ["industrial/structural workforce proxy exists; equipment still needs supplier confirmation"], "source": "01_proxy"}

    skill = {"status": "Unknown", "evidence": [], "source": "none"}
    if workforce:
        skill = {"status": "Proxy", "evidence": ["01 representative-region workforce proxy: " + ", ".join(sorted(workforce))], "source": "01_proxy"}

    return {"ready_mix": ready, "road_access": road_dim, "port_access": port_dim, "heavy_equipment": equipment, "skilled_labor": skill}


def evaluate_physical_constructability(project: dict[str, Any], overrides: dict[str, str] | None = None, use_online: bool = True) -> dict[str, Any]:
    overrides = overrides or {}
    latitude, longitude = _coords(project)
    online = {"status": "not_run", "roads": [], "concrete_plants": [], "ports": []}
    if use_online and latitude is not None and longitude is not None:
        online = fetch_osm_logistics_evidence(latitude, longitude)
    dimensions = _auto_dimensions(project, online)

    for key, value in overrides.items():
        mode = str(value or "Auto")
        if key not in dimensions or mode == "Auto":
            continue
        if mode == "Yes":
            dimensions[key] = {"status": "Confirmed", "evidence": ["user-confirmed in 01 AZRAS Planning"], "source": "user_override"}
        elif mode == "No":
            dimensions[key] = {"status": "Unavailable", "evidence": ["user-confirmed unavailable in regional constructability review"], "source": "user_override"}
        elif mode == "Unknown":
            dimensions[key] = {"status": "Unknown", "evidence": ["set to Unknown by user"], "source": "user_override"}

    screening = _screening(project)
    methods = []
    for src in screening.get("methods") or []:
        mid = str(src.get("method_id") or "")
        base_status = str(src.get("status") or "Unknown")
        req = METHOD_REQUIREMENTS.get(mid, ["road_access", "skilled_labor"])
        req_states = [dimensions.get(k, {}).get("status", "Unknown") for k in req]
        reasons = []
        if base_status == "Excluded":
            final = "Excluded"
            reasons.append("01 regulatory/administrative screening already marked this method Excluded")
        elif any(x == "Unavailable" for x in req_states):
            final = "Difficult"
            reasons.append("one or more required physical resources/access conditions are confirmed unavailable")
        elif all(x in ("Confirmed", "Evidence") for x in req_states):
            final = "Feasible"
            reasons.append("all required physical dimensions have direct/confirmed evidence")
        elif any(x == "Unknown" for x in req_states):
            final = "Unknown" if all(x == "Unknown" for x in req_states) else "Conditional"
            reasons.append("one or more required dimensions remain unverified")
        else:
            final = "Conditional"
            reasons.append("available evidence is proxy/conditional rather than direct confirmation")
        if base_status == "Conditional" and final == "Feasible":
            final = "Conditional"
            reasons.append("01 preliminary screening remains Conditional, so physical evidence alone cannot clear the method")
        methods.append({
            "method_id": mid,
            "label_ja": src.get("label_ja"),
            "label_en": src.get("label_en"),
            "screening_status_01": base_status,
            "physical_status": final,
            "required_dimensions": req,
            "required_dimension_states": {k: dimensions.get(k, {}).get("status", "Unknown") for k in req},
            "reasons": reasons,
        })

    statuses = ("Feasible", "Conditional", "Difficult", "Unknown", "Excluded")
    counts = {s: sum(1 for x in methods if x.get("physical_status") == s) for s in statuses}
    return {
        "version": "1.0",
        "stage": "01_physical_constructability_secondary_screening",
        "latitude": latitude,
        "longitude": longitude,
        "online_logistics_evidence": online,
        "dimension_assessment": dimensions,
        "manual_overrides": dict(overrides),
        "methods": methods,
        "counts": counts,
        "policy": {
            "Feasible": "all required physical dimensions have direct/confirmed evidence and 01 is not Conditional/Excluded",
            "Conditional": "construction may be possible but proxy evidence or unresolved conditions remain",
            "Difficult": "a required physical condition is explicitly confirmed unavailable",
            "Unknown": "insufficient evidence; method is not rejected",
            "Excluded": "carried forward only from explicit 01 regulatory/administrative exclusion",
        },
        "warning": "Planning feasibility screen only. It is not a logistics contract, permit, road-load certification or supplier guarantee.",
    }
