# -*- coding: utf-8 -*-
"""PATCH_011: result-table CSV export must never fail on uneven row keys.

Module 4's annual CSV raised ValueError "dict contains fields not in
fieldnames: 'climate_temperature_offset_C', 'operational_change_factor',
'climate_energy_factor'" because the header came from the first row (year 0)
and that row lacked the three climate columns.

This check fails when:
  1. any module/core file builds a csv.DictWriter header from the first row
     only (fieldnames=list(rows[0]...) / rows[0].keys());
  2. core.csv_export.write_dict_rows_csv drops a column or fails on rows whose
     keys differ (old saved Project JSONs still have short year-0 rows);
  3. the Module 4 engine year-0 row lacks a column that the yearly rows have;
  4. a real Module 4 annual timeline cannot be exported with the 3 columns.

Run: python dev_checks/csv_export_fieldnames_self_check.py
"""
import ast
import csv
import re
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

errors = []
CLIMATE = ["climate_temperature_offset_C", "operational_change_factor", "climate_energy_factor"]

# 1. static: no first-row-only headers
pattern = re.compile(r"DictWriter\([^)]*fieldnames\s*=\s*(list\()?\s*rows\[0\]")
for path in sorted(ROOT.rglob("*.py")):
    if "archive" in path.parts or "dev_checks" in path.parts:
        continue
    text = path.read_text(encoding="utf-8", errors="replace")
    for n, line in enumerate(text.splitlines(), 1):
        if pattern.search(line):
            errors.append(f"{path.relative_to(ROOT)}:{n}: header built from rows[0] only")

# 2. helper behaviour on uneven rows
from core.csv_export import write_dict_rows_csv, union_fieldnames
rows = [{"year": 0, "a": 1}, {"year": 1, "a": 2, **{k: 1.0 for k in CLIMATE}}]
with tempfile.TemporaryDirectory() as tmp:
    out = Path(tmp) / "t.csv"
    try:
        header = write_dict_rows_csv(out, rows)
        with out.open(encoding="utf-8-sig", newline="") as f:
            read = list(csv.DictReader(f))
        if header != ["year", "a"] + CLIMATE:
            errors.append(f"union header wrong/unstable order: {header}")
        if len(read) != 2 or read[0][CLIMATE[0]] != "" or read[1][CLIMATE[2]] != "1.0":
            errors.append("helper wrote wrong cells for uneven rows")
    except Exception as exc:  # noqa: BLE001
        errors.append(f"write_dict_rows_csv failed on uneven rows: {exc!r}")
if union_fieldnames([]) != []:
    errors.append("union_fieldnames([]) must be []")

# 3. engine source: year-0 literal has every yearly column
eng = (ROOT / "services" / "long_term_environment_engine_v9_3.py").read_text(encoding="utf-8")
tree = ast.parse(eng)
dict_keys = []
for node in ast.walk(tree):
    if isinstance(node, ast.Dict):
        keys = [k.value for k in node.keys if isinstance(k, ast.Constant)]
        if "operational_energy_MJ" in keys and "net_co2_kg" in keys:
            dict_keys.append(keys)
if len(dict_keys) < 2:
    errors.append("could not find the year-0 and yearly annual row literals")
else:
    first, *others = dict_keys
    for other in others:
        missing = [k for k in other if k not in first]
        if missing:
            errors.append(f"year-0 annual row lacks yearly columns: {missing}")

# 4. runtime: engine annual timeline -> CSV (synthetic minimal Project)
try:
    import json
    from services.long_term_environment_engine_v9_3 import evaluate_long_term_environment
    factors = json.loads((ROOT / "data" / "environmental_lca_factors_v9_3.json").read_text(encoding="utf-8"))
    project = {"common": {"scale_gfa_m2": 245.1}, "module_outputs": {
        "module1": {"quantity_takeoff": {"rows": []}},
        "module2": {"operational_CO2_kg_per_year": 8000.0, "primary_energy_MJ_per_year": 150000.0,
                    "total_building_electricity_kWh_per_year": 15000.0, "settings": {"electricity_co2": 0.45}},
        "module3": {"events": [{"year": 30, "action": "renew", "component_key": "windows",
                                "component": "windows", "scope": 1.0}]}}}
    result = evaluate_long_term_environment(project, factors, operational_change_pct=0.5)
    annual = result["annual_timeline"]
    for key in CLIMATE:
        if key not in annual[0]:
            errors.append(f"engine year-0 row lacks {key}")
    with tempfile.TemporaryDirectory() as tmp:
        header = write_dict_rows_csv(Path(tmp) / "annual.csv", annual)
        for key in CLIMATE:
            if key not in header:
                errors.append(f"annual CSV header lacks {key}")
        if result.get("event_impacts"):
            write_dict_rows_csv(Path(tmp) / "events.csv", result["event_impacts"])
except Exception as exc:  # noqa: BLE001
    errors.append(f"runtime annual CSV export failed: {exc!r}")

if errors:
    print("[FAIL] csv_export_fieldnames")
    for e in errors:
        print("  -", e)
    sys.exit(1)
print("[PASS] csv_export_fieldnames: union header, year-0 row complete, no rows[0]-only headers")
