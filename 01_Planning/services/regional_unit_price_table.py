# -*- coding: utf-8 -*-
"""PATCH_052: fixed regional unit-price table (地域単価表).

Purpose
-------
Two Projects in the same region used to get different AI prices for the same
item, because every Project asked the AIs again.  The first Project's adopted
multi-AI prices are now written to ONE standalone, versioned table per region
(not per construction method).  Later Projects in that region read the table
instead of searching again; only items the table does not have yet are sent
to the AIs, and once adopted they are appended to the same table.

Rules (agreed with the developer, 2026-10-01)
---------------------------------------------
* One standalone file per region and version, e.g. ``2026-10``, kept OUTSIDE
  every Project folder, so moving an old drawing set's data away never moves
  the table.
* Match key = cost item + spec key + unit + scale class.  The spec key is the
  construction method only for items whose work differs by method under the
  same key (formwork, concrete, reinforcing steel, phenolic foam - the same
  list 03 Compare uses); otherwise ``common``.
* Scale class comes from gross floor area.  Boundaries are stored in the table
  and can be edited there.
* No silent substitution: an item missing for this scale class is
  "unregistered" and goes to the AIs; another class's price is never used.
* A registered price is never overwritten.  New prices need a new version.

No tkinter import; testable headless.  Nothing here invents a price: every
value written comes from an adopted AI record of a Project.
"""
from __future__ import annotations

import copy
import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCHEMA = "AZRAS_REGIONAL_UNIT_PRICE_TABLE"
SCHEMA_VERSION = "1.0"
FOLDER_NAME = "Regional_Unit_Price_Tables"
FILE_PREFIX = "AZRAS_UNIT_PRICE_TABLE_"
TABLE_PRICING_STATUS = "regional_price_table_fixed"

DEFAULT_SCALE_CLASSES: list[dict[str, Any]] = [
    {"id": "S", "label_ja": "小", "label_en": "Small", "max_gross_floor_area_m2": 300.0},
    {"id": "M", "label_ja": "中", "label_en": "Medium", "max_gross_floor_area_m2": 3000.0},
    {"id": "L", "label_ja": "大", "label_en": "Large", "max_gross_floor_area_m2": None},
]
# Same list as 03 Compare item_classification_default.json "method_dependent_work".
DEFAULT_METHOD_DEPENDENT_KEYS = ["formwork", "concrete", "reinforcing_steel", "phenolic_foam"]

_VERSION_RE = re.compile(r"^\d{4}-\d{2}(?:\.\d+)?$")
PRICE_FIELDS = ("pricing_structure", "installed_unit_cost", "material", "labor", "equipment",
                "unit", "source_pricing_structure")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def region_slug(region_key: Any) -> str:
    text = re.sub(r"[^A-Za-z0-9]+", "_", str(region_key or "")).strip("_")
    return text or "Region"


def table_filename(region_key: Any, version: str) -> str:
    return f"{FILE_PREFIX}{region_slug(region_key)}_{version}.json"


def table_directory(json_root: str | Path) -> Path:
    path = Path(json_root) / FOLDER_NAME
    path.mkdir(parents=True, exist_ok=True)
    return path


def _version_sort_key(version: str) -> tuple[int, int, int]:
    m = re.match(r"^(\d{4})-(\d{2})(?:\.(\d+))?$", str(version or ""))
    if not m:
        return (0, 0, 0)
    return (int(m.group(1)), int(m.group(2)), int(m.group(3) or 1))


def validate_table(table: Any) -> list[str]:
    """Return a list of problems; empty means usable."""
    problems: list[str] = []
    if not isinstance(table, dict):
        return ["not a JSON object"]
    if table.get("schema") != SCHEMA:
        problems.append(f"schema is not {SCHEMA}")
    for key in ("region_key", "currency", "version"):
        if not str(table.get(key) or "").strip():
            problems.append(f"{key} missing")
    if table.get("version") and not _VERSION_RE.match(str(table.get("version"))):
        problems.append("version must look like YYYY-MM or YYYY-MM.n")
    classes = table.get("scale_classes")
    if not isinstance(classes, list) or not classes:
        problems.append("scale_classes missing")
    else:
        ids = [str((c or {}).get("id") or "") for c in classes]
        if "" in ids or len(set(ids)) != len(ids):
            problems.append("scale_classes ids must be unique and non-empty")
        last = -1.0
        for i, c in enumerate(classes):
            mx = (c or {}).get("max_gross_floor_area_m2")
            if mx is None:
                if i != len(classes) - 1:
                    problems.append("only the last scale class may have no upper bound")
                continue
            try:
                mxf = float(mx)
            except (TypeError, ValueError):
                problems.append(f"scale class {ids[i]}: upper bound is not a number")
                continue
            if mxf <= last:
                problems.append("scale class upper bounds must increase")
            last = mxf
        if classes and (classes[-1] or {}).get("max_gross_floor_area_m2") is not None:
            problems.append("the last scale class must have no upper bound")
    if not isinstance(table.get("entries"), dict):
        problems.append("entries must be a JSON object")
    return problems


