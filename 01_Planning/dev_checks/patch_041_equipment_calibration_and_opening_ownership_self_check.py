# -*- coding: utf-8 -*-
"""PATCH_041 self-check.

(1) A JPY equipment package price that is already a 2026 market figure (an
    imported AI approximate-cost package, or a user price that replaced the
    database default) must not be recalibrated by the construction-method
    market factor.  The untouched database default must still be calibrated.
(2) Opening (windows/doors) supersession must be recomputed on every pass, must
    never leave a scope without a monetary owner, and must be stable across
    repeated passes.

Module 1 imports tkinter at module level, so its ownership method is extracted
and executed in isolation; the check therefore runs without a display server.
"""
import copy
import json
import math
import re
import sys
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import services.construction_cost_engine_v9_4 as E  # noqa: E402

FAIL = []


def check(ok, label, detail=""):
    if ok:
        print(f"  [OK]   {label}")
    else:
        FAIL.append(f"{label} :: {detail}")
        print(f"  [NG]   {label} :: {detail}")


print("PATCH_041 self-check")
DB = json.loads((ROOT / "data" / "construction_cost_database_v9_4.json").read_text(encoding="utf-8"))
default_hvac = float(DB["equipment_packages"]["hvac"]["default_cost_jpy"])

print("-- 1. which JPY equipment prices are current-market")
f = E._equipment_price_is_current_market
check(f("hvac", 2836560.0, "ai_approximate_cost_session_local_currency", DB) is True,
      "an imported AI package is current-market")
check(f("hvac", 2836560.0, "ui_local_currency", DB) is True,
      "a UI price that replaced the default is current-market")
check(f("hvac", default_hvac, "ui_local_currency", DB) is False,
      "the untouched UI default is NOT current-market (still calibrated)")
check(f("hvac", default_hvac, "database_default_jpy", DB) is False,
      "the database default is NOT current-market (still calibrated)")
check(f("hvac", 999.0, "database_default_jpy", DB) is False,
      "database_default_jpy is never treated as current-market, whatever its value")

print("-- 2. the calibration branch honours the rule")
src = (ROOT / "services" / "construction_cost_engine_v9_4.py").read_text(encoding="utf-8")
i_new = src.index("elif common_2004_enabled and _equipment_price_is_current_market(")
i_old = src.index("elif common_2004_enabled:\n            equipment_market_factor,equipment_market_source=_market_calibration_factor_2026(")
check(i_new < i_old, "the current-market branch is evaluated before the calibration branch")
check('"current_market_package_price_no_recalibration"' in src,
      "the bypass is recorded with its own calibration source label")

print("-- 3. opening supersession")
m1_src = (ROOT / "module1" / "app.py").read_text(encoding="utf-8")
s = m1_src.index("    def _annotate_quantity_aggregation_ownership(self, takeoff):")
e = m1_src.index("\n    def ", s + 10)
ns = {"json": json, "math": math, "re": re, "copy": copy, "unicodedata": unicodedata}
exec("class M:\n" + m1_src[s:e], ns)
M = ns["M"]
M._reconcile_mep_route_quantity_ownership = lambda self, t: t
M.__getattr__ = lambda self, n: (lambda *a, **k: (a[0] if a else {}))


def row(item, src_mode, **extra):
    r = {"item": item, "unit": "m2", "quantity": 55.74, "accepted_quantity": 55.74,
         "source_mode": src_mode, "evidence_status": "estimated",
         "quantity_display_state": "assumed_yellow", "downstream_use": "allowed_provisional",
         "downstream_quantity_eligible": True, "quantity_adoption_class": "assumed"}
    r.update(extra)
    return r


def owners(rows):
    out = {}
    for r in rows:
        if r["item"] in ("Exterior window glazing", "外壁窓ガラス"):
            out[r["item"]] = (r.get("aggregation_role") != "audit_only"
                              and r.get("downstream_quantity_eligible") is not False
                              and r.get("quantity_adoption_class") != "audit_only")
    return out


def run(rows, passes=3):
    tk = {"rows": copy.deepcopy(rows)}
    hist = []
    for _ in range(passes):
        tk = M()._annotate_quantity_aggregation_ownership(tk)
        hist.append(owners(tk["rows"]))
    return hist, tk["rows"]


