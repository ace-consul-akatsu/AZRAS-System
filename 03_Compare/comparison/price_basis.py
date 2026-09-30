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


def line_origin(status: Any) -> str:
    """Same classification as 01 Planning _price_basis_fingerprint."""
    s = str(status or "unresolved")
    if s.startswith("comparison_group"):
        return "premise_book"
    if s.startswith("ai_"):
        return "ai"
    return "regional"


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
    if len(groups) <= 1:
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
    }
