# -*- coding: utf-8 -*-
"""PATCH_005 self-check (03 Compare): the comparison premise book.

The lists must separate a price difference from a scope difference, exclude the
items whose difference IS the construction method, refuse a rent derived from
construction cost, write every copy inside the group folder without touching a
source Project, and refuse to be compared until each copy has been recalculated.
"""
import copy
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from comparison import premise_book as PB  # noqa: E402

FAIL = []


def check(ok, label, detail=""):
    if ok:
        print(f"  [OK]   {label}")
    else:
        FAIL.append(f"{label} :: {detail}")
        print(f"  [NG]   {label} :: {detail}")


def line(key, unit, qty, rate, structure="installed_all_in"):
    return {"cost_item_key": key, "unit": unit, "quantity": qty, "installed_all_in_unit_cost": rate,
            "material_unit_cost": rate, "labor_unit_cost": 0.0, "equipment_unit_cost": 0.0,
            "pricing_structure": structure, "pricing_status": "ai_primary_basis_provisional",
            "regional_unit_cost_metadata": {"candidate_quality": {"scope_definition": "installed_all_in"},
                                            "provisional_evidence": {"status": "found", "source_title": "src",
                                                                     "source_url": "https://example.test"}}}


def project(name, method, lines, packages, rent_method="gross_yield", extra=None):
    p = {"project_id": f"id-{name}", "updated_at": "2026-09-22T00:00:00Z", "save_revision": 3,
         "common": {"project_name": name, "construction_method_id": method,
                    "project_location": "愛知県春日井市松河戸町2-18-7", "scale_gfa_m2": 245.1},
         "module_outputs": {
             "module3": {"period_years": 200, "events": [
                 {"year": 60, "action": "full_rebuild", "component_key": "whole_building"},
                 {"year": 10, "action": "repair", "component_key": f"structure_{method}"}]},
             "module5": {"currency": "JPY", "cost_lines": lines,
                         "summary": {"direct_construction_cost": 1.0, "additional_equipment_cost": 1.0,
                                     "total_construction_cost": 2.0},
                         "_input_snapshot": {"location": "Japan / Nagoya", "settings": {"overhead_rate": 12.0},
                                             "equipment_selection": {k: {"include": True, "cost": v,
                                                                         "cost_basis": "ui_local_currency"}
                                                                     for k, v in packages.items()},
                                             "ai_cost_provider_overlay": {
                                                 "project_binding": {"project_id": f"id-{name}"},
                                                 "unit_costs": {}, "equipment_packages": []}}},
             "module6": {"_input_snapshot": {"settings": {"annual_rent_per_m2": 30000.0,
                                                          "rent_setting_method": rent_method,
                                                          "discount_rate_percent": 4.0}}},
             "module7": {"_input_snapshot": {"settings": {"overhead": 0.12}}}},
         "module_status": {m: {"status": "saved", "updated_at": "2026-09-22T00:00:00Z"}
                           for m in ("module5", "module6", "module7")}}
    if extra:
        p["module_outputs"]["module5"]["cost_lines"].extend(extra)
    return p


CL = PB.load_classification()
A = project("Wood", "timber", [line("doors", "m2", 6.33, 204816.92), line("roofing", "m2", 122.5, 7250.0),
                               line("dimension_lumber", "m3", 30.0, 182834.0), line("concrete", "m3", 12.3, 30900.0)],
            {"hvac": 2824504.0, "electrical": 1297498.0})
B = project("RC", "rc_frame", [line("doors", "m2", 6.33, 47582.35), line("roofing", "m2", 162.6, 7250.0),
                               line("external_finish_rc", "m2", 126.8, 4538.0), line("concrete", "m3", 129.4, 26245.0)],
            {"hvac": 2836560.0, "electrical": 1482855.0})

print("PATCH_005 self-check")
print("-- 1. the two lists separate price from scope")
L = PB.build_lists([A, B], CL)
price_keys = {r["key"] for r in L["price_rows"]}
scope_keys = {r["key"] for r in L["scope_rows"]}
check("doors" in price_keys, "a shared item with different prices is a price difference")
check(next(r for r in L["price_rows"] if r["key"] == "doors")["differs"] is True, "and it is marked as differing")
check(next(r for r in L["price_rows"] if r["key"] == "roofing")["differs"] is False,
      "an equal price is listed but not marked as differing")
