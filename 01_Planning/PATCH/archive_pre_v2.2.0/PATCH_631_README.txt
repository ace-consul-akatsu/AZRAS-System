PATCH_631 — Module 5 save-gate: allow provisional save with confirmation

Problem:
Module 5 (Construction Cost) save_output() unconditionally raised a
ValueError and blocked saving whenever any monetary gap, unpriced cost
line, or construction_cost_is_partial condition existed. This made it
impossible to save a Module 5 result while any AZRAS-derived item
(e.g. AZRAS RC外壁フェノールフォーム, AZRAS屋根仕上材 etc.) remained
in "未単価・個別単価" status, even when the user intentionally wanted
to proceed with a provisional/assumed total.

Fix:
In module5/app.py save_output(), replaced the hard block (raise
ValueError) with a messagebox.askyesno confirmation dialog that states
the monetary gap count and unpriced line count, and explains that these
items are excluded from the total/unit cost and will be carried forward
as provisional to downstream modules (Evaluation/Compare, etc.). If the
user answers "No", the save is cancelled (function returns without
saving). If "Yes", the save proceeds exactly as before.

No change to:
- module1 → module5 integrity check (quantity_to_cost_line_integrity_audit
  must still be "pass")
- module1 cost-dependency fingerprint check
- construction_cost_is_partial / unpriced_cost_lines flags themselves,
  which continue to be carried into the saved result and displayed by
  downstream modules exactly as before.

Files changed:
- module5/app.py (save_output method only)