# (a) the reported defect: equal priority, both rows carrying a stale supersession
stale = dict(aggregation_role="audit_only", downstream_quantity_eligible=False,
             quantity_adoption_class="audit_only", superseded_physical_quantity=True,
             supersession_reason="superseded_by_current_pdf_windows_owner",
             accepted_quantity_source="ai_final_chatgpt_review")
rows_a = [row("Exterior window glazing", "chatgpt final drawing-evidence re-check", **stale),
          row("外壁窓ガラス", "chatgpt final drawing-evidence re-check", **stale)]
hist, final = run(rows_a)
check(all(sum(h.values()) == 1 for h in hist),
      "equal-priority rows with stale supersession: exactly one owner on every pass", str(hist))
check(len({tuple(sorted(h.items())) for h in hist}) == 1,
      "the owner does not flip between passes", str(hist))

# (b) the normal case: a stronger current-PDF row owns, the other is superseded
rows_b = [row("Exterior window glazing", "elevation / opening area"),
          row("外壁窓ガラス", "current-pdf elevation")]
hist, _ = run(rows_b)
check(hist[-1] == {"Exterior window glazing": False, "外壁窓ガラス": True},
      "a stronger current-PDF row keeps ownership (existing behaviour preserved)", str(hist))

# (c) a single row never supersedes itself
hist, _ = run([row("外壁窓ガラス", "current-pdf elevation")])
check(hist[-1] == {"外壁窓ガラス": True}, "a lone opening row stays the owner", str(hist))

# (d) no strong row at all: nothing is superseded, nothing is revived
weak = [row("Exterior window glazing", "legacy", quantity_display_state="unknown_red", evidence_status="unresolved"),
        row("外壁窓ガラス", "legacy", quantity_display_state="unknown_red", evidence_status="unresolved")]
_, fr = run(weak)
check(all(not r.get("superseded_physical_quantity") for r in fr),
      "without any eligible owner, no row is marked superseded")

# (e) a row that is audit-only for its OWN reason can never become the owner
rows_e = [row("Exterior window glazing", "current-pdf elevation", downstream_use="audit_subtotal",
              aggregation_role="audit_only", downstream_quantity_eligible=False,
              quantity_adoption_class="audit_only"),
          row("外壁窓ガラス", "elevation / opening area")]
hist, fr = run(rows_e)
check(hist[-1]["Exterior window glazing"] is False,
      "an independently audit-only row is not promoted to owner", str(hist))
check(hist[-1]["外壁窓ガラス"] is True,
      "the remaining eligible row owns the scope", str(hist))

# (f) every gate field agrees on a superseded row
_, fr = run(rows_b)
sup = [r for r in fr if r.get("superseded_physical_quantity")]
check(sup and all(r.get("quantity_adoption_class") == "audit_only"
                  and r.get("downstream_quantity_eligible") is False
                  and r.get("aggregation_role") == "audit_only" for r in sup),
      "a superseded row is audit-only in every field the cost gate reads")
check(all("_opening_supersession_previously_applied" not in r for r in fr),
      "the transient tie-break marker is not persisted")

print("-- 4. the cost gate sees exactly one glass owner")
p = {"common": {"construction_method_id": "rc_frame", "scale_gfa_m2": 245.1},
     "module_outputs": {"module1": {"quantity_takeoff": {"rows": copy.deepcopy(rows_a)}}}}
p["module_outputs"]["module1"]["quantity_takeoff"] = M()._annotate_quantity_aggregation_ownership(
    p["module_outputs"]["module1"]["quantity_takeoff"])
q, prov, exc = E.extract_quantities(p, p["module_outputs"]["module1"], {})
check(abs(float(q.get("glass") or 0.0) - 55.74) < 1e-9,
      "glass enters Module 5 exactly once (55.74 m2, not 0 and not 111.48)", str(q.get("glass")))

print()
if FAIL:
    print("[NG] PATCH_041 self-check FAILED:")
    for x in FAIL:
        print("   -", x)
    raise SystemExit(1)
print("PATCH_041_EQUIPMENT_CALIBRATION_AND_OPENING_OWNERSHIP_PASS")
