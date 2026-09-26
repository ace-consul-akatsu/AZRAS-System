# -*- coding: utf-8 -*-
"""Connections between the products (each product runs in its own process).

1. Project JSON hand-off: a Project saved by 01 Planning is loaded and
   validated by 02 Evaluation, read by 03 Compare, and validates against
   schemas/project_schema_v3_0.json.
2. Market-rent contract: the module6 result 02 Evaluation calculates in
   market-rent mode is read by 03 Compare as "no active target yield", with
   the user's preference kept only as the stored value.
3. Launcher: 00 Installer's launcher opens 01_Planning, 02_Evaluation and
   03_Compare from this repository layout.

Run from the repository root:  python tests/check_cross_product.py
"""
import json
import subprocess
import sys
import tempfile
import textwrap
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
FAIL = []


def run_in(product, code, *args):
    """Run code inside a product folder; returns the JSON it prints last."""
    prog = "import sys, json\nsys.path.insert(0, '.')\n" + textwrap.dedent(code)
    r = subprocess.run([sys.executable, "-c", prog, *map(str, args)], cwd=REPO / product,
                       capture_output=True, text=True, encoding="utf-8", timeout=600)
    if r.returncode != 0:
        raise RuntimeError(f"{product}: {r.stderr.strip().splitlines()[-1] if r.stderr.strip() else r.returncode}")
    return json.loads(r.stdout.strip().splitlines()[-1])


def check(ok, label, detail=""):
    print(f"  [{'OK' if ok else 'NG'}]   {label}" + ("" if ok else f" :: {detail}"))
    if not ok:
        FAIL.append(label)


with tempfile.TemporaryDirectory() as td:
    td = Path(td)
    print("-- 1. Project JSON hand-off: Planning -> Evaluation -> Compare")
    try:
        saved = td / "handoff.json"
        info = run_in("01_Planning", """
            from core import project_store as PS
            p = PS.new_project()
            p["common"]["project_name"] = "cross-product check"
            PS.save_project(p, sys.argv[1], create_backup=False)
            print(json.dumps({"schema_version": p.get("schema_version")}))
        """, saved)
        check(info["schema_version"] == "3.0", "Planning saves schema 3.0", info)
        ev = run_in("02_Evaluation", """
            from core import project_store as PS
            d = PS.load_project(sys.argv[1])
            print(json.dumps({"errors": PS.validate_project(d), "name": d["common"].get("project_name")}))
        """, saved)
        check(not ev["errors"] and ev["name"] == "cross-product check", "Evaluation loads and validates it", ev)
        cp = run_in("03_Compare", """
            from comparison.extractor import extract_core_project
            r = extract_core_project(sys.argv[1])
            print(json.dumps({"ok": isinstance(r, dict)}))
        """, saved)
        check(cp["ok"], "Compare reads it")
        schema = json.loads((REPO / "schemas" / "project_schema_v3_0.json").read_text(encoding="utf-8"))
        data = json.loads(saved.read_text(encoding="utf-8"))
        missing = [k for k in schema["required"] if k not in data]
        check(not missing and data.get("schema_version") == schema["properties"]["schema_version"]["const"],
              "the saved file matches schemas/project_schema_v3_0.json (required keys, schema_version)", missing)
        try:
            import jsonschema
            errs = [e.message for e in jsonschema.Draft202012Validator(schema).iter_errors(data)]
            check(not errs, "full JSON Schema validation", errs[:3])
        except ImportError:
            print("  [--]   jsonschema not installed: full JSON Schema validation not run")
    except Exception as exc:  # noqa: BLE001
        check(False, "Project JSON hand-off ran", exc)

    print("-- 2. Market-rent contract: Evaluation -> Compare")
    try:
        project = td / "market_rent.json"
        run_in("02_Evaluation", """
            from services.investment_engine_v9_5 import calculate_investment
            timeline = [{"year": y, "annual_cost": 0.0, "cumulative_cost": 0.0} for y in range(1, 201)]
            proj = {"project_id": "x", "common": {"project_name": "market rent", "scale_gfa_m2": 100.0,
                    "unit_count": 1, "construction_method_id": "rc_frame"},
                    "module_outputs": {"module5": {"currency": "JPY", "summary": {"subtotal_before_tax": 1e8,
                        "tax_amount": 0.0, "total_construction_cost": 1e8}},
                        "module7": {"annual_cost_timeline": timeline, "summary": {"total_lifecycle_work_cost": 0}},
                        "module3": {"timeline": []}}}
            s = {"rent_setting_method": "market_rent", "annual_rent_per_m2": 30000.0,
                 "target_gross_yield_percent": 6.5, "target_gross_yield_active": False,
                 "vacancy_rate_percent": 5.0, "operating_expense_rate_percent": 10.0,
                 "routine_maintenance_rate_percent": 0.0, "insurance_rate_percent": 0.0,
                 "discount_rate_percent": 4.0, "rent_growth_rate_percent": 0.0,
                 "construction_cost_escalation_percent": 0.0, "general_inflation_percent": 0.0,
                 "terminal_cap_rate_percent": 5.0, "sale_cost_rate_percent": 0.0, "use_loan": False}
            m6 = calculate_investment(proj, dict(s))
            m6["_input_snapshot"] = {"settings": s}
            m6["_meta"] = {"status": "saved", "is_current": True}
            proj["module_outputs"]["module6"] = m6
            open(sys.argv[1], "w", encoding="utf-8").write(json.dumps(proj, default=str))
            print(json.dumps({"ok": True}))
        """, project)
        r = run_in("03_Compare", """
            from comparison.extractor import extract_core_project
            r = extract_core_project(sys.argv[1])
            keys = ("rent_setting_method", "target_gross_yield_percent", "target_gross_yield_active",
                    "stored_target_gross_yield_percent")
            print(json.dumps({k: r.get(k) for k in keys}))
        """, project)
        check(r["rent_setting_method"] == "market_rent", "Compare sees market rent", r)
        check(r["target_gross_yield_percent"] is None and r["target_gross_yield_active"] is False,
              "no active target yield in market-rent mode", r)
        check(r["stored_target_gross_yield_percent"] == 6.5, "the user's 6.5 % is kept as the stored value", r)
    except Exception as exc:  # noqa: BLE001
        check(False, "market-rent contract ran", exc)

print("-- 3. Launcher opens the products of this repository")
try:
    got = run_in("00_Installer", """
        import azras_launcher as L
        out = {}
        for key, name, prefixes, bats in L.PRODUCT_SPECS:
            e = L.resolve_product(prefixes, bats)
            out[key] = e.parent.name if e else None
        print(json.dumps(out))
    """)
    check(got == {"P": "01_Planning", "E": "02_Evaluation", "C": "03_Compare"}, "launcher targets", got)
except Exception as exc:  # noqa: BLE001
    check(False, "launcher check ran", exc)

print("CHECK_CROSS_PRODUCT_" + ("FAIL" if FAIL else "PASS"))
sys.exit(1 if FAIL else 0)
