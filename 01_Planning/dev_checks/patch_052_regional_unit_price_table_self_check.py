# -*- coding: utf-8 -*-
"""PATCH_052 self-check: regional unit-price table and removal of "図面追加".

1. services/regional_unit_price_table.py: scale classes, match keys (method only
   for method-dependent items), never overwriting, versions, validation.
2. Module 5 (real window under a display): the four buttons exist; registering
   creates the standalone versioned table outside the Project folder and
   applies it; the AI request scope then excludes table items; a second
   Project of another method gets only the common items; a registered price
   is not overwritten and the difference is reported; removing the table
   restores the AI prices; applying twice does not stack; a new version
   replaces this Project's prices; currency mismatch and a fallback region
   are refused / asked.
3. Engine: price_basis_fingerprint tokens and table reference; a table price
   is displayed as an estimated (yellow) price.
4. Module 1: the "図面追加" button no longer exists; "PDF/ZIP読込" remains.

Run: python dev_checks/patch_052_regional_unit_price_table_self_check.py
"""
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from services import regional_unit_price_table as R  # noqa: E402
from services.construction_cost_engine_v9_4 import _price_basis_fingerprint  # noqa: E402

FAIL = []


def check(ok, label, detail=""):
    if ok:
        print(f"  [OK]   {label}")
    else:
        FAIL.append(f"{label} :: {detail}")
        print(f"  [NG]   {label} :: {detail}")


print("PATCH_052 self-check")
print("-- 1. table service")
t = R.new_table("Japan / Nagoya", "jpy", "2026-10")
check(not R.validate_table(t) and t["currency"] == "JPY", "a new table is valid", R.validate_table(t))
cl = t["scale_classes"]
check([R.scale_class_for(x, cl) for x in (245.1, 300, 300.1, 3000, 3000.1, 0, None)] == ["S", "S", "M", "M", "L", None, None],
      "scale class by gross floor area (300 / 3,000 m2, unknown -> None)")
check(R.spec_key_for("concrete", "rc_frame", t) == "rc_frame" and R.spec_key_for("xps", "rc_frame", t) == "common",
      "spec key = method only for method-dependent items")
ov = {"unit_costs": {
    "concrete": {"pricing_status": "ai_post_review_rechecked_provisional", "pricing_structure": "installed_all_in", "installed_unit_cost": 30000.0, "unit": "m3", "reviewer": "ChatGPT"},
    "xps": {"pricing_status": "ai_primary_basis_provisional", "pricing_structure": "component_split", "material": 100.0, "labor": 50.0, "equipment": 10.0, "unit": "m3"},
    "glass": {"pricing_status": "comparison_group_confirmed", "pricing_structure": "installed_all_in", "installed_unit_cost": 9.0}},
    "equipment_packages": [{"package_key": "hvac", "pricing_mode": "unit_rate_per_gfa", "unit_rate": 5000.0, "cost": 1.0},
                           {"package_key": "kitchen", "pricing_mode": "lump_sum", "cost": 800000.0}]}
e = R.entries_from_overlay(ov, t, units={"concrete": "m3", "xps": "m3", "glass": "m2"}, construction_method="rc_frame", scale_class="S", project_info={})
check({x["entry_key"] for x in e} == {"concrete|rc_frame|m3|S", "xps|common|m3|S", "hvac|common|JPY/m2_gfa|S"},
      "only AI-adopted prices and per-floor-area equipment are registrable", [x["entry_key"] for x in e])
a1, s1 = R.add_entries(t, e)
a2, s2 = R.add_entries(t, [dict(x, adopted_value=1.0) for x in e])
check(len(a1) == 3 and not a2 and len(s2) == 3 and t["entries"]["xps|common|m3|S"]["adopted_value"] == 160.0, "a registered price is never overwritten")
res = R.apply_table(t, cost_items={"concrete": "m3", "xps": "m3"}, equipment_keys=["hvac", "kitchen"], construction_method="wood_frame", gross_floor_area_m2=245.1, table_file="f.json")
check(sorted(res["unit_costs"]) == ["xps"] and [x["cost_item_key"] for x in res["ref"]["unregistered_items"]] == ["concrete", "kitchen"],
      "another method gets common items only; missing items are unregistered", res["ref"]["unregistered_items"])
