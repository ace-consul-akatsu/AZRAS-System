PATCH_000 — AZRAS Planning v2.2.0 baseline (patch numbering reset)

This is the first patch of the v2.2.0 baseline. Prior history (PATCH_1
through PATCH_630, plus PATCH_631-634 applied earlier in this same
audit) is preserved for reference under PATCH/archive_pre_v2.2.0/ and is
not deleted, but is no longer the active patch ledger.

Why re-baseline now:
The prior v1.0.x line reached PATCH_630 (its own internal notes had
already flagged, around PATCH_400, that isolated single-symptom patching
without cross-module regression testing risks one fix silently breaking
an unrelated part of the codebase). This session's audit found exactly
that pattern in practice: bugs in Module 5 (missing hard-block confirm),
Module 9/10 (regional mislabeling), and two silently-swallowed
NameErrors in Module 1/5 that had likely been present for many prior
patches without being caught.

What changed to reach this baseline (previously issued as PATCH_631-634
under the old numbering, now folded into this single v2.2.0 baseline):
- Module 5: save_output() now asks for confirmation (messagebox.askyesno)
  instead of unconditionally blocking the save when monetary
  gaps/unpriced cost lines remain.
- Module 9/10: _update_module0_location() now also replaces
  common["project_location"], fixing every generated region showing the
  base project's original address in Module 10's legend/tables.
- Module 9: RegionalCoefficientManager.refresh() no longer goes blank if
  one city entry fails; failures are isolated per-row, and an unexpected
  top-level failure now shows a dialog instead of failing silently.
- module5/app.py: added a missing "import re" (re.sub() was called in
  three places without it, crashing regional-cost JSON save/template
  export every time).
- module1/app.py: fixed two NameErrors (undefined "items" in
  _stage_ai_takeoff_payload, undefined "analysis" in
  _build_result_from_staged_ai_takeoff) that were silently swallowed by
  surrounding try/except blocks. The AI-reimport facade-surface publish
  feature and the canonical-contract normalization on the staged-AI-
  takeoff rebuild path had never actually executed successfully before
  this fix.
- Added dev_checks/ (5 re-runnable regression scripts), modeled on AZRAS
  Evaluation's dev_checks/:
    - all_python_sources_compile_self_check.py
    - pyflakes_undefined_names_self_check.py
    - language_combobox_liveness_self_check.py
    - regional_project_location_self_check.py
    - module5_cost_save_gate_self_check.py
  All 5 pass as of this baseline.

Going forward:
Run every script in dev_checks/ before packaging any new patch. New
patches are numbered PATCH_002 onward; each should get its own
PATCH_NNN_README.txt in this folder describing what changed and why, and
should re-run the full dev_checks/ suite (adding a new check to the
suite when a new bug class is discovered, as was done in this baseline).
