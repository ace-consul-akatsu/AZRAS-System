PATCH_021 — cleanup: duplicate translation key, unused import/variables; added dev_checks/

No crash-causing bugs were found in AZRAS Compare (unlike Planning/
Evaluation). pyflakes flagged three harmless dead-code issues, cleaned up
here:

1. main.py: TEXT_EN had two entries for the same Japanese key
   ('4. 200年間CO₂比較グラフ' and '5. 200年間投資回収比較グラフ'), each
   with a slightly different English wording. Python dict literals keep
   only the last value for a repeated key, so the first ("...Comparison" /
   "...Recovery") was always silently discarded in favor of the second
   ("...Comparison Graph" / "...Recovery Graph"). Both tab label and page
   heading use the identical Japanese source string in the UI code, so this
   never caused inconsistent display — the earlier entries were simply
   unreachable. Removed the discarded earlier entries; the effective
   English text (the "...Graph" wording) is unchanged.

2. comparison/extractor.py:
   - Removed unused "from datetime import datetime" (not referenced
     anywhere in the file).
   - Removed the unused "wanted" set in _parse_explicit_timeline(): it
     precomputed a lowercased alias set but the function always matched
     aliases directly via value_aliases a few lines below instead.
   - Removed the unused "m4 = _saved_module(d,'module4') or {}" in
     extract_core_project(): Module 4's saved output is fetched but never
     read anywhere in the function — 200-year CO2 is obtained separately
     via the _co2(d) helper.

Also added dev_checks/language_combobox_liveness_self_check.py (ported
from the Planning/Evaluation audit in this session) — verified clean: no
instance of the Module 4/6 (Evaluation) "StringVar garbage-collected,
combobox renders blank" bug class exists in Compare.

Files changed:
- main.py (TEXT_EN duplicate keys)
- comparison/extractor.py (unused import/variables)
- dev_checks/language_combobox_liveness_self_check.py (new)
