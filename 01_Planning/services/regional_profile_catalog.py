# -*- coding: utf-8 -*-
"""PATCH_053: regional (representative) cost-profile catalog.

tkinter-independent.  Three responsibilities:

1. ``load_construction_cost_database(root_dir)`` - read the built-in
   construction-cost database and merge every additional regional profile
   that exists on disk, so the Module 5 profile list is no longer a fixed
   list:
     a. user-added profiles   data/regional_profiles/*.json
     b. regional-cost datasets data/regional_cost/*.json whose ``region_key``
        ("Country / City") is not a built-in profile and which carries a
        complete ``regional_indices`` block and a currency.
   Built-in profiles are never overwritten by a file.

2. ``nearest_location(...)`` - great-circle distance from the Project
   coordinates to every profile that has coordinates; used by
   ``resolve_location_profile_from_project`` to pick the nearest profile
   inside the Project's country.

3. ``save_user_profile(...)`` - write one user profile file.

Every caller that calculates Module 5 (Module 5 itself and the automatic
recalculation in core/project_coordinator.py) must load the database through
this module, otherwise a saved Project that uses a user profile could not be
recalculated.
"""
from __future__ import annotations

import json
import math
import re
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

DATABASE_FILE = "construction_cost_database_v9_4.json"
USER_PROFILE_DIR = "regional_profiles"
REGIONAL_COST_DIR = "regional_cost"
USER_PROFILE_SCHEMA = "azras_regional_profile_v1"
INDEX_KEYS = ("material_index", "labor_index", "productivity_index")

# A nearest profile closer than this is treated as the Project's own region
# (no proxy warning, usable for the regional unit-price table without asking).
NEAREST_REGIONAL_MATCH_KM = 100.0


def _norm(value: Any) -> str:
    v = unicodedata.normalize("NFKC", str(value or "")).casefold()
    return re.sub(r"[^0-9a-z\u3040-\u30ff\u3400-\u9fff]+", "", v)


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371.0088
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = p2 - p1
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(min(1.0, math.sqrt(a)))


def _coord(value: Any) -> float | None:
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    if math.isnan(f) or math.isinf(f):
        return None
    return f


def location_coordinates(location: dict[str, Any]) -> tuple[float, float] | None:
    if not isinstance(location, dict):
        return None
    lat = _coord(location.get("latitude"))
    lon = _coord(location.get("longitude"))
    if lat is None or lon is None or not (-90 <= lat <= 90 and -180 <= lon <= 180):
        return None
    return lat, lon


def project_coordinates(project: dict[str, Any]) -> tuple[float, float] | None:
    """Project site coordinates (Module 0 stores them in common.latitude/longitude)."""
    if not isinstance(project, dict):
        return None
    common = project.get("common") or {}
    locobj = common.get("location") if isinstance(common.get("location"), dict) else {}
    for src in (common, locobj):
        c = location_coordinates(src)
        if c:
            return c
    return None


def split_location_key(key: str) -> tuple[str, str]:
    if " / " in str(key):
        a, b = str(key).split(" / ", 1)
        return a.strip(), b.strip()
    return "", str(key).strip()


def nearest_location(locations: dict[str, Any], lat: float, lon: float,
                     country_norm: str | None = None) -> tuple[str | None, float | None]:
    """Return (location_key, distance_km) of the nearest profile with coordinates.

    With ``country_norm`` only profiles of that (normalized) country are
    considered.  "User Defined" and keys without "Country / City" are skipped.
    """
    best: tuple[float, str] | None = None
    for key, loc in (locations or {}).items():
        if key == "User Defined" or " / " not in str(key):
            continue
        if country_norm:
            kc, _ = split_location_key(key)
            if _norm(kc) != country_norm:
                continue
        c = location_coordinates(loc)
        if not c:
            continue
        d = haversine_km(lat, lon, c[0], c[1])
        if best is None or d < best[0]:
            best = (d, key)
    if best is None:
        return None, None
    return best[1], round(best[0], 1)


def _profile_to_location(raw: dict[str, Any], source: str, path: Path) -> dict[str, Any] | None:
    try:
        currency = str(raw.get("currency") or "").strip().upper()
        idx = raw.get("regional_indices") if isinstance(raw.get("regional_indices"), dict) else raw
        values = {k: float(idx[k]) for k in INDEX_KEYS}
    except Exception:
        return None
    if not currency or any(v <= 0 for v in values.values()):
        return None
    year = raw.get("year")
    if year is None and raw.get("data_date"):
        m = re.match(r"(\d{4})", str(raw.get("data_date")))
        year = int(m.group(1)) if m else None
    loc: dict[str, Any] = {
        "currency": currency,
        "year": int(year or datetime.now(timezone.utc).year),
        **values,
        "unit_costs": {},
        "pricing_mode": "user_regional_profile" if source == "user_profile" else "regional_cost_dataset_profile",
        "pricing_status": "regional_index_estimate",
        "fx_jpy_per_local_currency": 1.0 if currency == "JPY" else 0.0,
        "profile_source": source,
        "profile_file": path.name,
    }
    c = location_coordinates(raw)
    if c:
        loc["latitude"], loc["longitude"] = c
    if source == "regional_cost_dataset":
        loc["dataset_file"] = f"data/{REGIONAL_COST_DIR}/{path.name}"
    for k in ("source_note", "note_ja", "created_utc"):
        if raw.get(k):
            loc[k] = raw.get(k)
    return loc


