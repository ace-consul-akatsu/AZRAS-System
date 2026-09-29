"""PATCH_011: shared CSV writer for result tables (list of dicts).

The header is the union of the keys of ALL rows, in first-seen order, instead
of the keys of the first row only. Module 4's annual CSV failed with
"dict contains fields not in fieldnames" because its first row (year 0) lacked
three climate columns that the yearly rows have. Project JSON files saved
before PATCH_011 still hold such year-0 rows, so the union header is kept even
though the engine now writes those columns in every row. A row missing a
column gets an empty cell. No column is ever dropped.
"""
from __future__ import annotations

import csv
from pathlib import Path
from typing import Any, Iterable, Mapping


def union_fieldnames(rows: Iterable[Mapping[str, Any]]) -> list[str]:
    fields: dict[str, None] = {}
    for row in rows:
        for key in row.keys():
            fields.setdefault(key, None)
    return list(fields)


def write_dict_rows_csv(path: str | Path, rows: list[Mapping[str, Any]]) -> list[str]:
    """Write rows to a UTF-8 (BOM) CSV; returns the header that was written."""
    fields = union_fieldnames(rows)
    with open(path, "w", newline="", encoding="utf-8-sig") as file:
        writer = csv.DictWriter(file, fieldnames=fields, restval="")
        writer.writeheader()
        writer.writerows(rows)
    return fields
