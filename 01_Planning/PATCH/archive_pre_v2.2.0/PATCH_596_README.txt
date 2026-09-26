AZRAS Planning PATCH 596

Reported error:
  name 'carried_gap_keys' is not defined

Root cause:
PATCH 595 added the omitted-scope continuity feature in two incomplete pieces.
The call that creates `carried_gap_keys` was accidentally inserted into
`_stage_ai_takeoff_payload()` (first-round AI collection), where `rows`,
`unresolved`, and `new_rows` do not belong. Meanwhile,
`_apply_ai_takeoff_final_review()` used `len(carried_gap_keys)` in its summary
without defining the variable there.

Correction:
- Remove the PATCH 595 carry-forward call from first-round staging.
- Execute it only in `_apply_ai_takeoff_final_review()`.
- Define `carried_gap_keys` before the FINAL summary.
- Keep PATCH 595's intended rule: a previously discovered omitted physical scope
  cannot disappear merely because the FINAL JSON omitted it.

The exact NameError path was regression-checked, together with the previous five
PATCH range and related critical invariants.
