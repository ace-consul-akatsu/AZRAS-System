# -*- coding: utf-8 -*-
"""PATCH_007 self-check (03 Compare): 02 Evaluation PATCH_009 market-rent contract.

In market-rent mode 02 Evaluation saves summary.target_gross_yield_percent =
null, summary.stored_target_gross_yield_percent = the user's preference and
target_gross_yield_active = false (summary and settings); settings keep the
preference in target_gross_yield_percent.  03 Compare must
  (1) never report that inactive yield as the Project's target yield,
  (2) never list it as a premise difference between Projects, and
  (3) write comparison copies in the same settings shape Evaluation saves
      (Module 6 replaces a null target with 8.0 on reload).
The section-1 fixture is the module6 output produced by 02_Evaluation_09's own
services/investment_engine_v9_5.calculate_investment (market rent, 6.5 %).
"""
import copy
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from comparison import extractor as EX  # noqa: E402
from comparison import premise_book as PB  # noqa: E402

FAIL = []


def check(ok, label, detail=""):
    if ok:
        print(f"  [OK]   {label}")
    else:
        FAIL.append(f"{label} :: {detail}")
        print(f"  [NG]   {label} :: {detail}")


SAVED = {"status": "saved", "is_current": True}


def core_json(m6):
    return {"project_id": "id-x", "common": {"project_name": "X", "construction_method_id": "rc_frame"},
            "module_outputs": {"module6": m6}}


def extract(m6):
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "p.json"
        p.write_text(json.dumps(core_json(m6)), encoding="utf-8")
        return EX.extract_core_project(p)


print("PATCH_007 self-check")
print("-- 1. extractor: real 02_Evaluation_09 market-rent output (preference 6.5 %)")
# Output of 02_Evaluation_09 calculate_investment() + its _input_snapshot, trimmed to the rent keys.
m6_eval09 = {"_meta": dict(SAVED),
             "settings": {"rent_setting_method": "market_rent", "target_gross_yield_percent": 6.5,
                          "stored_target_gross_yield_percent": None, "target_gross_yield_active": False,
                          "annual_rent_per_m2": 30000.0, "resolved_annual_rent_per_m2": 30000.0},
             "summary": {"rent_setting_method": "market_rent", "target_gross_yield_percent": None,
                         "stored_target_gross_yield_percent": 6.5, "target_gross_yield_active": False,
                         "resolved_annual_rent_per_m2": 30000.0},
             "_input_snapshot": {"settings": {"rent_setting_method": "market_rent", "annual_rent_per_m2": 30000.0,
                                              "target_gross_yield_percent": 6.5, "target_gross_yield_active": False}}}
old = EX._num(m6_eval09.get("target_gross_yield_percent")
              or m6_eval09["settings"].get("target_gross_yield_percent"))
check(old == 6.5, "the pre-PATCH_007 read did return the inactive 6.5 %, so this is the right defect", str(old))
r = extract(m6_eval09)
check(r["rent_setting_method"] == "market_rent" and r["rent_derived_from_cost"] is False,
      "rent method is market_rent, not derived from cost", str((r["rent_setting_method"], r["rent_derived_from_cost"])))
check(r["target_gross_yield_percent"] is None, "inactive yield is NOT reported as the target",
      str(r["target_gross_yield_percent"]))
check(r["target_gross_yield_active"] is False, "target_gross_yield_active is False")
check(r["stored_target_gross_yield_percent"] == 6.5, "the stored preference is kept for reference",
      str(r["stored_target_gross_yield_percent"]))

print("-- 2. extractor: other shapes")
m6 = {"_meta": dict(SAVED), "settings": {"rent_setting_method": "market_rent",
                                         "target_gross_yield_percent": 8.0}}
r = extract(m6)
check(r["target_gross_yield_percent"] is None and r["stored_target_gross_yield_percent"] == 8.0,
      "pre-PATCH_009 market_rent JSON (no flag): yield becomes the stored memo only",
      str((r["target_gross_yield_percent"], r["stored_target_gross_yield_percent"])))
m6 = {"_meta": dict(SAVED), "_input_snapshot": {"settings": {"rent_setting_method": "market_rent",
                                                             "target_gross_yield_percent": 8.0}}}
r = extract(m6)
check(r["rent_setting_method"] == "market_rent" and r["target_gross_yield_percent"] is None,
      "method saved only in _input_snapshot.settings is still recognised",
      str((r["rent_setting_method"], r["target_gross_yield_percent"])))
m6 = {"_meta": dict(SAVED), "settings": {"rent_setting_method": "gross_yield",
                                         "target_gross_yield_percent": 8.0, "target_gross_yield_active": True}}
r = extract(m6)
check(r["target_gross_yield_percent"] == 8.0 and r["target_gross_yield_active"] is True
      and r["rent_derived_from_cost"] is True, "gross_yield mode still reports its active 8 %",
      str((r["target_gross_yield_percent"], r["target_gross_yield_active"])))