def _user_profile_dir(root_dir: Path) -> Path:
    return Path(root_dir) / "data" / USER_PROFILE_DIR


def load_extra_profiles(root_dir: str | Path, builtin_keys: set[str]) -> tuple[dict[str, Any], list[dict[str, str]]]:
    """Profiles found on disk that are not built in.  Errors are reported, not raised."""
    root = Path(root_dir)
    found: dict[str, Any] = {}
    errors: list[dict[str, str]] = []
    sources = (
        ("user_profile", _user_profile_dir(root), "location_key"),
        ("regional_cost_dataset", root / "data" / REGIONAL_COST_DIR, "region_key"),
    )
    for source, folder, key_field in sources:
        if not folder.is_dir():
            continue
        for p in sorted(folder.glob("*.json")):
            try:
                raw = json.loads(p.read_text(encoding="utf-8"))
            except Exception as exc:
                errors.append({"path": str(p), "error": str(exc)})
                continue
            if not isinstance(raw, dict):
                continue
            key = str(raw.get(key_field) or "").strip()
            if " / " not in key or key in builtin_keys or key in found:
                continue
            loc = _profile_to_location(raw, source, p)
            if loc is None:
                if source == "user_profile":
                    errors.append({"path": str(p), "error": "incomplete profile (currency / indices)"})
                continue
            found[key] = loc
    return found, errors


def load_construction_cost_database(root_dir: str | Path) -> dict[str, Any]:
    root = Path(root_dir)
    db = json.loads((root / "data" / DATABASE_FILE).read_text(encoding="utf-8"))
    locations = db.setdefault("locations", {})
    builtin = set(locations)
    extra, errors = load_extra_profiles(root, builtin)
    # Keep "User Defined" last in the list.
    user_defined = locations.pop("User Defined", None)
    locations.update(extra)
    if user_defined is not None:
        locations["User Defined"] = user_defined
    db["_regional_profile_catalog"] = {
        "builtin_count": len(builtin),
        "extra_profiles": sorted(extra),
        "errors": errors,
    }
    return db


def _safe_name(text: str) -> str:
    s = re.sub(r"[^0-9A-Za-z\u3040-\u30ff\u3400-\u9fff_-]+", "_", unicodedata.normalize("NFKC", str(text))).strip("_")
    return s or "profile"


def user_profile_path(root_dir: str | Path, country: str, city: str) -> Path:
    return _user_profile_dir(Path(root_dir)) / f"{_safe_name(country)}_{_safe_name(city)}.json"


def build_user_profile(country: str, city: str, latitude: Any, longitude: Any, currency: str,
                       year: Any, material_index: Any, labor_index: Any, productivity_index: Any,
                       source_note: str = "") -> dict[str, Any]:
    """Validate the input and return the profile file content.  Raises ValueError."""
    country = str(country or "").strip()
    city = str(city or "").strip()
    if not country or not city:
        raise ValueError("country and city are required")
    if "/" in country or "/" in city:
        raise ValueError("'/' cannot be used in country or city")
    lat, lon = _coord(latitude), _coord(longitude)
    if lat is None or lon is None or not (-90 <= lat <= 90 and -180 <= lon <= 180):
        raise ValueError("latitude/longitude are required (-90..90 / -180..180)")
    currency = str(currency or "").strip().upper()
    if not re.fullmatch(r"[A-Z]{3}", currency):
        raise ValueError("currency must be a 3-letter code such as JPY")
    try:
        year_i = int(float(year))
    except (TypeError, ValueError):
        raise ValueError("year must be a number")
    idx = {}
    for k, v in (("material_index", material_index), ("labor_index", labor_index),
                 ("productivity_index", productivity_index)):
        f = _coord(v)
        if f is None or f <= 0:
            raise ValueError(f"{k} must be a positive number")
        idx[k] = f
    return {
        "schema": USER_PROFILE_SCHEMA,
        "location_key": f"{country} / {city}",
        "country": country,
        "city": city,
        "latitude": lat,
        "longitude": lon,
        "currency": currency,
        "year": year_i,
        **idx,
        "source_note": str(source_note or "").strip(),
        "created_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }


def save_user_profile(root_dir: str | Path, profile: dict[str, Any], builtin_keys: set[str]) -> Path:
    """Write a user profile.  A built-in profile name is refused (ValueError)."""
    key = str(profile.get("location_key") or "")
    if key in builtin_keys:
        raise ValueError(f"'{key}' is a built-in profile and cannot be replaced")
    path = user_profile_path(root_dir, profile["country"], profile["city"])
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(profile, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def builtin_location_keys(root_dir: str | Path) -> set[str]:
    db = json.loads((Path(root_dir) / "data" / DATABASE_FILE).read_text(encoding="utf-8"))
    return set((db.get("locations") or {}).keys())