def load_table(path: str | Path) -> dict[str, Any]:
    raw = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    problems = validate_table(raw)
    if problems:
        raise ValueError("; ".join(problems))
    return raw


def list_tables(directory: str | Path, region_key: Any) -> list[tuple[str, Path]]:
    """All valid tables of one region, oldest version first."""
    out: list[tuple[str, Path]] = []
    d = Path(directory)
    if not d.exists():
        return out
    for p in d.glob(f"{FILE_PREFIX}{region_slug(region_key)}_*.json"):
        try:
            raw = load_table(p)
        except Exception:
            continue
        if str(raw.get("region_key")) != str(region_key):
            continue
        out.append((str(raw.get("version")), p))
    out.sort(key=lambda x: _version_sort_key(x[0]))
    return out


def latest_table_path(directory: str | Path, region_key: Any) -> Path | None:
    tables = list_tables(directory, region_key)
    return tables[-1][1] if tables else None


def next_version(existing: list[str], now: datetime | None = None) -> str:
    """YYYY-MM of now (UTC); YYYY-MM.2, .3 ... when that month already exists."""
    now = now or datetime.now(timezone.utc)
    base = now.strftime("%Y-%m")
    taken = set(existing)
    if base not in taken:
        return base
    n = 2
    while f"{base}.{n}" in taken:
        n += 1
    return f"{base}.{n}"