check("concrete" not in price_keys, "method-dependent work is excluded from the price list")
check("dimension_lumber" not in price_keys and "dimension_lumber" not in scope_keys,
      "a method-specific item is in neither list")
check("external_finish_rc" not in scope_keys, "a method-specific item does not become a scope gap")
check("exterior_finish" in scope_keys, "a Project with no exterior finish at all IS a scope gap (family rule)")
fam = next(r for r in L["scope_rows"] if r["key"] == "exterior_finish")
check(fam["present"] == [1] and fam["missing"] == [0], "the family row names who has it and who does not", str(fam["present"]))
check({r["key"] for r in L["price_rows"] if r["kind"] == "equipment_package"} == {"hvac", "electrical"},
      "equipment packages are compared as prices")

print("-- 2. nothing is unified until a human decides")
D = PB.default_decisions(L)
left = PB.validate_decisions(L, D)
check(any(x.startswith("price_undecided:doors") for x in left), "an undecided differing price blocks the book")
check("market_rent_missing" in left, "the market rent must be entered")
check(D["business"]["module6:rent_setting_method"] == "market_rent", "the rent method defaults to market rent")
D["business"]["module6:rent_setting_method"] = "gross_yield"
check("rent_method_must_be_market_rent" in PB.validate_decisions(L, D),
      "a rent derived from construction cost is refused outright")
D["business"]["module6:rent_setting_method"] = "market_rent"
D["business"]["module6:annual_rent_per_m2"] = 15000.0
for r in L["price_rows"]:
    c = r["candidates"][0]
    D["price"][r["row_id"]] = {"mode": "unify", "rate": c["rate"], "from_project": c["project_index"]}
for r in L["scope_rows"]:
    D["scope"][r["row_id"]] = {"decision": "accept_method_difference", "note": ""}
check(PB.validate_decisions(L, D) == [], "with every decision made the book is ready")

