"""Regression check for PATCH_027: Module 1's AZRAS-only mandatory structural
scope coverage rows (module1/app.py _ensure_azras_mandatory_scope_coverage_rows,
PATCH_576) must never be injected into -- and must be cleaned out of -- a
project whose construction_method_id is not exactly "azras", including when
that field is empty/unset.
"""
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))
sys.path.insert(0, str(_ROOT / "module1"))

import app as m1

obj = object.__new__(m1.Module1App)

def check(method_id, existing_rows, expect_injected, expect_stale_removed):
    obj.project = {"common": {"construction_method_id": method_id}}
    takeoff = {"rows": [dict(r) for r in existing_rows]}
    out = obj._ensure_azras_mandatory_scope_coverage_rows(takeoff)
    keys = [r.get("coverage_gap_key") for r in out.get("rows") or [] if isinstance(r, dict)]
    has_azras_keys = any(str(k or "").startswith("azras_") for k in keys)
    if expect_injected and not has_azras_keys:
        print(f"[NG] method={method_id!r}: expected AZRAS rows to be injected, found none")
        raise SystemExit(1)
    if not expect_injected and has_azras_keys:
        print(f"[NG] method={method_id!r}: AZRAS rows present when they must not be")
        raise SystemExit(1)
    real_items = [r.get("item") for r in out.get("rows") or []
                  if isinstance(r, dict) and not str(r.get("coverage_gap_key") or "").startswith("azras_")]
    if "Foundation concrete" not in real_items:
        print(f"[NG] method={method_id!r}: a real user row was lost")
        raise SystemExit(1)

stale_row = {
    "item": "AZRAS internal RC party-wall concrete",
    "coverage_gap_required": True,
    "coverage_gap_key": "azras_internal_rc_party_wall_concrete",
    "quantity": 0.0,
}
real_row = {"item": "Foundation concrete", "quantity": 10.0}

# 1) Empty/unset construction_method_id (the reported bug) with a stale row present.
check("", [real_row, stale_row], expect_injected=False, expect_stale_removed=True)

# 2) An ordinary non-AZRAS method id.
check("wood_frame_wall_2x6", [real_row], expect_injected=False, expect_stale_removed=False)

# 3) Explicit "azras" -- injection must still happen (no regression).
check("azras", [real_row], expect_injected=True, expect_stale_removed=False)

print("AZRAS_SCOPE_LEAKAGE_REGRESSION_PASS")
