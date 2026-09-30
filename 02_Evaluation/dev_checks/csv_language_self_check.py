# -*- coding: utf-8 -*-
"""CSV language self-check (01_Planning PATCH_049 / 02_Evaluation PATCH_014).

CSV files follow the UI language when saved.  This check fails when:
  1. a column that a result CSV of this product can write has no Japanese
     header in lang/csv_ja.json (it would appear in English in a Japanese CSV);
  2. two columns of the same CSV get the same Japanese header;
  3. English output of core.csv_export.write_dict_rows_csv changes (header
     must stay the internal key; cells unchanged);
  4. Japanese output translates a number, drops an unknown column, or fails to
     translate a code value listed in value_columns;
  5. a localizer that raises breaks the export instead of keeping the value;
  6. (Planning only) the 8760 comparison CSV reload no longer accepts the
     Japanese header written by the save function.

Run: python dev_checks/csv_language_self_check.py
"""
from __future__ import annotations

import ast
import csv
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.csv_export import (  # noqa: E402
    header_label, missing_header_translations, write_dict_rows_csv,
)

errors: list[str] = []


def dict_literal_keys(rel: str, must: tuple[str, ...]) -> list[str]:
    path = ROOT / rel
    tree = ast.parse(path.read_text(encoding="utf-8"))
    keys: dict[str, None] = {}
    found = False
    for node in ast.walk(tree):
        if isinstance(node, ast.Dict):
            ks = [k.value for k in node.keys
                  if isinstance(k, ast.Constant) and isinstance(k.value, str)]
            if all(m in ks for m in must):
                found = True
                for k in ks:
                    keys.setdefault(k, None)
    if not found:
        errors.append(f"{rel}: row literal with {must} not found (check needs updating)")
    return list(keys)


PRODUCT = "planning" if (ROOT / "module1").exists() else "evaluation"
csv_sets: dict[str, list[str]] = {}

if PRODUCT == "planning":
    text = (ROOT / "module1/app.py").read_text(encoding="utf-8")
    seg = text[text.index("    def save_detailed_quantity_csv(self):"):]
    csv_sets["Module 1 detailed quantity"] = list(ast.literal_eval(
        seg[seg.index("fields=[") + 7: seg.index("]", seg.index("fields=[")) + 1]))
    cost = dict_literal_keys("services/construction_cost_engine_v9_4.py",
                             ("cost_item_key", "line_total_after_conditions"))
    csv_sets["Module 5 construction cost"] = list(dict.fromkeys(cost + [
        "currency", "record_type", "item_name", "item", "quantity_source", "quantity_basis"]))
    text10 = (ROOT / "regional_analysis/module10_ui.py").read_text(encoding="utf-8")
    seg10 = text10[text10.index("    def save_hourly_csv(self):"):]
    csv_sets["Module 10 selected-hour regional"] = list(ast.literal_eval(
        seg10[seg10.index("fields = [") + 9: seg10.index("]", seg10.index("fields = [")) + 1]))
    csv_sets["Module 2 8760 comparison"] = ["metric", "baseline", "alternative", "delta", "delta_percent"]
else:
    text3 = (ROOT / "module3/app.py").read_text(encoding="utf-8")
    seg3 = text3[text3.index("    def save_csv(self):"):]
    csv_sets["Module 3 timeline"] = list(ast.literal_eval(
        seg3[seg3.index("fields=[") + 7: seg3.index("]", seg3.index("fields=[")) + 1]))
    csv_sets["Module 4 annual"] = dict_literal_keys(
        "services/long_term_environment_engine_v9_3.py",
        ("operational_energy_MJ", "net_co2_kg")) + ["cumulative_co2_kg", "cumulative_energy_MJ"]
    csv_sets["Module 4 events"] = dict_literal_keys(
        "services/long_term_environment_engine_v9_3.py", ("event_id", "co2_event_semantics"))
    csv_sets["Module 6 cashflow"] = dict_literal_keys(
        "services/investment_engine_v9_5.py", ("noi", "loan_balance"))
    csv_sets["Module 7 event costs"] = dict_literal_keys(
        "services/repair_demolition_cost_engine_v9_6.py", ("event_id", "work_cost"))

# 1 + 2: Japanese header coverage and uniqueness
for name, keys in csv_sets.items():
    if not keys:
        errors.append(f"{name}: no columns found")
        continue
    missing = missing_header_translations(keys, "ja")
    if missing:
        errors.append(f"{name}: no Japanese header for {missing}")
    labels = [header_label(k, "ja") for k in keys]
    dup = sorted({x for x in labels if labels.count(x) > 1})
    if dup:
        errors.append(f"{name}: duplicate Japanese headers {dup}")
    print(f"[info] {name}: {len(keys)} columns")

table = json.loads((ROOT / "lang" / "csv_ja.json").read_text(encoding="utf-8"))
code = next(iter(table["values"]))

# 3-5: helper behaviour
rows = [{"year": 1, "amount": 1234.5, "code": code, "unknown_key_xyz": "keep", "bad": "x"}]
with tempfile.TemporaryDirectory() as tmp:
    en = Path(tmp) / "en.csv"
    write_dict_rows_csv(en, rows, "en", value_columns=("code",))
    with en.open(encoding="utf-8-sig", newline="") as f:
        read = list(csv.reader(f))
    if read[0] != ["year", "amount", "code", "unknown_key_xyz", "bad"]:
        errors.append(f"English header changed: {read[0]}")
    if read[1] != ["1", "1234.5", code, "keep", "x"]:
        errors.append(f"English cells changed: {read[1]}")

    ja = Path(tmp) / "ja.csv"

    def boom(_v, _row):
        raise RuntimeError("localizer failure")

    write_dict_rows_csv(ja, rows, "ja", value_columns=("code",), localizers={"bad": boom})
    with ja.open(encoding="utf-8-sig", newline="") as f:
        read = list(csv.reader(f))
    if read[1][1] != "1234.5" or read[1][0] != "1":
        errors.append(f"Japanese CSV changed a number: {read[1]}")
    if read[1][2] != table["values"][code]:
        errors.append(f"Japanese CSV did not translate code {code!r}: {read[1][2]!r}")
    if read[0][3] != "unknown_key_xyz" or read[1][3] != "keep":
        errors.append("Japanese CSV dropped or blanked an untranslated column")
    if read[1][4] != "x":
        errors.append("a failing localizer did not keep the original value")
    if header_label("year", "ja") == "year" and "year" in table["headers"]:
        errors.append("header_label ignored the Japanese table")

# 6: Planning 8760 reload accepts the Japanese header
if PRODUCT == "planning":
    src = (ROOT / "module2/app.py").read_text(encoding="utf-8")
    if '("metric", "指標")' not in src:
        errors.append("Module 2 8760 CSV reload does not accept the Japanese header 指標")
    if header_label("metric", "ja") != "指標":
        errors.append("8760 comparison header 'metric' is not 指標 (reload would treat it as data)")

if errors:
    for e in errors:
        print("[NG]", e)
    sys.exit(1)
print("[OK] every result-CSV column has a unique Japanese header")
print("[OK] English CSV output unchanged; Japanese output keeps numbers and unknown columns")
sys.exit(0)
