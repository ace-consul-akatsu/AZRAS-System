# -*- coding: utf-8 -*-
"""PATCH_004 self-check (03 Compare).

(1) A Module 10 snapshot whose envelope disagrees with the saved Module 2 result
    is stale and must not be presented as the Project's current 8760 energy.
(2) Evaluation results saved before the Planning input they consume are stale
    and must be reported.
(3) The currency shown for a cost is the currency the cost was priced in.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from comparison import extractor as X  # noqa: E402

FAIL = []


def check(ok, label, detail=""):
    if ok:
        print(f"  [OK]   {label}")
    else:
        FAIL.append(f"{label} :: {detail}")
        print(f"  [NG]   {label} :: {detail}")


def project(snap_light_u=0.13, m2_light_u=0.13, light_area=82.88, rc_u=0.13, rc_area=126.76):
    return {
        "regional_analysis": {"module10_snapshot": {
            "annual": {"total_use_kWh": 23206.9},
            "monthly": [{"total_use_kWh": 1000.0}] * 12,
            "model_config": {"u_light_wall_W_m2K": snap_light_u, "light_exterior_area_m2": light_area,
                             "u_rc_wall_W_m2K": rc_u, "rc_exterior_area_m2": rc_area},
        }},
        "module_outputs": {"module2": {
            "floor_thermal_breakdown": {"light_wall_u_W_m2K_used": m2_light_u, "light_wall_area_m2_used": light_area,
                                        "rc_wall_u_W_m2K_used": rc_u, "rc_wall_area_m2_used": rc_area},
            "settings": {},
        }},
    }


print("PATCH_004 self-check")
print("-- 1. envelope staleness of the 8760 snapshot")
p_ok = project()
check(X.snapshot_envelope_mismatches(p_ok) == [], "a consistent snapshot raises nothing")
check(X._snapshot(p_ok) != {}, "a consistent snapshot is still used")

p_bad = project(snap_light_u=5.88235294117647, m2_light_u=0.1303780964797914)
mm = X.snapshot_envelope_mismatches(p_bad)
check(len(mm) == 1 and mm[0]["component"] == "light_wall", "the reported light-wall case is detected", str(mm))
check(mm and mm[0]["snapshot_conductance_W_K"] > 480 and mm[0]["module2_conductance_W_K"] < 12,
      "the mismatch is reported as conductance (U x A)", str(mm))
check(X._snapshot(p_bad) == {}, "a stale snapshot is rejected, exactly as PATCH 044 rejects lost passive inputs")

p_zero = project(snap_light_u=5.88, m2_light_u=0.10, light_area=0.0)
check(X.snapshot_envelope_mismatches(p_zero) == [],
      "a U-value difference on a zero-area component is not a false alarm")

p_tiny = project(snap_light_u=0.1304, m2_light_u=0.1303780964797914)
check(X.snapshot_envelope_mismatches(p_tiny) == [], "a rounding-level difference is tolerated")

p_missing = project(); del p_missing["module_outputs"]["module2"]["floor_thermal_breakdown"]
check(X.snapshot_envelope_mismatches(p_missing) == [] and X._snapshot(p_missing) != {},
      "a Module 2 result without a breakdown (older file) is not rejected")

print("-- 2. stale Evaluation results")
def ms(**t):
    return {"module_status": {k: {"status": "saved", "updated_at": v} for k, v in t.items()}}
fresh = ms(module2="2026-09-19T00:03:23", module5="2026-09-20T08:46:03",
           module3="2026-09-20T09:02:31", module4="2026-09-20T09:02:31",
           module6="2026-09-20T09:02:44", module7="2026-09-20T09:02:37")
check(X.stale_downstream_results(fresh) == [], "results saved after their inputs are not stale")
rc = ms(module2="2026-09-21T04:15:01", module5="2026-09-21T04:14:43",
        module3="2026-09-20T09:05:38", module4="2026-09-20T09:05:38",
        module6="2026-09-20T09:06:27", module7="2026-09-20T09:05:48")
got = {(s["input_module"], s["result_module"]) for s in X.stale_downstream_results(rc)}
check(got == {("module2", "module3"), ("module2", "module4"), ("module2", "module6"), ("module2", "module7"),
              ("module5", "module6"), ("module5", "module7")},
      "the reported RC case lists every stale result", str(sorted(got)))
notcalc = ms(module2="2026-09-20T04:53:22", module5="2026-09-20T09:09:23", module6="2026-09-20T09:10:51")
notcalc["module_status"]["module3"] = {"status": "not_calculated", "updated_at": None}
check(X.stale_downstream_results(notcalc) == [],
      "a not-calculated module is not mislabelled as stale")

print("-- 3. currency comes from the pricing modules")
src = (ROOT / "comparison" / "extractor.py").read_text(encoding="utf-8")
check("'currency':str(m5.get('currency') or m6.get('currency') or identity.get('currency')" in src,
      "Module 5/6 currency takes precedence over the Module 0 declaration")
check("'currency_conflict'" in src and "'declared_identity_currency'" in src,
      "a declaration/calculation mismatch is carried out for reporting")

print("-- 4. the warning is wired and changes nothing")
main = (ROOT / "main.py").read_text(encoding="utf-8")
check("'保存データの整合性確認':'Saved Data Consistency Check'" in main, "the dialog title is translated")
for key in ("snapshot_envelope_mismatches", "stale_downstream_results", "currency_conflict"):
    check(key in main, f"the load-time warning reports {key}")

print()
if FAIL:
    print("[NG] PATCH_004 self-check FAILED:")
    for f in FAIL:
        print("   -", f)
    raise SystemExit(1)
print("PATCH_004_SNAPSHOT_STALENESS_AND_CURRENCY_PASS")
