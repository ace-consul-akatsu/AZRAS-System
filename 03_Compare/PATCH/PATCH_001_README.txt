PATCH_001 — AZRAS Compare v2.2.0 baseline (patch numbering reset)

This is the first patch of the v2.2.0 baseline. Prior history (PATCH_16
through PATCH_20, plus the cleanup issued earlier in this same audit as
"PATCH_021" under the old numbering) is preserved for reference under
PATCH/archive_pre_v2.2.0/ and is not deleted, but is no longer the
active patch ledger.

Unlike Planning/Evaluation, no crash-causing bugs were found in Compare
during this audit. What changed to reach this baseline (previously
issued as PATCH_021 under the old numbering, now folded into this single
v2.2.0 baseline):
- main.py: removed a duplicate translation-dictionary key (TEXT_EN had
  two entries for the same Japanese source string with slightly
  different English wording; Python dict literals silently keep only the
  last one, so the earlier entry was dead code). No visible behavior
  change — the effective English text is unchanged.
- comparison/extractor.py: removed an unused import (datetime.datetime)
  and two unused local variables (wanted, m4) flagged by pyflakes. No
  behavior change.
- Added dev_checks/language_combobox_liveness_self_check.py (ported from
  the Planning/Evaluation audit in this same session). Confirmed clean:
  Compare does not have the Module 4/6 (Evaluation) "StringVar
  garbage-collected, combobox renders blank" bug class.

Going forward:
New patches are numbered PATCH_002 onward; each should get its own
PATCH_NNN_README.txt in this folder. Run
dev_checks/language_combobox_liveness_self_check.py and a plain
`python -m pyflakes` pass across the package before every future patch.