check(res["equipment_packages"][0]["cost"] == 5000.0 * 245.1, "equipment cost = table rate x this Project's floor area")
res_m = R.apply_table(t, cost_items={"xps": "m3"}, equipment_keys=[], construction_method="rc_frame", gross_floor_area_m2=1000.0, table_file="f.json")
check(not res_m["unit_costs"] and res_m["ref"]["scale_class"] == "M", "no substitution from another scale class")
check(R.next_version(["2026-10"], __import__("datetime").datetime(2026, 10, 1)) == "2026-10.2"
      and R.next_version([], __import__("datetime").datetime(2026, 10, 1)) == "2026-10", "version numbering")
check(R.table_filename("Japan / Nagoya", "2026-10") == "AZRAS_UNIT_PRICE_TABLE_Japan_Nagoya_2026-10.json", "file name")
bad = json.loads(json.dumps(t))
bad["scale_classes"][1]["max_gross_floor_area_m2"] = 100
check(bool(R.validate_table(bad)), "decreasing scale boundaries are rejected")

print("-- 3. engine")
loc = {"pricing_mode": "ai", "regional_unit_price_table": {"region_key": "Japan / Nagoya", "version": "2026-10", "sha256": "h", "scale_class": "S"}}
RT = R.TABLE_PRICING_STATUS
fp = _price_basis_fingerprint(loc, [{"pricing_status": RT}, {"pricing_status": RT}])
check(fp["basis_token"] == "regional_unit_price_table" and fp["regional_unit_price_table"]["version"] == "2026-10", "all table lines", fp["basis_token"])
fp = _price_basis_fingerprint(loc, [{"pricing_status": RT}, {"pricing_status": "ai_primary_basis_provisional"}])
check(fp["basis_token"] == "regional_unit_price_table_with_ai_items", "table + AI lines", fp["basis_token"])
fp = _price_basis_fingerprint(loc, [{"pricing_status": RT}, {"pricing_status": "priced"}])
check(fp["basis_token"] == "mixed_regional_unit_price_table_and_regional_database", "table + database lines", fp["basis_token"])
fp = _price_basis_fingerprint(loc, [{"pricing_status": "comparison_group_confirmed"}, {"pricing_status": RT}])
check(fp["basis_token"] == "comparison_group_premise_book", "premise-book copy keeps its token with table items", fp["basis_token"])
fp = _price_basis_fingerprint({}, [{"pricing_status": "ai_primary_basis_provisional"}])
check(fp["basis_token"] == "ai_approximate_cost_session" and fp["regional_unit_price_table"] is None, "old behaviour unchanged without a table")
eng = (ROOT / "services" / "construction_cost_engine_v9_4.py").read_text(encoding="utf-8")
check('"ai_research_provisional","regional_price_table_fixed","estimated"' in eng, "a table price is displayed as estimated (yellow)")

print("-- 4. Module 1")
m1 = (ROOT / "module1" / "app.py").read_text(encoding="utf-8")
check('text=("図面追加"' not in m1 and "register_drawing_files(replace=False)" not in m1, "the 図面追加 button is removed")
check('command=lambda:self.register_drawing_files(replace=True)' in m1, "PDF/ZIP読込 remains")

print("-- 2. Module 5 window")
try:
    import tkinter as tk
    _p = tk.Tk(); _p.destroy()
    have_display = True
except Exception as exc:  # noqa: BLE001
    have_display = False
    print(f"  [SKIP] no display: {str(exc)[:60]}")
