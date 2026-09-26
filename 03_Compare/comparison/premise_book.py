# -*- coding: utf-8 -*-
"""PATCH_005: comparison premise book (比較前提表).

03 Compare exists to show how much the environmental load and the business case
of the SAME building change when only the construction method changes.  For the
business case that is only true when every Project is priced and evaluated on
the same premises.  This module

1. reads the saved Projects and lists
   * the shared cost items whose unit prices differ (単価差リスト),
   * the items that some Projects carry and others do not (範囲差リスト),
   * the Module 5/6/7 settings that differ, and the rent premise,
   * the method-dependent premises that must stay different (display only);
2. lets a human decide each difference (the UI lives in premise_book_ui.py);
3. writes a comparison-group folder containing the premise book and one
   COPY of every Project with the decided prices and premises applied.

Every copy is written inside the group folder; no source Project is ever
modified.  A copy must then be recalculated in 01 Planning (Module 5) and
02 Evaluation (Modules 6/7) before it is compared; verify_group() reports
anything that is not yet in that state.

No tkinter import here, so the logic is testable without a display server.
"""
from __future__ import annotations

import copy
import hashlib
import json
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

BOOK_SCHEMA = "AZRAS_COMPARISON_PREMISE_BOOK_V1"
COPY_SCHEMA = "AZRAS_COMPARISON_COPY_V1"
COPY_SUFFIX = "__CMP"
COPY_ALLOWED_MODULES = ["module5", "module6", "module7"]
PRICE_TOLERANCE = 0.02
EQUIPMENT_KEYS = ("hvac", "electrical", "plumbing", "kitchen", "bathroom", "other")
# Module 6 values that are RESULTS written back into settings, not premises.
DERIVED_SETTING_KEYS = {"resolved_annual_rent_per_m2", "resolved_year1_gross_rent", "resolved_monthly_rent_per_unit",
                        "rent_setting_basis", "implied_gross_yield_percent", "analysis_years",
                        "moving_expense_standard_migrated"}
# PATCH_007: the target-gross-yield fields of 02 Evaluation PATCH_009.  The
# premise book always puts every copy on the market-rent method, where the
# target yield is only a stored preference (target_gross_yield_active=false).  An inactive
# yield is not a premise, so a difference in it must not appear as a premise
# difference, and a book must never write one back into a copy.
RENT_YIELD_MEMO_KEYS = {"target_gross_yield_percent", "stored_target_gross_yield_percent",
                        "target_gross_yield_active"}
_HERE = Path(__file__).resolve().parent


# --------------------------------------------------------------------- basics
def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _f(v, d=None):
    try:
        return float(v)
    except (TypeError, ValueError):
        return d


