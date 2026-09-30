# -*- coding: utf-8 -*-
"""PATCH_008 self-check: price-basis check after the premise book.

1. Copies of ONE premise book whose method-dependent items keep different
   price origins (regional database in one, AI in another) are reported as
   aligned information, not as the PATCH_003 price-basis warning.
2. Originals with different bases, copies of two book versions and a copy
   whose Module 5 still carries the source basis stay a warning.
3. The warning names the tab 7 procedure and the regionally priced items.
4. Tab 7 shows every loaded building (2..7), not only buildings 1..3.
5. (display available) the real App shows a warning for the originals and an
   information dialog for the copies.

Fingerprint fixtures reproduce 01 Planning _price_basis_fingerprint
(PATCH_040/043); the tokens were confirmed against 01_Planning_48.

Run: python dev_checks/patch_008_price_basis_premise_book_self_check.py
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


AI = "ai_post_review_rechecked_provisional"
CG = "comparison_group_confirmed"
DB = "planning_city_initial_estimate_2026"


def planning_token(lines, is_copy):
    """Mirror of 01 Planning _price_basis_fingerprint basis_token."""
    st = [str(x.get("pricing_status") or "unresolved") for x in lines]
    total = len(st)
    ai = sum(1 for s in st if s.startswith("ai_"))
    cg = sum(1 for s in st if s.startswith("comparison_group"))
    if total <= 0:
        return "no_priced_lines"
    if cg > 0 and cg + ai >= total:
        return "comparison_group_premise_book"
    if cg > 0:
        return "mixed_comparison_group_and_regional_database"
    if ai >= total:
        return "ai_approximate_cost_session"
    if ai > 0:
        return "mixed_ai_and_regional_database"
    return "regional_cost_database"


def L(key, status):
    return {"cost_item_key": key, "pricing_status": status, "quantity": 10.0, "unit": "m3",
            "installed_all_in_unit_cost": 1000.0}


def raw(name, method, lines, version):
    p = {"project_id": name,
         "common": {"project_name": name, "construction_method_id": method,
                    "project_location": "Kasugai", "currency": "JPY"},
         "module_outputs": {"module5": {"_meta": {"status": "saved"}, "currency": "JPY", "cost_lines": lines}}}
    if version:
        p["comparison_copy"] = {"schema": "AZRAS_COMPARISON_COPY_V1", "premise_book_version": version,
                                "group_id": "G1", "premise_book_file": "PB.json",
                                "source_project_path": "/nonexistent/source.json"}
    p["module_outputs"]["module5"]["price_basis_fingerprint"] = {
        "basis_token": planning_token(lines, bool(version)),
        "premise_book_version": version}
    return p


def rec(p):
    fp = p["module_outputs"]["module5"]["price_basis_fingerprint"]
    return {"label": p["common"]["project_name"], "price_basis_token": fp["basis_token"], "raw": p}


orig_2x6 = raw("2x6", "wood_frame", [L("xps", AI), L("concrete", AI), L("dimension_lumber", AI)], None)
orig_az = raw("AZRAS", "azras", [L("xps", AI), L("concrete", DB), L("reinforcing_steel", DB)], None)
copy_2x6 = raw("2x6 [CMP]", "wood_frame", [L("xps", CG), L("concrete", AI), L("dimension_lumber", AI)], "v1")
copy_az = raw("AZRAS [CMP]", "azras", [L("xps", CG), L("concrete", DB), L("reinforcing_steel", DB)], "v1")
copy_rc = raw("RC [CMP]", "rc_frame", [L("xps", CG), L("concrete", DB), L("formwork", DB)], "v1")

print("PATCH_008 self-check")
print("-- 1. copies of one premise book")
r = PBASIS.assess([rec(copy_2x6), rec(copy_az), rec(copy_rc)])
check(len(r["groups"]) == 2, "the Planning tokens of the copies really differ (the PATCH_003 trigger)", r["groups"])
check(r["status"] == PBASIS.PREMISE_BOOK_ALIGNED, "copies of one book are premise-book aligned", r["status"])
check(r["premise_book_version"] == "v1", "the book version is reported", r["premise_book_version"])
check(r["regional_items"]["AZRAS [CMP]"] == ["concrete", "reinforcing_steel"]
      and r["regional_items"]["2x6 [CMP]"] == [], "own regional items are listed per Project", r["regional_items"])
check("xps" not in r["own_price_items"]["2x6 [CMP]"], "a premise-book price is not listed as an own price")
check(r["mixed_own_origins"], "mixed origins of own prices are flagged")

print("-- 2. real mismatches stay a warning")
check(PBASIS.assess([rec(orig_2x6), rec(orig_az)])["status"] == PBASIS.MISALIGNED, "originals AI vs mixed")
other = raw("AZRAS [CMP]", "azras", copy_az["module_outputs"]["module5"]["cost_lines"], "v0")
check(PBASIS.assess([rec(copy_2x6), rec(other)])["status"] == PBASIS.MISALIGNED, "copies of two book versions")
not_recalc = raw("AZRAS [CMP]", "azras", orig_az["module_outputs"]["module5"]["cost_lines"], "v1")
check(PBASIS.assess([rec(copy_2x6), rec(not_recalc)])["status"] == PBASIS.MISALIGNED,
      "a copy still priced on the source basis")
check(PBASIS.assess([rec(copy_2x6), rec(orig_az)])["status"] == PBASIS.MISALIGNED, "a copy mixed with an original")
same = PBASIS.assess([rec(orig_2x6), rec(raw("B", "rc_frame", [L("xps", AI)], None))])
check(same["status"] == PBASIS.UNIFORM, "one token is uniform", same["status"])
legacy = rec(copy_az)
legacy["raw"] = json.loads(json.dumps(legacy["raw"]))
legacy["raw"]["module_outputs"]["module5"]["_meta"] = {}
check(PBASIS.own_price_lines(legacy["raw"]) == [], "an unsaved module5 gives no price-origin lines (extractor rule)")

print("-- 3. the warning text")
src = (ROOT / "main.py").read_text(encoding="utf-8")
check("PBASIS.assess(self.projects)" in src, "main.py uses comparison/price_basis.py")
check("「7. 比較前提表」タブで「一覧を作成」" in src and "比較用コピーを作成" in src,
      "the Japanese warning names tab 7 and its buttons")
check("7. Comparison Premise Book" in src and "Load the copies here" in src, "an English procedure exists")
check("内蔵地域単価で値付けされた工種" in src, "the warning lists the regionally priced items")
ui = (ROOT / "comparison" / "premise_book_ui.py").read_text(encoding="utf-8")
check("一覧を作成" in ui and "比較用コピーを作成" in ui, "the button names quoted in the warning exist in tab 7")

print("-- 4. tab 7 shows buildings 1..7")
check("*vals[:3]" not in ui, "no list is cut to three buildings")
check("MAX_BUILDINGS = 7" in ui, "seven building columns are defined")

print("-- 5. GUI (skipped without a display)")
try:
    import tkinter as tk
    _probe = tk.Tk()
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
        f = os.path.join(tmp, p["project_id"].replace(" ", "_").replace("[", "").replace("]", "") + ".json")
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
        res = run([orig_2x6, orig_az])
        warn = [m for k, m in res if k == "warning" and "単価根拠の前提" in m]
        check(len(warn) == 1 and "コンクリート、鉄筋" in warn[0] and "比較用コピーを作成" in warn[0],
              "originals: one warning with the regional items and the procedure", [k for k, _ in res])
        res = run([copy_2x6, copy_az, copy_rc])
        check(not [m for k, m in res if "単価根拠の前提" in m], "copies: the price-basis warning is gone")
        info = [m for k, m in res if k == "info" and "比較前提表（版 v1）" in m]
        check(len(info) == 1 and "コンクリート（地域単価）" in info[0] and "コンクリート（AI単価）" in info[0],
              "copies: one information dialog lists each Project's own prices")
        res = run([copy_2x6, copy_az], "en")
        check(any(k == "info" and "premise book (version v1)" in m for k, m in res), "the English information exists")
        app = M.App()
        pt = app.premise_tab
        check(list(pt.price_tree["columns"])[-1] == "p7" and list(pt.business_tree["columns"])[-1] == "p7",
              "tab 7 price and business lists have building 7 columns")
        app.destroy()
    finally:
        messagebox.showwarning, messagebox.showinfo, messagebox.showerror = saved

print()
if FAIL:
    print("[NG] PATCH_008 self-check FAILED:")
    for f in FAIL:
        print("   -", f)
    raise SystemExit(1)
print("PATCH_008_PRICE_BASIS_PREMISE_BOOK_PASS")
