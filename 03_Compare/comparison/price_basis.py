# -*- coding: utf-8 -*-
"""PATCH_008: price-basis assessment for the load-time premise check.

01 Planning (PATCH_040/043) stores module5.price_basis_fingerprint.basis_token.
03 Compare PATCH_003 warned whenever the loaded Projects did not share ONE
token.  Two defects followed from that:

1. Comparison copies made by the premise book (tab 7) could never pass.  The
   book unifies only the shared ("common") cost items.  Method-specific items
   and items whose work differs by method (formwork, concrete, reinforcing
   steel, phenolic foam) deliberately keep each Project's own price.  When one
   Project priced such an item from the built-in regional database and another
   from an AI session, Planning tags the first copy
   ``mixed_comparison_group_and_regional_database`` and the second
   ``comparison_group_premise_book``, so the warning fired again after the user
   had done exactly what it asked.
2. The warning did not say HOW to align the prices, although tab 7 exists to
   do it.

This module decides which of three states applies and lists, per Project, the
cost items whose price did NOT come from the premise book, with their origin.
It never changes a value.  No tkinter import, so it is testable headless.
"""
from __future__ import annotations

from typing import Any

from comparison.extractor import _saved_module

COPY_SCHEMA = "AZRAS_COMPARISON_COPY_V1"
PREMISE_BOOK_TOKENS = {"comparison_group_premise_book", "mixed_comparison_group_and_regional_database"}

UNIFORM = "uniform"
PREMISE_BOOK_ALIGNED = "premise_book_aligned"
MISALIGNED = "misaligned"


PRICE_TABLE_TOKENS = {"regional_unit_price_table", "regional_unit_price_table_with_ai_items",
                      "mixed_regional_unit_price_table_and_regional_database"}


def line_origin(status: Any) -> str:
    """Same classification as 01 Planning _price_basis_fingerprint."""
    s = str(status or "unresolved")
    if s.startswith("comparison_group"):
        return "premise_book"
    if s.startswith("regional_price_table"):
        return "price_table"
    if s.startswith("ai_"):
        return "ai"
    return "regional"


def _table_ref(raw: dict[str, Any]) -> dict[str, Any] | None:
    fp = (_saved_module(raw, "module5") or {}).get("price_basis_fingerprint") or {}
    ref = fp.get("regional_unit_price_table") if isinstance(fp, dict) else None
    return ref if isinstance(ref, dict) and ref.get("region_key") else None


def _line_rate(line: dict[str, Any]) -> float | None:
    try:
        return float(line.get("material_unit_cost") or 0) + float(line.get("labor_unit_cost") or 0) + float(line.get("equipment_unit_cost") or 0)
    except (TypeError, ValueError):
        return None


def price_table_check(projects: list[dict[str, Any]]) -> dict[str, Any]:
    """PATCH_010: Projects priced from the 01 Planning regional unit-price table.

    Within one region every Project must use the same table version, and the
    same table entry (item + spec + unit + scale class) must carry the same
    price.  Different regions legitimately use different tables, and a
    different scale class legitimately gives a different price: neither is a
    conflict.  Only reads; never changes a value.
    """
    refs: dict[str, dict[str, Any]] = {}
    for x in projects:
        ref = _table_ref(x.get("raw") or {})
        if ref:
            refs[x.get("label")] = ref
    versions: dict[str, dict[str, list[str]]] = {}
    for lab, ref in refs.items():
        versions.setdefault(str(ref.get("region_key")), {}).setdefault(str(ref.get("version")), []).append(lab)
    version_conflicts = {r: v for r, v in versions.items() if len(v) > 1}
    prices: dict[tuple[str, str, str], dict[str, float]] = {}
    for x in projects:
        lab = x.get("label")
        ref = refs.get(lab)
        if not ref:
            continue
        m5 = _saved_module(x.get("raw") or {}, "module5") or {}
        for line in m5.get("cost_lines") or []:
            if not isinstance(line, dict) or line_origin(line.get("pricing_status")) != "price_table":
                continue
            meta = line.get("regional_unit_cost_metadata") or {}
            ek = str(meta.get("regional_price_table_entry") or "") if isinstance(meta, dict) else ""
            rate = _line_rate(line)
            if ek and rate is not None:
                prices.setdefault((str(ref.get("region_key")), str(ref.get("version")), ek), {})[lab] = rate
    price_conflicts = []
    for (region, version, ek), by_lab in sorted(prices.items()):
        vals = list(by_lab.values())
        if len(vals) > 1 and max(vals) - min(vals) > max(abs(max(vals)), 1.0) * 1e-6:
            price_conflicts.append({"region_key": region, "version": version, "entry_key": ek,
                                    "cost_item_key": ek.split("|", 1)[0], "prices": by_lab})
    scale = {lab: ref.get("scale_class") for lab, ref in refs.items()}
    return {
        "refs": refs,
        "version_conflicts": version_conflicts,
        "price_conflicts": price_conflicts,
        "scale_classes": scale,
        "mixed_scale_classes": len({v for v in scale.values()}) > 1,
        "projects_without_table": [x.get("label") for x in projects if x.get("label") not in refs],
    }


