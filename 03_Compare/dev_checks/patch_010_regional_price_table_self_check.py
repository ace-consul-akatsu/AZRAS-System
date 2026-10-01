# -*- coding: utf-8 -*-
"""PATCH_010 self-check: regional unit-price table (01 Planning PATCH_052).

1. Projects of one region priced from the same table version and the same
   prices are uniform (no warning), also with different scale classes.
2. Two table versions in one region, or the same table entry with different
   prices, are a warning that names the versions / items and the procedure.
3. Different regions with different tables are not a conflict.
4. A table price is shown as "地域単価表" in the premise-book information.
5. (display available) the real App shows the warning with the table section.

Fingerprints mirror 01 Planning PATCH_052 _price_basis_fingerprint.
Run: python dev_checks/patch_010_regional_price_table_self_check.py
"""
import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from comparison import price_basis as PBASIS  # noqa: E402

FAIL = []


def check(ok, label, detail=""):
    if ok:
        print(f"  [OK]   {label}")
    else:
        FAIL.append(f"{label} :: {detail}")
        print(f"  [NG]   {label} :: {detail}")


RT = "regional_price_table_fixed"


def L(key, rate, scale, method="common"):
    return {"cost_item_key": key, "pricing_status": RT, "quantity": 10.0, "unit": "m3",
            "material_unit_cost": rate, "labor_unit_cost": 0.0, "equipment_unit_cost": 0.0,
            "regional_unit_cost_metadata": {"regional_price_table_entry": f"{key}|{method}|m3|{scale}"}}


def raw(name, lines, region="Japan / Nagoya", version="2026-10", scale="S"):
    p = {"project_id": name,
         "common": {"project_name": name, "construction_method_id": "wood_frame", "project_location": "Kasugai", "currency": "JPY"},
         "module_outputs": {"module5": {"_meta": {"status": "saved"}, "currency": "JPY", "cost_lines": lines}}}
    p["module_outputs"]["module5"]["price_basis_fingerprint"] = {
        "basis_token": "regional_unit_price_table",
        "regional_unit_price_table": {"region_key": region, "version": version, "sha256": "x", "scale_class": scale,
                                      "table_file": "AZRAS_UNIT_PRICE_TABLE_x.json", "currency": "JPY"}}
    return p


def rec(p):
    fp = p["module_outputs"]["module5"]["price_basis_fingerprint"]
    return {"label": p["common"]["project_name"], "price_basis_token": fp["basis_token"], "raw": p}


a = raw("A", [L("xps", 41500.0, "S"), L("glass", 9000.0, "S")])
b = raw("B", [L("xps", 41500.0, "S")])
big = raw("BIG", [L("xps", 39000.0, "M")], scale="M")
old_ver = raw("OLD", [L("xps", 41500.0, "S")], version="2026-07")
edited = raw("EDIT", [L("xps", 50000.0, "S")])
tokyo = raw("TOKYO", [L("xps", 52000.0, "S")], region="Japan / Tokyo", version="2026-08")

print("PATCH_010 self-check")
r = PBASIS.assess([rec(a), rec(b)])
check(r["status"] == PBASIS.UNIFORM and not r["price_table_conflict"], "same table, same prices: uniform", r["status"])
r = PBASIS.assess([rec(a), rec(big)])
check(r["status"] == PBASIS.UNIFORM and r["price_table"]["mixed_scale_classes"], "different scale class is not a conflict", r)
r = PBASIS.assess([rec(a), rec(old_ver)])
check(r["status"] == PBASIS.MISALIGNED and "Japan / Nagoya" in r["price_table"]["version_conflicts"], "two versions in one region warn", r["price_table"])
r = PBASIS.assess([rec(a), rec(edited)])
pc = r["price_table"]["price_conflicts"]
check(r["status"] == PBASIS.MISALIGNED and len(pc) == 1 and pc[0]["cost_item_key"] == "xps", "same entry, different price warns", pc)
r = PBASIS.assess([rec(a), rec(tokyo)])
check(r["status"] == PBASIS.UNIFORM and not r["price_table_conflict"], "different regions are not a conflict", r["price_table"])
check(PBASIS.line_origin(RT) == "price_table" and PBASIS.line_origin("ai_primary_basis_provisional") == "ai", "line origin of a table price")
r = PBASIS.assess([rec(a)])
check(r["price_table_items"]["A"] == ["glass", "xps"], "table items listed per Project", r["price_table_items"])

try:
    import tkinter as _tk
    _probe = _tk.Tk()
    _probe.destroy()
    have_display = True
except Exception as exc:  # noqa: BLE001
    have_display = False
    print(f"  [SKIP] no display: {str(exc)[:60]}")
if have_display:
    import main as M
    from tkinter import messagebox
    log = []
    saved = (messagebox.showwarning, messagebox.showinfo, messagebox.showerror)
    messagebox.showwarning = lambda t, m, **k: log.append(("warning", m))
    messagebox.showinfo = lambda t, m, **k: log.append(("info", m))
    messagebox.showerror = lambda t, m, **k: log.append(("error", m))
    tmp = tempfile.mkdtemp()

    def write(p):
        f = os.path.join(tmp, p["project_id"] + ".json")
        Path(f).write_text(json.dumps(p, ensure_ascii=False), encoding="utf-8")
        return f

    def run(projects, lang="ja"):
        log.clear()
        app = M.App()
        app.language = lang
        for i, p in enumerate(projects):
            app.paths[i].set(write(p))
        app.compare()
        app.update()
        out = list(log)
        app.destroy()
        return out

    try:
        res = run([a, old_ver])
        warn = [m for k, m in res if k == "warning" and "【地域単価表】" in m]
        check(len(warn) == 1 and "2026-07" in warn[0] and "地域単価表を適用" in warn[0], "App: version conflict warning", [k for k, _ in res])
        check(not [m for k, m in res if "【単価根拠の前提】" in m], "App: no duplicate generic price-basis warning when tokens agree")
        res = run([a, edited])
        check(any("【地域単価表】" in m and "50,000.00" in m for k, m in res), "App: price conflict lists the prices")
        res = run([a, b])
        check(not [m for k, m in res if "地域単価表】" in m or "単価根拠の前提" in m], "App: aligned table gives no warning")
        res = run([a, old_ver], "en")
        check(any("[Regional price table]" in m for k, m in res), "App: English warning")
    finally:
        messagebox.showwarning, messagebox.showinfo, messagebox.showerror = saved

print()
if FAIL:
    print("[NG] PATCH_010 self-check FAILED:")
    for f in FAIL:
        print("   -", f)
    raise SystemExit(1)
print("PATCH_010_REGIONAL_PRICE_TABLE_PASS")