if have_display:
    import module5.app as M
    msgs = []
    answers = {"okcancel": True, "yesnocancel": True, "yesno": True}
    saved = {n: getattr(M.messagebox, n) for n in ("showinfo", "showwarning", "showerror", "askokcancel", "askyesnocancel", "askyesno")}
    M.messagebox.showinfo = lambda *a, **k: msgs.append(("info", a[1]))
    M.messagebox.showwarning = lambda *a, **k: msgs.append(("warn", a[1]))
    M.messagebox.showerror = lambda *a, **k: msgs.append(("error", a[1]))
    M.messagebox.askokcancel = lambda *a, **k: answers["okcancel"]
    M.messagebox.askyesnocancel = lambda *a, **k: answers["yesnocancel"]
    M.messagebox.askyesno = lambda *a, **k: answers["yesno"]
    saved_req = M.require_current_module_output
    M.require_current_module_output = lambda *a, **k: {}
    try:
        root = tk.Tk(); root.withdraw()
        app = M.Module5App(root, ROOT, language="ja")
        texts = []

        def walk(w):
            for c in w.winfo_children():
                try:
                    texts.append(str(c.cget("text")))
                except Exception:  # noqa: BLE001
                    pass
                walk(c)
        walk(app)
        check(all(x in texts for x in ("地域単価表を適用（AI調査の前に）", "AI採用単価を地域単価表へ登録", "地域単価表の内容を確認", "地域単価表の適用を解除")),
              "the four table buttons exist")
        tmp = Path(tempfile.mkdtemp())
        folder = R.table_directory(tmp)
        app._price_table_dir = lambda: folder
        app._ask_price_table_folder = lambda title: folder  # PATCH_054: folder dialog answered "register here"
        app.refresh_project_from_context = lambda *a, **k: None
        app._cost_profile_match_basis = lambda: "matched_project_city"
        app._authoritative_project_cost_location = lambda: "Kasugai"
        app.calculate = lambda silent_success=False: True
        scope = {"items": [{"cost_item_key": "concrete", "unit": "m3"}, {"cost_item_key": "xps", "unit": "m3"}, {"cost_item_key": "glass", "unit": "m2"}],
                 "equipment_packages": [{"package_key": "hvac"}], "gross_floor_area_m2": 245.1}
        app._full_cost_scope = lambda: json.loads(json.dumps(scope))
        app.location.set("Japan / Nagoya"); app.currency.set("JPY")
        lc = app.db["locations"]["Japan / Nagoya"]

        def project(pid, method):
            app.project = {"project_id": pid, "common": {"project_name": pid, "construction_method_id": method}}
            app.project_path = tmp / "JSON_A" / pid / f"{pid}.json"

        def ai(v, who="ChatGPT"):
            return {"pricing_status": "ai_primary_basis_provisional", "pricing_structure": "installed_all_in", "installed_unit_cost": v, "unit": "m3", "reviewer": who}
        project("A", "rc_frame")
        lc["_session_ai_unit_cost_overlay"] = {"project_binding": {"project_id": "A"}, "unit_costs": {"concrete": ai(30000.0), "xps": ai(41500.0)},
                                               "equipment_packages": [{"package_key": "hvac", "pricing_mode": "unit_rate_per_gfa", "unit_rate": 5000.0, "cost": 1225500.0}]}
        app.register_regional_price_table()
        files = sorted(folder.glob("*.json"))
        check([f.name for f in files] == [R.table_filename("Japan / Nagoya", R.next_version([]))], "register creates one standalone table", [f.name for f in files])
        ov = app._current_ai_cost_overlay()
        check(ov["unit_costs"]["xps"]["pricing_status"] == RT and ov["regional_unit_price_table"]["scale_class"] == "S", "the creating Project is priced from the table")
        sc = app._ai_cost_request_scope()
        check([x["cost_item_key"] for x in sc["items"]] == ["glass"] and not sc["equipment_packages"], "AI request scope excludes table items", sc)
        project("B", "wood_frame"); lc.pop("_session_ai_unit_cost_overlay", None)
        app.apply_regional_price_table()
        ov = app._current_ai_cost_overlay()
        check(sorted(ov["unit_costs"]) == ["xps"] and ov["project_binding"]["project_id"] == "B", "another method gets the common items", sorted(ov["unit_costs"]))
        ov["unit_costs"]["concrete"] = ai(28000.0, "Gemini")
        ov["regional_unit_price_table"]["replaced_ai_records"] = {"unit_costs": {"xps": ai(74000.0)}, "equipment_packages": []}
        lc["_session_ai_unit_cost_overlay"] = ov
        app.register_regional_price_table()
        tb = R.load_table(files[0])
        check("concrete|wood_frame|m3|S" in tb["entries"] and tb["entries"]["xps|common|m3|S"]["adopted_value"] == 41500.0, "append adds new items, keeps registered prices")
        check("違う品目" in msgs[-1][1], "a differing AI price is reported", msgs[-1][1][:200])
        app.clear_regional_price_table()
        ov = app._current_ai_cost_overlay()
        check("regional_unit_price_table" not in ov and ov["unit_costs"]["xps"]["installed_unit_cost"] == 74000.0, "remove restores the AI prices")
        app.apply_regional_price_table(); app.apply_regional_price_table()
        ov = app._current_ai_cost_overlay()
        check(ov["unit_costs"]["xps"]["installed_unit_cost"] == 41500.0 and ov["regional_unit_price_table"]["replaced_ai_records"]["unit_costs"]["xps"]["installed_unit_cost"] == 74000.0,
              "applying twice does not stack")
        answers["yesnocancel"] = False
        app.register_regional_price_table()
        vers = [v for v, _ in R.list_tables(folder, "Japan / Nagoya")]
        t2 = R.load_table(R.latest_table_path(folder, "Japan / Nagoya"))
        check(len(vers) == 2 and t2["entries"]["xps|common|m3|S"]["adopted_value"] == 74000.0, "a new version replaces this Project's prices", vers)
        app.currency.set("USD"); app.apply_regional_price_table()
        check(msgs[-1][0] == "error", "currency mismatch is refused")
        app.currency.set("JPY")
        app._cost_profile_match_basis = lambda: "country_reference_fallback_not_project_city"
        answers["yesno"] = False; n = len(msgs)
        app.apply_regional_price_table()
        check(len(msgs) == n, "a country-reference profile asks first and stops on No")
        # AI import after a table: only unregistered items are parsed, table prices stay.
        app._cost_profile_match_basis = lambda: "matched_project_city"
        project("C", "wood_frame"); lc.pop("_session_ai_unit_cost_overlay", None)
        app.apply_regional_price_table()
        seen = []
        resp = tmp / "resp.json"; resp.write_text('{"schema": "AZRAS_AI_APPROX_COST"}', encoding="utf-8")
        saved_dlg, saved_url, saved_audit = M.filedialog.askopenfilenames, M.enforce_public_evidence_urls, M.record_ai_import_audit
        M.filedialog.askopenfilenames = lambda **k: [str(resp)]
        M.enforce_public_evidence_urls = lambda p: {}
        M.record_ai_import_audit = lambda *a, **k: None
        app._copy_ai_cost_json_to_round_folder = lambda *a: None
        app._ai_cost_security_audit_dir = lambda: tmp
        app._show_ai_cost_changelog = lambda *a, **k: None

        def parse(payload, path, scope, cur):
            seen.append([x["cost_item_key"] for x in scope["items"]])
            c = lambda v, u: {"installed_unit_cost": v, "pricing_structure": "installed_all_in", "unit": u, "reviewer": "ChatGPT",
                              "completed_at": "2026-10-01", "research_execution_status": "completed"}
            return {"reviewer": "ChatGPT", "research_role": "primary_guide", "completed_at": "2026-10-01T00:00:00Z", "source_json": "resp.json",
                    "research_execution_status": "completed", "unit_cost_candidates": {"glass": c(9000.0, "m2"), "xps": c(99999.0, "m3")},
                    "equipment_candidates": {}, "incomplete_items": []}
        app._parse_ai_cost_payload = parse
        try:
            app.import_ai_cost_json()
        finally:
            M.filedialog.askopenfilenames, M.enforce_public_evidence_urls, M.record_ai_import_audit = saved_dlg, saved_url, saved_audit
        ov = app._current_ai_cost_overlay()
        check(seen == [["glass"]], "AI import parses only unregistered items", seen)
        check(ov["unit_costs"]["xps"]["pricing_status"] == RT and ov["unit_costs"]["glass"]["installed_unit_cost"] == 9000.0
              and ov["regional_unit_price_table"]["version"], "AI import keeps the table prices and reference")
        app._apply_global_language("en")
        check("Regional price table" in app.price_table_status.get(), "status follows the language")
        app.destroy(); root.destroy()
    finally:
        for n, f in saved.items():
            setattr(M.messagebox, n, f)
        M.require_current_module_output = saved_req

print()
if FAIL:
    print("[NG] PATCH_052 self-check FAILED:")
    for f in FAIL:
        print("   -", f)
    raise SystemExit(1)
print("PATCH_052_REGIONAL_UNIT_PRICE_TABLE_PASS")