def own_price_lines(raw: dict[str, Any]) -> list[dict[str, Any]]:
    """Cost lines of one Project whose price is NOT from a premise book."""
    # Same current-only rule as the extractor: an unsaved/legacy module5 is
    # not a price basis and must not produce a note either.
    m5 = _saved_module(raw, "module5") or {}
    out = []
    for line in m5.get("cost_lines") or []:
        if not isinstance(line, dict):
            continue
        origin = line_origin(line.get("pricing_status"))
        if origin == "premise_book":
            continue
        out.append({"key": str(line.get("cost_item_key") or ""), "origin": origin})
    return out


def _copy_version(raw: dict[str, Any]) -> str | None:
    cc = raw.get("comparison_copy")
    if isinstance(cc, dict) and cc.get("schema") == COPY_SCHEMA:
        return str(cc.get("premise_book_version") or "")
    return None


def assess(projects: list[dict[str, Any]]) -> dict[str, Any]:
    """``projects``: extractor records (need 'price_basis_token', 'label', 'raw').

    Returns {"status", "groups", "premise_book_version", "regional_items",
    "own_price_items", "mixed_own_origins"}.
      uniform              one basis token for every Project: no warning.
      premise_book_aligned every Project is a recalculated copy of ONE premise
                           book and differs only in the origin of the items the
                           book leaves to each Project: information, not a
                           warning.
      misaligned           anything else: the PATCH_003 warning, now with the
                           tab 7 procedure.
    """
    groups: dict[str, list[str]] = {}
    for x in projects:
        groups.setdefault(str(x.get("price_basis_token") or "unknown"), []).append(x.get("label"))
    own = {x.get("label"): own_price_lines(x.get("raw") or {}) for x in projects}
    regional = {lab: sorted({ln["key"] for ln in lines if ln["origin"] == "regional" and ln["key"]})
                for lab, lines in own.items()}
    origins = {ln["origin"] for lines in own.values() for ln in lines}
    versions = {_copy_version(x.get("raw") or {}) for x in projects}
    all_copies = bool(projects) and None not in versions
    one_book = all_copies and len(versions) == 1 and "" not in versions
    fp_ok = True
    for x in projects:
        raw = x.get("raw") or {}
        fp = (_saved_module(raw, "module5") or {}).get("price_basis_fingerprint") or {}
        fv = fp.get("premise_book_version") if isinstance(fp, dict) else None
        if fv not in (None, _copy_version(raw)):
            fp_ok = False
    table = price_table_check(projects)
    table_conflict = bool(table["version_conflicts"] or table["price_conflicts"])
    if table_conflict:
        # PATCH_010: one token for everyone does not help when the regional
        # table versions or prices differ.
        status = MISALIGNED
    elif len(groups) <= 1:
        status = UNIFORM
    elif one_book and fp_ok and set(groups) <= PREMISE_BOOK_TOKENS:
        status = PREMISE_BOOK_ALIGNED
    else:
        status = MISALIGNED
    return {
        "status": status,
        "groups": groups,
        "premise_book_version": next(iter(versions)) if one_book else None,
        "regional_items": regional,
        "own_price_items": {lab: sorted({ln["key"] for ln in lines if ln["key"]}) for lab, lines in own.items()},
        "mixed_own_origins": len(origins) > 1,
        "price_table_items": {lab: sorted({ln["key"] for ln in lines if ln["origin"] == "price_table" and ln["key"]})
                              for lab, lines in own.items()},
        "price_table": table,
        "price_table_conflict": table_conflict,
    }
