"""Shared CSV writer for result tables (list of dicts).

PATCH_011 (02_Evaluation): the header is the union of the keys of ALL rows,
in first-seen order, instead of the keys of the first row only. Module 4's
annual CSV failed with "dict contains fields not in fieldnames" because its
first row (year 0) lacked three climate columns that the yearly rows have.
A row missing a column gets an empty cell. No column is ever dropped.

v2.2.0 CSV language (01_Planning PATCH_049 / 02_Evaluation PATCH_014):
CSV files follow the UI language at the moment of saving.

* English (default): the header row is the internal English key, exactly as
  before, so existing English CSVs and any tool that reads them are unchanged.
* Japanese: the header row is translated with lang/csv_ja.json ("headers"),
  and cells of the columns named in ``value_columns`` are translated with
  "values" (e.g. action codes such as ``full_rebuild`` -> 全面建替え).
  Numbers are never translated or reformatted.  A key or code missing from the
  table is written unchanged in English (never blank), and
  dev_checks/csv_language_self_check.py fails when a column a product writes
  has no Japanese header.

Internal data (Project JSON, result dicts) stays English-canonical; only the
CSV presentation changes.  The row data passed in is never modified.
"""
from __future__ import annotations

import csv
import json
from functools import lru_cache
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping

_LANG_DIR = Path(__file__).resolve().parent.parent / "lang"
_TABLE_PATH_BY_LANGUAGE = {"ja": _LANG_DIR / "csv_ja.json"}

ValueLocalizer = Callable[[Any, Mapping[str, Any]], Any]


@lru_cache(maxsize=None)
def _table(language: str) -> dict[str, dict[str, str]]:
    path = _TABLE_PATH_BY_LANGUAGE.get(language)
    if path is None or not path.exists():
        return {"headers": {}, "values": {}}
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except Exception:
        return {"headers": {}, "values": {}}
    headers = data.get("headers") if isinstance(data, dict) else None
    values = data.get("values") if isinstance(data, dict) else None
    return {
        "headers": headers if isinstance(headers, dict) else {},
        "values": values if isinstance(values, dict) else {},
    }


def csv_language(language: str | None) -> str:
    """Normalise a UI language code to a CSV language ("ja" or "en")."""
    return "ja" if str(language or "").lower().startswith("ja") else "en"


def header_label(key: str, language: str | None) -> str:
    """Header text for one internal column key (English key if untranslated)."""
    if csv_language(language) == "en":
        return key
    return str(_table("ja")["headers"].get(key) or key)


def value_label(value: Any, language: str | None) -> Any:
    """Translate one code value (e.g. ``full_rebuild``); non-strings unchanged."""
    if csv_language(language) == "en" or not isinstance(value, str):
        return value
    return _table("ja")["values"].get(value, value)


def missing_header_translations(keys: Iterable[str], language: str = "ja") -> list[str]:
    """Keys that would be written in English in a ``language`` CSV header."""
    table = _table(csv_language(language))["headers"]
    return [key for key in keys if key not in table]


def union_fieldnames(rows: Iterable[Mapping[str, Any]]) -> list[str]:
    fields: dict[str, None] = {}
    for row in rows:
        for key in row.keys():
            fields.setdefault(key, None)
    return list(fields)


def write_dict_rows_csv(
    path: str | Path,
    rows: list[Mapping[str, Any]],
    language: str | None = "en",
    fields: list[str] | None = None,
    value_columns: Iterable[str] = (),
    localizers: Mapping[str, ValueLocalizer] | None = None,
) -> list[str]:
    """Write rows to a UTF-8 (BOM) CSV; returns the internal header keys.

    ``fields``       fixed column order; default is the union of all row keys.
    ``value_columns`` columns whose string codes are translated in Japanese.
    ``localizers``   {column: fn(value, row)} for columns that need a module's
                     own display logic (e.g. component names); applied only in
                     Japanese and before ``value_columns`` translation.
    """
    lang = csv_language(language)
    keys = list(fields) if fields is not None else union_fieldnames(rows)
    code_columns = set(value_columns)
    with open(path, "w", newline="", encoding="utf-8-sig") as file:
        writer = csv.writer(file)
        writer.writerow([header_label(key, lang) for key in keys])
        for row in rows:
            cells = []
            for key in keys:
                value = row.get(key, "")
                if value is None:
                    value = ""
                if lang == "ja":
                    if localizers and key in localizers:
                        try:
                            value = localizers[key](value, row)
                        except Exception:
                            pass
                    if key in code_columns:
                        value = value_label(value, lang)
                cells.append(value)
            writer.writerow(cells)
    return keys
