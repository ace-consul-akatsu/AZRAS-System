# -*- coding: utf-8 -*-
"""PATCH_006 self-check (02 Evaluation, Module 6).

In market-rent mode the gross yield is a RESULT (rent x GFA / initial
investment), not an input.  It must be calculated and saved per Project, shown
in the yield field read-only, and must never overwrite the user's own target
yield or be submitted as the target.  Tkinter is not required: the Module 6
methods are extracted and run against small stand-ins.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

FAIL = []


def check(ok, label, detail=""):
    if ok:
        print(f"  [OK]   {label}")
    else:
        FAIL.append(f"{label} :: {detail}")
        print(f"  [NG]   {label} :: {detail}")


print("PATCH_006 self-check")
print("-- 1. engine")
src = (ROOT / "services" / "investment_engine_v9_5.py").read_text(encoding="utf-8")
check("implied_gross_yield_percent=(base_gross_rent/initial_total*100.0) if initial_total else None" in src,
      "the derived yield is rent / initial investment")
check('"implied_gross_yield_percent":implied_gross_yield_percent,' in src, "the derived yield is saved in the summary")
check('settings["implied_gross_yield_percent"]=implied_gross_yield_percent' in src,
      "the derived yield is saved with the resolved settings")
check(src.count('settings["target_gross_yield_percent"]=target_gross_yield_percent') == 1,
      "the user's target is still stored exactly as entered (no second write)")

print("-- 2. Module 6 UI behaviour")
ui = (ROOT / "module6" / "app.py").read_text(encoding="utf-8")


def grab(name):
    s = ui.index(f"    def {name}(self")
    return ui[s:ui.index("\n    def ", s + 10)]


body = grab("_implied_yield_from_result") + grab("_apply_yield_field_mode") + grab("settings")
ns = {}
exec("class M:\n" + body, ns)
M = ns["M"]


class Var:
    def __init__(self, v=""):
        self.v = v

    def get(self):
        return self.v

    def set(self, v):
        self.v = v


class W:
    def __init__(self):
        self.cfg = {}

    def configure(self, **k):
        self.cfg.update(k)


class I18N:
    language = "ja"


def make(result=None):
    m = M()
    m.i18n = I18N()
    m.vars = {"target_gross_yield_percent": Var("8.0"), "annual_rent_per_m2": Var("15000"),
              "loan_term_years": Var("30"), "total_dwelling_units": Var("3"),
              "partial_renewal_affected_dwelling_units": Var("1")}
    m.rent_setting_method = Var("gross_yield")
    m.region_id = Var("JP_NAGOYA")
    m.use_loan = Var(False)
    m.yield_entry = W()
    m.yield_label = W()
    m._user_target_yield = "8.0"
    m._yield_field_shows_implied = False
    m.result = result
    return m


market_result = {"summary": {"rent_setting_method": "market_rent", "implied_gross_yield_percent": 9.1296,
                             "year1_gross_yield_percent": 9.1296}}
m = make()
m.rent_setting_method.set("market_rent")
m._apply_yield_field_mode()
check(m.vars["target_gross_yield_percent"].get() == "", "before the first calculation the derived field is blank",
      m.vars["target_gross_yield_percent"].get())
check(m.yield_entry.cfg.get("state") == "readonly", "the field is read-only in market-rent mode")
check("市場家賃から算出" in m.yield_label.cfg.get("text", ""), "the label says the value is derived")
s = m.settings()
check(s["target_gross_yield_percent"] == 8.0, "a blank derived field still submits the user's target",
      str(s["target_gross_yield_percent"]))

m.result = market_result
m._apply_yield_field_mode()
check(m.vars["target_gross_yield_percent"].get() == "9.13", "after calculation the derived yield is shown",
      m.vars["target_gross_yield_percent"].get())
s = m.settings()
check(s["target_gross_yield_percent"] == 8.0, "the displayed derived yield is never submitted as the target",
      str(s["target_gross_yield_percent"]))

m.rent_setting_method.set("gross_yield")
m._apply_yield_field_mode()
check(m.vars["target_gross_yield_percent"].get() == "8.0", "switching back restores the user's target unchanged",
      m.vars["target_gross_yield_percent"].get())
check(m.yield_entry.cfg.get("state") == "normal", "the field is editable again in gross-yield mode")
check("目標表面利回り" in m.yield_label.cfg.get("text", ""), "the label returns to target yield")

m.vars["target_gross_yield_percent"].set("7.5")
m.rent_setting_method.set("market_rent")
m._apply_yield_field_mode()
m.rent_setting_method.set("gross_yield")
m._apply_yield_field_mode()
check(m.vars["target_gross_yield_percent"].get() == "7.5", "a target edited before switching is preserved",
      m.vars["target_gross_yield_percent"].get())

gy_result = {"summary": {"rent_setting_method": "gross_yield", "implied_gross_yield_percent": 8.0}}
m = make(gy_result)
m.rent_setting_method.set("market_rent")
m._apply_yield_field_mode()
check(m.vars["target_gross_yield_percent"].get() == "",
      "a gross-yield result is not shown as a market-rent yield (it would only echo the target)")

print("-- 3. Compare is not connected")
for path in (ROOT.parent / "03_Compare_04" / "comparison" / "extractor.py",
             ROOT.parent / "03_Compare_04" / "main.py"):
    if path.exists():
        check("implied_gross_yield" not in path.read_text(encoding="utf-8"),
              f"{path.parent.name}/{path.name} does not read the derived yield")
disc = src[src.index('"revenue_basis_disclosure"'):src.index('"revenue_basis_disclosure"') + 1800]
check("implied_gross_yield" not in disc, "the PATCH_005 comparison disclosure does not carry the derived yield")

print()
if FAIL:
    print("[NG] PATCH_006 self-check FAILED:")
    for f in FAIL:
        print("   -", f)
    raise SystemExit(1)
print("PATCH_006_MARKET_RENT_DERIVED_YIELD_PASS")