print("-- 3. writing the group")
with tempfile.TemporaryDirectory() as tmp:
    src_dir = Path(tmp) / "JSON"
    sources = []
    for pj in (A, B):
        d = src_dir / pj["common"]["project_name"]
        d.mkdir(parents=True)
        f = d / f"{pj['common']['project_name']}.json"
        f.write_text(json.dumps(pj, ensure_ascii=False), encoding="utf-8")
        sources.append((str(f), pj))
    before = {s[0]: Path(s[0]).read_bytes() for s in sources}
    out = PB.write_group(str(src_dir), "工法比較", sources, CL, L, D)
    folder = Path(out["folder"])
    check(folder.parent == src_dir and folder.name.endswith("_比較_工法比較"), "the group folder is created where asked",
          str(folder))
    check(all(Path(c["path"]).parent.parent == folder for c in out["copies"]),
          "every copy is inside the group folder")
    check(all(Path(s[0]).read_bytes() == before[s[0]] for s in sources), "no source Project is modified")
    check((folder / Path(out["book_path"]).name).exists(), "the premise book is written in the group folder")
    book = json.loads(Path(out["book_path"]).read_text(encoding="utf-8"))
    check(book["schema"] == PB.BOOK_SCHEMA and book["version"] == out["version"], "the book records its own version")
    check(book["classification"] == CL, "the classification actually used is saved with the book")
    check([s["sha256"] for s in book["sources"]] == [PB.file_sha256(s[0]) for s in sources],
          "each source is recorded with its content hash")

    cp = json.loads(Path(out["copies"][1]["path"]).read_text(encoding="utf-8"))
    ov = cp["module_outputs"]["module5"]["_input_snapshot"]["ai_cost_provider_overlay"]
    check(cp["project_id"] != B["project_id"], "the copy gets its own project id")
    check(ov["project_binding"]["project_id"] == cp["project_id"],
          "the price overlay is re-bound to the copy (otherwise the engine discards every price)")
    check(abs(ov["unit_costs"]["doors"]["installed_unit_cost"] - 204816.92) < 1e-6,
          "the unified price is written into the copy", str(ov["unit_costs"]["doors"]["installed_unit_cost"]))
    check(ov["unit_costs"]["doors"]["pricing_status"] == "comparison_group_confirmed",
          "premise-book prices are identifiable in Module 5")
    sel = cp["module_outputs"]["module5"]["_input_snapshot"]["equipment_selection"]["electrical"]
    check(abs(sel["cost"] - 1297498.0) < 1e-6 and sel["cost_basis"].startswith("ai_approximate_cost_session"),
          "the unified equipment price is written as a current-market price", str(sel))
    s6 = cp["module_outputs"]["module6"]["_input_snapshot"]["settings"]
    check(s6["rent_setting_method"] == "market_rent" and s6["annual_rent_per_m2"] == 15000.0,
          "the business premises are written into every copy")
    check(cp["comparison_copy"]["schema"] == PB.COPY_SCHEMA
          and cp["comparison_copy"]["allowed_modules"] == PB.COPY_ALLOWED_MODULES,
          "the copy carries the marker 01 Planning / 02 Evaluation act on")
    check(cp["comparison_copy"]["source_sha256"] == PB.file_sha256(sources[1][0]),
          "the copy remembers the exact source content it was built from")
    check(all(cp["module_status"][m]["status"] == "recalculation_pending" for m in PB.COPY_ALLOWED_MODULES),
          "a fresh copy is marked as needing recalculation")

    print("-- 4. a copy is not comparable until it is recalculated")
    issues = {i["code"] for i in PB.verify_copy(cp)}
    check(issues == {"not_recalculated"}, "a fresh copy reports only that it must be recalculated", str(issues))
    done = copy.deepcopy(cp)
    for m in PB.COPY_ALLOWED_MODULES:
        done["module_status"][m] = {"status": "saved", "updated_at": "2026-09-22T10:00:00Z"}
    check(PB.verify_copy(done) == [], "a recalculated copy with an unchanged source reports nothing")
    Path(sources[1][0]).write_text(json.dumps(dict(B, save_revision=4), ensure_ascii=False), encoding="utf-8")
    check({i["code"] for i in PB.verify_copy(done)} == {"source_changed"},
          "editing the source Project afterwards is detected")
    other = copy.deepcopy(done)
    other["comparison_copy"]["premise_book_version"] = "deadbeef0000"
    check({i["code"] for i in PB.verify_group([done, other])} == {"different_premise_book_versions"},
          "copies from two different premise books cannot be compared together")
    mixed = PB.verify_group([done, {"project_id": "plain"}])
    check("mixed_copies_and_originals" in {i["code"] for i in mixed},
          "mixing copies and source Projects is reported")
    rentdiff = copy.deepcopy(done)
    rentdiff["module_outputs"]["module6"]["_input_snapshot"]["settings"]["annual_rent_per_m2"] = 20000.0
    check("different_rent_premises" in {i["code"] for i in PB.verify_group([done, rentdiff])},
          "different rents between copies are reported")

print("-- 5. the screen is wired in")
main = (ROOT / "main.py").read_text(encoding="utf-8")
check("from comparison.premise_book_ui import PremiseBookTab" in main, "the premise-book tab is imported")
check("self.tabs.add(self.premise_tab,text='7. 比較前提表')" in main, "the tab is added")
check("(self.premise_tab,'7. 比較前提表')" in main, "the tab title follows the language switch")
check("'7. 比較前提表':'7. Comparison Premise Book'" in main, "the tab has an English title")
check("PB.verify_copy(raw)" in main and "PB.verify_group(" in main, "loading a copy verifies it")
ui = (ROOT / "comparison" / "premise_book_ui.py").read_text(encoding="utf-8")
check("元Projectで行い" in ui, "the scope list tells the user where a quantity is corrected")
check("市場家賃を直接入力してください" in ui, "the screen refuses a yield-derived rent")

print()
if FAIL:
    print("[NG] PATCH_005 self-check FAILED:")
    for f in FAIL:
        print("   -", f)
    raise SystemExit(1)
print("PATCH_005_COMPARISON_PREMISE_BOOK_PASS")