def file_sha256(path: str | Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def load_classification(path: str | Path | None = None) -> dict[str, Any]:
    p = Path(path) if path else _HERE / "item_classification_default.json"
    return json.loads(p.read_text(encoding="utf-8"))


def classify(key: str, classification: dict[str, Any]) -> str:
    if key in set((classification.get("method_specific") or {}).get("keys") or []):
        return "method_specific"
    if key in set((classification.get("method_dependent_work") or {}).get("keys") or []):
        return "method_dependent_work"
    return "common"


def project_label(project: dict[str, Any], language: str = "en") -> str:
    """PATCH_006: 01 Planning saves construction_method_(detail_)name_en/_ja;
    the old lookup read a non-existent 'construction_method_name' field and so
    always fell back to the raw id ("[rc_frame]", "[azras]").  The persisted
    label stays English-canonical; the screen asks for language="ja"."""
    c = project.get("common") or {}
    name = str(c.get("project_name") or (c.get("project_identity") or {}).get("project_name") or "Project")
    if language == "ja":
        from comparison.extractor import _method_ja
        method = str(_method_ja(project) or "")
    else:
        method = str(c.get("construction_method_detail_name_en") or c.get("construction_method_name_en")
                     or c.get("construction_method_name") or c.get("construction_method_id") or "")
    return f"{name} [{method}]" if method else name


def _currency(project: dict[str, Any]) -> str:
    m5 = (project.get("module_outputs") or {}).get("module5") or {}
    return str(m5.get("currency") or (project.get("common") or {}).get("currency") or "JPY").upper()


# ------------------------------------------------------------- price tables
def project_price_table(project: dict[str, Any]) -> dict[str, Any]:
    """Unit prices and equipment package prices as saved in Module 5."""
    m5 = (project.get("module_outputs") or {}).get("module5") or {}
    lines: dict[str, Any] = {}
    for L in m5.get("cost_lines") or []:
        if not isinstance(L, dict):
            continue
        key = str(L.get("cost_item_key") or "")
        if not key:
            continue
        installed = _f(L.get("installed_all_in_unit_cost"))
        split = sum(_f(L.get(k), 0.0) for k in ("material_unit_cost", "labor_unit_cost", "equipment_unit_cost"))
        rate = installed if installed is not None else split
        meta = L.get("regional_unit_cost_metadata") if isinstance(L.get("regional_unit_cost_metadata"), dict) else {}
        cq = meta.get("candidate_quality") if isinstance(meta.get("candidate_quality"), dict) else {}
        ev = {}
        for k in ("installed_evidence", "provisional_evidence"):
            e = meta.get(k)
            if isinstance(e, dict) and str(e.get("status") or "") == "found":
                ev = e
                break
        lines[key] = {
            "unit": str(L.get("unit") or ""),
            "quantity": _f(L.get("quantity"), 0.0),
            "rate": rate,
            "pricing_structure": str(L.get("pricing_structure") or ""),
            "scope_definition": str(cq.get("scope_definition") or ""),
            "source_title": str(ev.get("source_title") or meta.get("source_name") or ""),
            "source_url": str(ev.get("source_url") or ""),
            "pricing_status": str(L.get("pricing_status") or ""),
            "reviewer": str(meta.get("reviewer") or ""),
        }
    snap = m5.get("_input_snapshot") or {}
    ov = snap.get("ai_cost_provider_overlay") if isinstance(snap.get("ai_cost_provider_overlay"), dict) else {}
    ov_pk = {str(r.get("package_key")): r for r in (ov.get("equipment_packages") or []) if isinstance(r, dict)}
    sel = snap.get("equipment_selection") or {}
    packages: dict[str, Any] = {}
    for key in EQUIPMENT_KEYS:
        rec = ov_pk.get(key)
        s = sel.get(key) if isinstance(sel.get(key), dict) else {}
        # The INPUT price (what was adopted or entered), not the saved result,
        # which older engines had multiplied by a method-dependent calibration.
        cost = _f((rec or {}).get("cost")) if rec else _f(s.get("cost"))
        include = bool(s.get("include", True)) if s else bool(rec)
        if cost is None or cost <= 0 or not include:
            continue
        src = (rec or {}).get("source") if isinstance((rec or {}).get("source"), dict) else {}
        packages[key] = {"cost": cost, "source_title": str(src.get("source_title") or ""),
                         "source_url": str(src.get("source_url") or ""),
                         "basis": "ai_session" if rec else str(s.get("cost_basis") or "ui_local_currency")}
    return {"lines": lines, "packages": packages, "currency": _currency(project)}


def _settings(project: dict[str, Any], module: str) -> dict[str, Any]:
    out = (project.get("module_outputs") or {}).get(module) or {}
    st = (out.get("_input_snapshot") or {}).get("settings") or out.get("settings") or {}
    return st if isinstance(st, dict) else {}


def _method_premises(project: dict[str, Any]) -> dict[str, str]:
    """Durability / renewal premises that legitimately differ by method."""
    m3 = (project.get("module_outputs") or {}).get("module3") or {}
    ev = m3.get("events") or []
    rebuild = sorted({int(_f(e.get("year"), 0)) for e in ev
                      if e.get("action") == "full_rebuild" or e.get("component_key") in {"whole_building", "all_infill"}})
    structure = sorted({str(e.get("component_key")) for e in ev if str(e.get("component_key") or "").startswith("structure_")})
    retain = sorted({int(_f(e.get("year"), 0)) for e in ev if e.get("action") == "retain_skeleton"})
    return {
        "structure_component": ", ".join(structure) or "-",
        "full_rebuild_or_all_infill_years": ", ".join(str(y) for y in rebuild) or "-",
        "retain_skeleton_years": ", ".join(str(y) for y in retain) or "-",
    }


# --------------------------------------------------------------- the lists
def build_lists(projects: list[dict[str, Any]], classification: dict[str, Any],
                tolerance: float = PRICE_TOLERANCE) -> dict[str, Any]:
    """Difference lists for 2..n loaded Projects (same order as ``projects``)."""
    n = len(projects)
    tables = [project_price_table(p) for p in projects]
    labels = [project_label(p) for p in projects]
    blocking: list[str] = []
    currencies = sorted({t["currency"] for t in tables})
    if len(currencies) > 1:
        blocking.append("currency_mismatch:" + "/".join(currencies))
    addrs = sorted({str((p.get("common") or {}).get("project_location") or "") for p in projects})
    if len(addrs) > 1:
        blocking.append("location_mismatch")

    price_rows: list[dict[str, Any]] = []
    scope_rows: list[dict[str, Any]] = []
    all_keys = sorted(set().union(*[t["lines"].keys() for t in tables])) if tables else []
    for key in all_keys:
        cls = classify(key, classification)
        present = [i for i, t in enumerate(tables) if key in t["lines"]]
        if cls == "method_specific":
            continue
        if len(present) < n:
            scope_rows.append({"row_id": f"item:{key}", "kind": "item", "key": key, "class": cls,
                               "present": present, "missing": [i for i in range(n) if i not in present],
                               "quantities": {i: tables[i]["lines"][key]["quantity"] for i in present},
                               "unit": tables[present[0]]["lines"][key]["unit"]})
        if cls != "common" or len(present) < 2:
            continue
        units = {tables[i]["lines"][key]["unit"] for i in present}
        if len(units) > 1:
            scope_rows.append({"row_id": f"unit:{key}", "kind": "unit_mismatch", "key": key, "class": cls,
                               "present": present, "missing": [], "quantities": {}, "unit": "/".join(sorted(units))})
            continue
        cands = []
        for i in present:
            L = tables[i]["lines"][key]
            cands.append({"project_index": i, "label": labels[i], "rate": L["rate"], "scope_definition": L["scope_definition"],
                          "pricing_structure": L["pricing_structure"], "source_title": L["source_title"],
                          "source_url": L["source_url"], "reviewer": L["reviewer"], "quantity": L["quantity"]})
        rates = [c["rate"] for c in cands if c["rate"] is not None and c["rate"] > 0]
        differs = bool(rates) and (max(rates) / min(rates) > 1 + tolerance)
        price_rows.append({"row_id": f"unit_cost:{key}", "kind": "unit_cost", "key": key, "unit": next(iter(units)),
                           "candidates": cands, "differs": differs,
                           "ratio": (max(rates) / min(rates)) if rates else None,
                           "scopes": sorted({c["scope_definition"] for c in cands if c["scope_definition"]})})
    for fam, g in ((classification.get("families") or {}).get("groups") or {}).items():
        members = set(g.get("keys") or [])
        have = [i for i, t in enumerate(tables) if members & set(t["lines"])]
        if len(have) < n:
            scope_rows.append({"row_id": f"family:{fam}", "kind": "family", "key": fam, "class": "family",
                               "label_ja": g.get("ja"), "label_en": g.get("en"),
                               "present": have, "missing": [i for i in range(n) if i not in have],
                               "quantities": {i: sum(tables[i]["lines"][k]["quantity"] for k in members & set(tables[i]["lines"]))
                                              for i in have}, "unit": "m2"})
    for key in EQUIPMENT_KEYS:
        present = [i for i, t in enumerate(tables) if key in t["packages"]]
        if not present:
            continue
        if len(present) < n:
            scope_rows.append({"row_id": f"package:{key}", "kind": "package", "key": key, "class": "common",
                               "present": present, "missing": [i for i in range(n) if i not in present],
                               "quantities": {}, "unit": "lump_sum"})
        if len(present) >= 2:
            cands = [{"project_index": i, "label": labels[i], "rate": tables[i]["packages"][key]["cost"],
                      "scope_definition": "lump_sum", "pricing_structure": "lump_sum",
                      "source_title": tables[i]["packages"][key]["source_title"],
                      "source_url": tables[i]["packages"][key]["source_url"], "reviewer": "", "quantity": 1.0}
                     for i in present]
            rates = [c["rate"] for c in cands]
            price_rows.append({"row_id": f"equipment_package:{key}", "kind": "equipment_package", "key": key,
                               "unit": "lump_sum", "candidates": cands,
                               "differs": max(rates) / min(rates) > 1 + tolerance,
                               "ratio": max(rates) / min(rates), "scopes": ["lump_sum"]})

    business_rows: list[dict[str, Any]] = []
    for module in ("module5", "module6", "module7"):
        sts = [_settings(p, module) for p in projects]
        keys = sorted(set().union(*[s.keys() for s in sts])) if sts else []
        for k in keys:
            if k in DERIVED_SETTING_KEYS:
                continue
            if module == "module6" and k in RENT_YIELD_MEMO_KEYS:
                continue
            vals = {i: s.get(k) for i, s in enumerate(sts)}
            if any(isinstance(v, (dict, list)) for v in vals.values()):
                continue
            distinct = {json.dumps(v, ensure_ascii=False, sort_keys=True) for v in vals.values()}
            required = (module == "module6" and k in {"rent_setting_method", "annual_rent_per_m2"})
            business_rows.append({"row_id": f"{module}:{k}", "module": module, "key": k, "values": vals,
                                  "differs": len(distinct) > 1, "required": required})
    method_rows = [{"project_index": i, "label": labels[i], **_method_premises(p)} for i, p in enumerate(projects)]
    return {"labels": labels, "currency": currencies[0] if currencies else "", "blocking": blocking,
            "price_rows": price_rows, "scope_rows": scope_rows, "business_rows": business_rows,
            "method_premise_rows": method_rows, "tolerance": tolerance}


def default_decisions(lists: dict[str, Any]) -> dict[str, Any]:
    """A starting point for the human: nothing is unified until chosen.

    Price rows start as ``undecided``; business values start at the value shared
    by every Project (or the first Project's value), with the rent forced to the
    market-rent method and left EMPTY so it must be entered.
    """
    price = {r["row_id"]: {"mode": "undecided"} for r in lists["price_rows"]}
    scope = {r["row_id"]: {"decision": "undecided", "note": ""} for r in lists["scope_rows"]}
    business = {}
    for r in lists["business_rows"]:
        vals = [v for v in r["values"].values() if v is not None]
        business[r["row_id"]] = vals[0] if vals else None
    business["module6:rent_setting_method"] = "market_rent"
    business["module6:annual_rent_per_m2"] = None
    return {"price": price, "scope": scope, "business": business}


def validate_decisions(lists: dict[str, Any], decisions: dict[str, Any]) -> list[str]:
    """Reasons the premise book cannot be issued yet ([] = ready)."""
    out = []
    if lists["blocking"]:
        out.extend(lists["blocking"])
    for r in lists["price_rows"]:
        d = (decisions.get("price") or {}).get(r["row_id"]) or {}
        mode = d.get("mode")
        if mode == "undecided" and r["differs"]:
            out.append(f"price_undecided:{r['key']}")
        if mode == "unify" and not (_f(d.get("rate"), 0.0) > 0):
            out.append(f"price_rate_missing:{r['key']}")
    for r in lists["scope_rows"]:
        d = (decisions.get("scope") or {}).get(r["row_id"]) or {}
        if d.get("decision") not in {"accept_method_difference", "fix_source_quantity"}:
            out.append(f"scope_undecided:{r['key']}")
    b = decisions.get("business") or {}
    if b.get("module6:rent_setting_method") != "market_rent":
        out.append("rent_method_must_be_market_rent")
    if not (_f(b.get("module6:annual_rent_per_m2"), 0.0) > 0):
        out.append("market_rent_missing")
    return out


def premise_book_version(core: dict[str, Any]) -> str:
    raw = json.dumps(core, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()[:12]


def _safe_name(text: str) -> str:
    t = re.sub(r'[\\/:*?"<>|\s]+', "_", str(text or "").strip())
    return t.strip("._")[:60] or "group"


def _mark_pending(project: dict[str, Any], module: str, timestamp: str, reason: str) -> None:
    out = (project.get("module_outputs") or {}).get(module)
    if isinstance(out, dict) and out:
        meta = out.setdefault("_meta", {})
        meta.update({"is_current": False, "stale_since": timestamp, "stale_trigger": "comparison_premise_book",
                     "stale_reason": reason})
    project.setdefault("module_status", {})[module] = {
        "status": "recalculation_pending", "updated_at": timestamp, "save_mode": "comparison_copy",
        "source_modules": ["comparison_premise_book"], "message": reason}


def build_copy(source: dict[str, Any], source_path: str | Path, book_file: str, group_id: str, version: str,
               lists: dict[str, Any], decisions: dict[str, Any], timestamp: str) -> dict[str, Any]:
    """The comparison copy of one source Project (pure; nothing is written)."""
    p = copy.deepcopy(source)
    old_id = str(p.get("project_id") or "")
    new_id = str(uuid.uuid4())
    p["project_id"] = new_id
    common = p.setdefault("common", {})
    name = str(common.get("project_name") or "Project")
    if not name.endswith("[CMP]"):
        common["project_name"] = name + " [CMP]"
    p["comparison_copy"] = {
        "schema": COPY_SCHEMA, "group_id": group_id, "premise_book_file": book_file,
        "premise_book_version": version, "created_at": timestamp,
        "source_project_id": old_id, "source_project_name": name,
        "source_project_path": str(Path(source_path).resolve()),
        "source_sha256": file_sha256(source_path),
        "source_updated_at": source.get("updated_at"), "source_save_revision": source.get("save_revision"),
        "allowed_modules": list(COPY_ALLOWED_MODULES),
    }
    m5 = (p.get("module_outputs") or {}).get("module5") or {}
    snap = m5.setdefault("_input_snapshot", {})
    ov = snap.get("ai_cost_provider_overlay")
    if not isinstance(ov, dict):
        ov = {"unit_costs": {}, "equipment_packages": []}
        snap["ai_cost_provider_overlay"] = ov
    # PATCH 038 binding: an overlay whose project_id differs from the Project
    # is discarded by the engine, which would silently drop every price.
    ov["project_binding"] = {"project_id": new_id, "project_name": common.get("project_name")}
    units = ov.setdefault("unit_costs", {})
    pk = ov.get("equipment_packages") if isinstance(ov.get("equipment_packages"), list) else []
    pk_by_key = {str(r.get("package_key")): r for r in pk if isinstance(r, dict)}
    sel = snap.setdefault("equipment_selection", {})
    rows = {r["row_id"]: r for r in lists["price_rows"]}
    applied = {}
    for row_id, d in (decisions.get("price") or {}).items():
        if (d or {}).get("mode") != "unify" or row_id not in rows:
            continue
        r = rows[row_id]
        rate = float(d["rate"])
        chosen = next((c for c in r["candidates"] if c["project_index"] == d.get("from_project")), None) or {}
        cg = {"group_id": group_id, "premise_book_file": book_file, "premise_book_version": version,
              "chosen_from": chosen.get("label") or ("manual" if d.get("manual") else None),
              "source_title": chosen.get("source_title"), "source_url": chosen.get("source_url"),
              "scope_definition": chosen.get("scope_definition")}
        if r["kind"] == "unit_cost":
            units[r["key"]] = {"unit": r["unit"], "installed_unit_cost": rate, "pricing_structure": "installed_all_in",
                               "pricing_status": "comparison_group_confirmed", "certainty": "confirmed",
                               "display_color": "normal", "reviewer": "comparison_group_premise_book",
                               "source_json": book_file, "comparison_group": cg}
        else:
            rec = {"package_key": r["key"], "cost": rate, "unit_rate": None, "currency": lists.get("currency"),
                   "pricing_mode": "lump_sum", "certainty": "confirmed", "display_color": "normal",
                   "reviewer": "comparison_group_premise_book", "source_json": book_file,
                   "comparison_group": cg, "source": {"source_title": cg["source_title"], "source_url": cg["source_url"]}}
            pk_by_key[r["key"]] = rec
            item = sel.setdefault(r["key"], {})
            item.update({"include": True, "cost": rate, "cost_basis": "ai_approximate_cost_session_local_currency"})
        applied[r["key"]] = rate
    ov["equipment_packages"] = list(pk_by_key.values())
    # Business premises: identical in every copy.
    for row_id, value in (decisions.get("business") or {}).items():
        module, _, key = row_id.partition(":")
        if module == "module6" and key in RENT_YIELD_MEMO_KEYS:
            continue  # premise books issued before PATCH_007 may still carry it
        out = (p.get("module_outputs") or {}).get(module)
        if not isinstance(out, dict) or value is None:
            continue
        st = out.setdefault("_input_snapshot", {}).setdefault("settings", {})
        st[key] = value
    _apply_market_rent_yield_contract(p)
    reason = ("比較前提表を反映しました。01 Planning の Module 5、02 Evaluation の Module 6・7 の順に再計算してください。"
              " / Comparison premises applied: recalculate Module 5 (01 Planning), then Modules 6 and 7 (02 Evaluation).")
    for module in COPY_ALLOWED_MODULES:
        _mark_pending(p, module, timestamp, reason)
    p.setdefault("audit_log", []).append({"timestamp": timestamp, "action": "comparison_copy_created",
                                          "module": "03 Compare", "premise_book": book_file,
                                          "premise_book_version": version, "unified_items": applied})
    return p


def _apply_market_rent_yield_contract(project: dict[str, Any]) -> None:
    """PATCH_007: a market-rent copy carries the settings shape 02 Evaluation
    PATCH_009 itself saves: the user's yield preference stays in
    target_gross_yield_percent (Module 6 restores the UI from it and replaces a
    null with 8.0, which would lose e.g. 6.5), and target_gross_yield_active =
    False records that it does not drive the rent."""
    out = (project.get("module_outputs") or {}).get("module6")
    if not isinstance(out, dict):
        return
    st = (out.get("_input_snapshot") or {}).get("settings")
    if not isinstance(st, dict) or st.get("rent_setting_method") != "market_rent":
        return
    st["target_gross_yield_active"] = False


def write_group(parent_dir: str | Path, group_name: str, sources: list[tuple[str | Path, dict[str, Any]]],
                classification: dict[str, Any], lists: dict[str, Any], decisions: dict[str, Any],
                now: datetime | None = None) -> dict[str, Any]:
    """Create the comparison-group folder, the premise book and every copy.

    Everything is written INSIDE the new group folder.  Source Projects are
    only read.  Raises ValueError if the decisions are incomplete.
    """
    problems = validate_decisions(lists, decisions)
    if problems:
        raise ValueError("; ".join(problems))
    now = now or datetime.now(timezone.utc)
    stamp = now.strftime("%y%m%d_%H%M")
    timestamp = now.replace(microsecond=0).isoformat().replace("+00:00", "Z")
    parent = Path(parent_dir)
    folder = parent / f"{stamp}_比較_{_safe_name(group_name)}"
    folder.mkdir(parents=True, exist_ok=False)
    book_file = f"{stamp}_AZRAS_COMPARISON_PREMISE_BOOK.json"
    group_id = str(uuid.uuid4())
    src_records = [{"index": i, "label": project_label(pj), "project_id": pj.get("project_id"),
                    "path": str(Path(sp).resolve()), "sha256": file_sha256(sp),
                    "updated_at": pj.get("updated_at"), "save_revision": pj.get("save_revision"),
                    "construction_method_id": (pj.get("common") or {}).get("construction_method_id")}
                   for i, (sp, pj) in enumerate(sources)]
    core = {"sources": src_records, "classification": classification, "decisions": decisions}
    version = premise_book_version(core)
    copies = []
    for i, (sp, pj) in enumerate(sources):
        cp = build_copy(pj, sp, book_file, group_id, version, lists, decisions, timestamp)
        stem = Path(sp).stem + COPY_SUFFIX
        cdir = folder / stem
        cdir.mkdir(parents=True, exist_ok=False)
        cpath = cdir / f"{stem}.json"
        cpath.write_text(json.dumps(cp, ensure_ascii=False, indent=2), encoding="utf-8")
        copies.append({"index": i, "path": str(cpath), "relative_path": str(cpath.relative_to(folder)),
                       "project_id": cp["project_id"], "source_project_id": pj.get("project_id")})
    book = {"schema": BOOK_SCHEMA, "version": version, "group_id": group_id, "group_name": group_name,
            "created_at": timestamp, "tolerance": lists.get("tolerance"), "currency": lists.get("currency"),
            "sources": src_records, "copies": copies, "classification": classification,
            "lists": {"price_rows": lists["price_rows"], "scope_rows": lists["scope_rows"],
                      "business_rows": lists["business_rows"], "method_premise_rows": lists["method_premise_rows"]},
            "decisions": decisions,
            "note_ja": ("同じ建物で工法だけを変えた比較のための前提表。共通工種の単価・設備一式・Module 5/6/7 の前提を統一し、"
                        "工法固有の工種・工法で仕事が違う工種・耐用年数と更新周期は各Projectの値のまま残す。"
                        "各コピーは 01 Planning の Module 5、02 Evaluation の Module 6・7 で再計算してから比較する。"),
            "note_en": ("Premise book for comparing the same building built with different methods. Shared unit prices, "
                        "equipment packages and Module 5/6/7 premises are unified; method-specific items, method-dependent "
                        "work, durability and renewal cycles keep each Project's own values. Recalculate every copy in "
                        "01 Planning (Module 5) and 02 Evaluation (Modules 6/7) before comparing.")}
    (folder / book_file).write_text(json.dumps(book, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"folder": str(folder), "book_path": str(folder / book_file), "version": version, "copies": copies}


# ----------------------------------------------------------------- checking
def verify_copy(project: dict[str, Any]) -> list[dict[str, Any]]:
    """Issues with ONE comparison copy (empty list = ready to compare)."""
    cc = project.get("comparison_copy")
    if not (isinstance(cc, dict) and cc.get("schema") == COPY_SCHEMA):
        return []
    issues = []
    src = Path(str(cc.get("source_project_path") or ""))
    if not src.exists():
        issues.append({"code": "source_missing", "path": str(src)})
    else:
        try:
            if file_sha256(src) != cc.get("source_sha256"):
                issues.append({"code": "source_changed", "path": str(src)})
        except OSError:
            issues.append({"code": "source_unreadable", "path": str(src)})
    status = project.get("module_status") or {}
    for m in COPY_ALLOWED_MODULES:
        st = str((status.get(m) or {}).get("status") or "")
        if st in {"recalculation_pending", "stale", "error", ""}:
            issues.append({"code": "not_recalculated", "module": m})
    m5 = (project.get("module_outputs") or {}).get("module5") or {}
    fp = m5.get("price_basis_fingerprint") if isinstance(m5.get("price_basis_fingerprint"), dict) else {}
    if fp and fp.get("premise_book_version") not in (None, cc.get("premise_book_version")):
        issues.append({"code": "priced_with_other_version", "found": fp.get("premise_book_version")})
    return issues


def verify_group(projects: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Issues across the loaded copies of one comparison."""
    copies = [p for p in projects if isinstance(p.get("comparison_copy"), dict)
              and p["comparison_copy"].get("schema") == COPY_SCHEMA]
    if not copies:
        return []
    out = []
    if len(copies) != len(projects):
        out.append({"code": "mixed_copies_and_originals"})
    versions = {str(p["comparison_copy"].get("premise_book_version")) for p in copies}
    if len(versions) > 1:
        out.append({"code": "different_premise_book_versions", "versions": sorted(versions)})
    rents = set()
    for p in copies:
        st = _settings(p, "module6")
        rents.add((str(st.get("rent_setting_method")), _f(st.get("annual_rent_per_m2"))))
    if len(rents) > 1:
        out.append({"code": "different_rent_premises", "values": sorted(str(x) for x in rents)})
    return out
