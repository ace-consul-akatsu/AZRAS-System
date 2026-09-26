AZRAS Planning PATCH 590

Human Review compound-question regression correction

Observed defect
AZR-0001 displayed:
  AZRAS exterior-wall system area allocation unresolved
but only one generic approved-value field was available.

Root cause
The multi-answer recognizer preferred canonical_item over item.
For the current row, canonical_item was the placeholder:
  English canonical migration unresolved for item; see source_text_original.item
That placeholder hid the real exterior-wall allocation label, so the UI fell back
to one generic approved_quantity field.

Correction
AZR-0001 is now always rendered as two independent answers when the row evidence
identifies exterior-wall system allocation:
  AZR-0001-1  RC exterior wall area       m2
  AZR-0001-2  2x6 exterior wall area      m2

Formal apply is rejected unless BOTH quantities have been answered.
The final human-review decision remains one structured allocation decision with:
  rc_exterior_wall_area_m2
  timber_exterior_wall_area_m2

The audit target label also falls back to the real row item when canonical_item is
only a migration placeholder.
