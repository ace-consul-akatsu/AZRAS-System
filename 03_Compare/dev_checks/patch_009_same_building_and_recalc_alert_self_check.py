# -*- coding: utf-8 -*-
"""PATCH_009 self-check (03 Compare): same-building check and persistent alert.

Real case: the AZRAS terrace-house Project carried 37.6 m2 of floor area
(Module 1 read a per-unit finish-area note) against 245.1 m2 for the 2x6 and
RC Projects of the same building, and the comparison copies were loaded
before Modules 5/6/7 were recalculated.  The only warning was a dismissable
popup, so the investment graphs looked like a valid comparison.

This check fails when:
  1. building_rows() misses a >3 % floor-area difference, reports a <=3 %
     one, or misses a storey / dwelling-unit difference;
  2. a building-size row does not block the premise book until decided, or a
     decision of either kind does not clear it;
  3. the persistent alert above the tabs does not show (in Japanese and in
     English) for copies that are not recalculated and for different-sized
     copies, or stays after the problem is gone / after "New";
  4. ordinary (non-copy) comparisons of different-sized buildings get an alert.

Run: python dev_checks/patch_009_same_building_and_recalc_alert_self_check.py
"""
import ast, copy, json, os, sys, tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from comparison import premise_book as PB  # noqa: E402

FAIL = []


def check(ok, label, detail=""):
    print(("  [OK]   " if ok else "  [NG]   ") + label + ("" if ok else f" :: {detail}"))
    if not ok:
        FAIL.append(label)


def proj(name, gfa, storeys=2, units=3, copy_pending=False):
    p = {"project_id": "id-" + name,
         "common": {"project_name": name, "scale_gfa_m2": gfa, "project_location": "愛知県春日井市"},
         "module_outputs": {
             "module1": {"drawing_analysis": {"profile": {"geometry": {"floor_area_m2": gfa, "footprint_m2": 122.55,
                                                                          "storeys": storeys}}}},
             "module5": {"currency": "JPY", "summary": {"total_construction_cost": 5e7}, "cost_lines": []},
             "module6": {"_input_snapshot": {"settings": {"total_dwelling_units": units,
                                                          "rent_setting_method": "market_rent",
                                                          "annual_rent_per_m2": 15000.0}}}}}
    if copy_pending:
        p["comparison_copy"] = {"schema": PB.COPY_SCHEMA, "premise_book_version": "v1",
                                "source_project_path": "", "source_sha256": ""}
        p["module_status"] = {m: {"status": "recalculation_pending"} for m in PB.COPY_ALLOWED_MODULES}
    return p


# 1. rows
rows = PB.building_rows([proj("2x6", 245.1), proj("AZRAS", 37.6), proj("RC", 245.1)])
check([r["row_id"] for r in rows] == ["building:gross_floor_area"], "37.6 vs 245.1 m2 reported", rows)
check(PB.building_rows([proj("a", 245.1), proj("b", 250.0)]) == [], "2.0 % difference not reported")
check([r["key"] for r in PB.building_rows([proj("a", 245.1), proj("b", 254.0)])] == ["gross_floor_area"],
      "3.6 % difference reported")
check([r["key"] for r in PB.building_rows([proj("a", 245.1, storeys=2), proj("b", 245.1, storeys=3)])] == ["storeys"],
      "storey difference reported")
check([r["key"] for r in PB.building_rows([proj("a", 245.1, units=3), proj("b", 245.1, units=2)])] == ["dwelling_units"],
      "dwelling-unit difference reported")

# 2. premise book gate
ps = [proj("2x6", 245.1), proj("AZRAS", 37.6)]
L = PB.build_lists(ps, PB.load_classification())
D = PB.default_decisions(L)
check("scope_undecided:gross_floor_area" in PB.validate_decisions(L, D), "undecided size row blocks the premise book")
for dec in ("accept_method_difference", "fix_source_quantity"):
    D2 = copy.deepcopy(D)
    D2["scope"]["building:gross_floor_area"] = {"decision": dec, "note": ""}
    check("scope_undecided:gross_floor_area" not in PB.validate_decisions(L, D2), f"decision {dec} clears it")

# 3./4. persistent alert
try:
    import tkinter as tk
    from tkinter import messagebox
    tk.Tk().destroy()
except Exception as exc:  # noqa: BLE001
    print(f"  [SKIP] no Tk display ({exc.__class__.__name__}); alert test skipped")
    tk = None
if tk is not None:
    for n in ("showwarning", "showinfo", "showerror"):
        setattr(messagebox, n, lambda *a, **k: None)
    os.chdir(ROOT)
    import main
    app = main.App(); app.update()
    tmp = Path(tempfile.mkdtemp())

    def load(*projects):
        app.clear()
        for i, p in enumerate(projects):
            f = tmp / f"p{i}.json"
            f.write_text(json.dumps(p, ensure_ascii=False), encoding="utf-8")
            app.paths[i].set(str(f))
        app.compare(); app.update()
        return app.alert_label.cget("text"), bool(app.alert_label.winfo_manager())

    app.language_var.set("日本語"); app._change_language()
    text, shown = load(proj("2x6", 245.1, copy_pending=True), proj("AZRAS", 37.6, copy_pending=True))
    check(shown and "再計算されていません" in text and "建物規模が一致しません" in text,
          "Japanese alert shows both problems", text)
    app.language_var.set("English"); app._change_language(); app.update()
    text = app.alert_label.cget("text")
    check("not recalculated" in text and "Building size differs" in text, "English alert after language switch", text)
    app.clear(); app.update()
    check(app.alert_label.cget("text") == "" and not app.alert_label.winfo_manager(), "New clears the alert")
    ok = [proj("2x6", 245.1, copy_pending=True), proj("RC", 245.1, copy_pending=True)]
    for p in ok:
        p["module_status"] = {m: {"status": "saved"} for m in PB.COPY_ALLOWED_MODULES}
    text, shown = load(*ok)
    check(not shown and text == "", "no alert for recalculated same-size copies", text)
    text, shown = load(proj("small", 100.0), proj("large", 300.0))
    check(not shown, "no alert for an ordinary comparison of different buildings", text)
    app.destroy()

if FAIL:
    print(f"PATCH_009 SAME BUILDING / RECALC ALERT: {len(FAIL)} FAILED")
    sys.exit(1)
print("PATCH_009 SAME BUILDING / RECALC ALERT: PASS")