def table_sha256(table: dict[str, Any]) -> str:
    text = json.dumps(table, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def save_table(table: dict[str, Any], directory: str | Path) -> Path:
    problems = validate_table(table)
    if problems:
        raise ValueError("; ".join(problems))
    path = Path(directory) / table_filename(table["region_key"], table["version"])
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(table, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)
    return path


def new_table(region_key: str, currency: str, version: str, *, previous: dict[str, Any] | None = None) -> dict[str, Any]:
    """A new version.  Copies scale classes, method list and entries of ``previous``."""
    table = {
        "schema": SCHEMA,
        "schema_version": SCHEMA_VERSION,
        "region_key": str(region_key),
        "currency": str(currency).upper(),
        "version": str(version),
        "price_basis_date": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "created_at": _now_iso(),
        "previous_version": (previous or {}).get("version"),
        "scale_classes": copy.deepcopy((previous or {}).get("scale_classes") or DEFAULT_SCALE_CLASSES),
        "method_dependent_keys": list((previous or {}).get("method_dependent_keys") or DEFAULT_METHOD_DEPENDENT_KEYS),
        "note_ja": ("同一地域の建設費単価を固定するための表。最初のProjectで複数AIが採用した単価を登録し、"
                    "以後の同地域Projectはこの表を使う。登録済みの単価は上書きしない。単価を更新するときは新しい版を作る。"
                    "scale_classes の境界値（延床面積 m2）はこのファイルで変更できる。"),
        "note_en": ("Fixes construction unit prices within one region. Prices adopted by the multi-AI review of the "
                    "first Project are registered here and later Projects in the region use them. A registered price "
                    "is never overwritten; make a new version to update prices. The scale_classes boundaries "
                    "(gross floor area, m2) can be edited in this file."),
        "entries": copy.deepcopy((previous or {}).get("entries") or {}),
        "history": [],
    }
    if previous:
        table["history"].append({"at": _now_iso(), "action": "created_from_previous_version",
                                 "previous_version": previous.get("version"),
                                 "copied_entry_count": len(table["entries"])})
    else:
        table["history"].append({"at": _now_iso(), "action": "created"})
    return table


def scale_class_for(gross_floor_area_m2: Any, classes: list[dict[str, Any]]) -> str | None:
    try:
        gfa = float(gross_floor_area_m2)
    except (TypeError, ValueError):
        return None
    if gfa <= 0:
        return None
    for c in classes:
        mx = c.get("max_gross_floor_area_m2")
        if mx is None or gfa <= float(mx):
            return str(c.get("id"))
    return None


def spec_key_for(cost_item_key: str, construction_method: str, table: dict[str, Any]) -> str:
    keys = set(table.get("method_dependent_keys") or DEFAULT_METHOD_DEPENDENT_KEYS)
    return str(construction_method or "general") if cost_item_key in keys else "common"


def entry_key(cost_item_key: str, spec_key: str, unit: str, scale_class: str) -> str:
    return f"{cost_item_key}|{spec_key}|{unit}|{scale_class}"


def candidate_total(rec: Any) -> float | None:
    if not isinstance(rec, dict):
        return None
    structure = str(rec.get("pricing_structure") or "").lower()
    try:
        if structure == "installed_all_in":
            return float(rec.get("installed_unit_cost"))
        if structure == "provisional_estimate":
            return float(rec.get("provisional_unit_cost"))
        if structure == "component_split":
            return sum(float(rec.get(x)) for x in ("material", "labor", "equipment"))
    except (TypeError, ValueError):
        return None
    return None


def _ai_candidates_for(sessions: list[dict[str, Any]], key: str, bucket: str) -> list[dict[str, Any]]:
    out = []
    for s in sessions or []:
        c = (s.get(bucket) or {}).get(key)
        if not isinstance(c, dict):
            continue
        value = candidate_total(c) if bucket == "unit_cost_candidates" else c.get("unit_rate")
        out.append({"reviewer": s.get("reviewer"), "research_role": s.get("research_role"),
                    "value": value, "completed_at": s.get("completed_at"), "source_json": s.get("source_json")})
    return out


def entries_from_overlay(overlay: dict[str, Any], table: dict[str, Any], *, units: dict[str, str],
                         construction_method: str, scale_class: str, project_info: dict[str, Any]) -> list[dict[str, Any]]:
    """Registrable entries from a Project's adopted AI overlay.

    Only AI-adopted records are taken (a price already coming from a table, a
    premise book or a manual edit is not an AI adoption of this Project).
    Equipment is registered only when it was priced per m2 of floor area; a
    lump sum for one building cannot be moved to another building.
    """
    sessions = list((overlay or {}).get("ai_candidate_sessions") or [])
    audit = (overlay or {}).get("reconciliation_audit") or {}
    out: list[dict[str, Any]] = []
    for key, rec in sorted(((overlay or {}).get("unit_costs") or {}).items()):
        if not isinstance(rec, dict) or not str(rec.get("pricing_status") or "").startswith("ai_"):
            continue
        unit = str(units.get(key) or rec.get("unit") or "")
        if not unit or candidate_total(rec) is None:
            continue
        spec = spec_key_for(key, construction_method, table)
        price = {f: rec.get(f) for f in PRICE_FIELDS if rec.get(f) is not None}
        price["unit"] = unit
        out.append({
            "entry_key": entry_key(key, spec, unit, scale_class),
            "kind": "unit_cost", "cost_item_key": key, "spec_key": spec, "unit": unit,
            "scale_class": scale_class, "price": price, "adopted_value": candidate_total(rec),
            "adopted_by": rec.get("reviewer"), "adoption_basis": (audit.get(key) or {}).get("adoption_basis"),
            "verification_stage": rec.get("verification_stage"),
            "evidence": rec.get("installed_evidence") or rec.get("source_components") or rec.get("provisional_evidence"),
            "ai_candidates": _ai_candidates_for(sessions, key, "unit_cost_candidates"),
            "added_from_project": dict(project_info),
        })
    currency = str(table.get("currency") or "")
    for rec in (overlay or {}).get("equipment_packages") or []:
        if not isinstance(rec, dict):
            continue
        if str(rec.get("pricing_mode") or "") != "unit_rate_per_gfa" or rec.get("unit_rate") in (None, ""):
            continue
        if str(rec.get("adoption_basis") or "") == "regional_price_table":
            continue
        try:
            rate = float(rec.get("unit_rate"))
        except (TypeError, ValueError):
            continue
        key = str(rec.get("package_key") or "")
        unit = f"{currency}/m2_gfa"
        out.append({
            "entry_key": entry_key(key, "common", unit, scale_class),
            "kind": "equipment_per_gfa", "cost_item_key": key, "spec_key": "common", "unit": unit,
            "scale_class": scale_class, "price": {"unit_rate": rate}, "adopted_value": rate,
            "adopted_by": rec.get("reviewer"), "adoption_basis": rec.get("adoption_basis"),
            "verification_stage": None, "evidence": rec.get("source"),
            "ai_candidates": _ai_candidates_for(sessions, key, "equipment_candidates"),
            "added_from_project": dict(project_info),
        })
    return out


def add_entries(table: dict[str, Any], entries: list[dict[str, Any]]) -> tuple[list[str], list[str]]:
    """Append entries; never overwrite.  Returns (added_keys, already_registered_keys)."""
    added: list[str] = []
    skipped: list[str] = []
    store = table.setdefault("entries", {})
    for e in entries:
        k = e["entry_key"]
        if k in store:
            skipped.append(k)
            continue
        rec = dict(e)
        rec["added_at"] = _now_iso()
        store[k] = rec
        added.append(k)
    if added:
        projects = sorted({str((e.get("added_from_project") or {}).get("project_name") or "") for e in entries if e["entry_key"] in added})
        table.setdefault("history", []).append({"at": _now_iso(), "action": "entries_added",
                                                "entry_keys": added, "projects": projects})
    return added, skipped


def apply_table(table: dict[str, Any], *, cost_items: dict[str, str], equipment_keys: list[str],
                construction_method: str, gross_floor_area_m2: float, table_file: str) -> dict[str, Any]:
    """Prices for this Project from the table.

    ``cost_items``: cost_item_key -> unit needed by this Project.
    Returns unit_costs (engine overlay format), equipment_packages, and the
    reference to record in the Project.  Missing entries are listed, never
    filled from another scale class.
    """
    scale = scale_class_for(gross_floor_area_m2, table.get("scale_classes") or [])
    if scale is None:
        raise ValueError("gross floor area is unknown; the scale class cannot be decided")
    store = table.get("entries") or {}
    unit_costs: dict[str, dict[str, Any]] = {}
    registered: list[str] = []
    unregistered: list[dict[str, Any]] = []
    for key, unit in sorted(cost_items.items()):
        spec = spec_key_for(key, construction_method, table)
        ek = entry_key(key, spec, str(unit), scale)
        e = store.get(ek)
        if not isinstance(e, dict) or e.get("kind") != "unit_cost":
            unregistered.append({"cost_item_key": key, "entry_key": ek, "kind": "unit_cost"})
            continue
        rec = dict(e.get("price") or {})
        rec.update({"pricing_status": TABLE_PRICING_STATUS, "certainty": "estimated", "display_color": "yellow",
                    "regional_price_table_entry": ek, "regional_price_table_version": table.get("version"),
                    "reviewer": e.get("adopted_by"), "verification_stage": "regional_price_table"})
        unit_costs[key] = rec
        registered.append(ek)
    currency = str(table.get("currency") or "")
    packages: list[dict[str, Any]] = []
    for key in sorted(equipment_keys):
        ek = entry_key(key, "common", f"{currency}/m2_gfa", scale)
        e = store.get(ek)
        if not isinstance(e, dict) or e.get("kind") != "equipment_per_gfa":
            unregistered.append({"cost_item_key": key, "entry_key": ek, "kind": "equipment"})
            continue
        rate = float((e.get("price") or {}).get("unit_rate"))
        packages.append({"package_key": key, "cost": rate * float(gross_floor_area_m2), "unit_rate": rate,
                         "currency": currency, "pricing_mode": "unit_rate_per_gfa", "certainty": "estimated",
                         "display_color": "yellow", "adoption_basis": "regional_price_table",
                         "regional_price_table_entry": ek, "regional_price_table_version": table.get("version"),
                         "reviewer": e.get("adopted_by")})
        registered.append(ek)
    ref = {
        "schema": SCHEMA, "table_file": table_file, "region_key": table.get("region_key"),
        "currency": currency, "version": table.get("version"), "sha256": table_sha256(table),
        "scale_class": scale, "gross_floor_area_m2": float(gross_floor_area_m2),
        "construction_method": construction_method, "applied_at": _now_iso(),
        "registered_entry_keys": registered, "unregistered_items": unregistered,
    }
    return {"unit_costs": unit_costs, "equipment_packages": packages, "ref": ref}