m6 = {"_meta": dict(SAVED), "target_gross_yield_percent": 0.0,
      "settings": {"rent_setting_method": "gross_yield", "target_gross_yield_percent": 8.0}}
r = extract(m6)
check(r["target_gross_yield_percent"] == 0.0, "a saved 0.0 is not skipped as falsy",
      str(r["target_gross_yield_percent"]))
m6 = {"_meta": dict(SAVED), "settings": {"target_gross_yield_percent": 8.0}}
r = extract(m6)
check(r["target_gross_yield_percent"] == 8.0 and r["rent_setting_method"] == "unknown",
      "legacy JSON with no rent method keeps the previous behaviour", str(r["target_gross_yield_percent"]))
m6 = {"_meta": dict(SAVED), "settings": {"rent_setting_method": "gross_yield",
                                         "target_gross_yield_percent": 8.0, "target_gross_yield_active": False}}
r = extract(m6)
check(r["target_gross_yield_percent"] is None, "an explicit active=False flag wins over the method",
      str(r["target_gross_yield_percent"]))


def project(name, rent_method, extra_settings):
    st = {"annual_rent_per_m2": 30000.0, "rent_setting_method": rent_method, "discount_rate_percent": 4.0}
    st.update(extra_settings)
    return {"project_id": f"id-{name}", "updated_at": "2026-09-24T00:00:00Z", "save_revision": 1,
            "common": {"project_name": name, "construction_method_id": name.lower()},
            "module_outputs": {"module5": {"currency": "JPY", "cost_lines": [],
                                           "_input_snapshot": {"settings": {"overhead_rate": 12.0}}},
                               "module6": {"_input_snapshot": {"settings": st}},
                               "module7": {"_input_snapshot": {"settings": {"overhead": 0.12}}}}}


print("-- 3. premise book: an inactive yield is not a premise difference")
CL = PB.load_classification()
A = project("Wood", "market_rent", {"target_gross_yield_percent": 8.0, "target_gross_yield_active": False})
B = project("RC", "market_rent", {"target_gross_yield_percent": 6.5, "target_gross_yield_active": False})
L = PB.build_lists([A, B], CL)
ids = {r["row_id"] for r in L["business_rows"]}
leaked = sorted(i for i in ids if i.split(":", 1)[1] in PB.RENT_YIELD_MEMO_KEYS)
check(not leaked, "no target-yield row in the business premise list (market_rent vs market_rent)", str(leaked))
C = project("Steel", "gross_yield", {"target_gross_yield_percent": 8.0, "target_gross_yield_active": True})
L2 = PB.build_lists([B, C], CL)
leaked = sorted(r["row_id"] for r in L2["business_rows"] if r["key"] in PB.RENT_YIELD_MEMO_KEYS)
check(not leaked, "no target-yield row even when one Project is still on gross_yield", str(leaked))
rm = next((r for r in L2["business_rows"] if r["row_id"] == "module6:rent_setting_method"), None)
check(rm is not None and rm["differs"], "the rent METHOD difference itself is still reported")
check(any(r["row_id"] == "module6:discount_rate_percent" for r in L2["business_rows"]),
      "other Module 6 premises are still listed")

print("-- 4. comparison copy uses the settings shape 02 Evaluation saves")
dec = PB.default_decisions(L2)
dec["business"]["module6:annual_rent_per_m2"] = 28000.0
dec["business"]["module6:target_gross_yield_percent"] = 8.0  # as a pre-PATCH_007 book could hold
with tempfile.TemporaryDirectory() as td:
    src = Path(td) / "src.json"
    src.write_text(json.dumps(C), encoding="utf-8")
    before = copy.deepcopy(C)
    for label, source, pref in (("gross_yield source", C, 8.0), ("market_rent source (6.5 %)", B, 6.5)):
        cp = PB.build_copy(source, src, "book.json", "gid", "v1", L2, dec, "2026-09-24T00:00:00Z")
        st = cp["module_outputs"]["module6"]["_input_snapshot"]["settings"]
        check(st.get("rent_setting_method") == "market_rent", f"{label}: copy is on market_rent")
        check(st.get("target_gross_yield_active") is False, f"{label}: target_gross_yield_active is False")
        check(st.get("target_gross_yield_percent") == pref,
              f"{label}: the user's own preference is kept (Evaluation would turn null into 8.0)",
              str(st.get("target_gross_yield_percent")))
        check("stored_target_gross_yield_percent" not in st, f"{label}: no summary-only key written into settings")
    check(C == before, "the source Project is not modified")

print("-- 5. source guards")
ext = (ROOT / "comparison" / "extractor.py").read_text(encoding="utf-8")
check("m6.get('target_gross_yield_percent') or m6_settings.get('target_gross_yield_percent')" not in ext,
      "the 'or' fallback that revived the inactive yield is gone")

print()
if FAIL:
    print("[NG] PATCH_007 self-check FAILED:")
    for f in FAIL:
        print("   -", f)
    raise SystemExit(1)
print("PATCH_007_MARKET_RENT_YIELD_CONTRACT_PASS")
