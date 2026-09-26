PATCH_634 — add dev_checks/ regression suite for Planning; fix 2 real bugs it found

Background: modeled on AZRAS Evaluation's dev_checks/ folder (6 small,
re-runnable self-check scripts). Planning had no equivalent — only
PATCH_NNN_REGRESSION.json result records (manually-confirmed checklists,
not re-runnable test code) and PATCH_NNN README/SELF_CHECK text files.

Added dev_checks/ (5 scripts, run individually with `python dev_checks/<name>.py`,
each prints a *_PASS sentinel and exits 0 on success, exits 1 with [NG] lines
on failure):

1. all_python_sources_compile_self_check.py
   ast.parse() every .py file in the package. Equivalent to the old
   "all_NN_python_sources_compile" line seen in past REGRESSION.json files,
   but actually re-runnable.

2. pyflakes_undefined_names_self_check.py
   Runs pyflakes across every source file and fails on any "undefined name"
   (F821) finding. Found two REAL, previously-unknown bugs (fixed in this
   patch, see below).

3. language_combobox_liveness_self_check.py
   Static check for the Module 4/Module 6 (Evaluation) bug class: a
   Combobox's textvariable StringVar assigned to a local variable, whose
   <<ComboboxSelected>> handler doesn't reference it and nothing else keeps
   it alive, gets garbage-collected after build() returns, unsetting the
   underlying Tcl variable and leaving the combobox blank. Pairs each
   Combobox with its own textvariable and its own bind() handler (an
   earlier draft of this script conflated all StringVars/handlers in a
   whole build() method and produced 16 false positives across
   module0/module1/module2/module5/core — all confirmed false on inspection
   once the script was corrected to resolve named nested-function handlers,
   not just inline lambdas). Current result: PASS, no real instances found
   in Planning.

4. regional_project_location_self_check.py
   Regression test for PATCH_632 (Module 9/10 showed the same base-project
   address for every generated region). Calls
   regional_analysis.project_generator._update_module0_location() directly
   with synthetic cities and asserts project_location is replaced per city.

5. module5_cost_save_gate_self_check.py
   Regression test for PATCH_631 (Module 5 save gate). Source-level check
   that save_output() still uses messagebox.askyesno for incomplete-cost
   confirmation and has not reverted to a hard "raise ValueError" block.

Real bugs found by (2) and fixed in this patch:
- module5/app.py: used re.sub(...) in three places (regional-cost JSON
  filename sanitization, template export) without ever importing the `re`
  module. Any save on those paths raised NameError. Added `import re`.
- module1/app.py, _stage_ai_takeoff_payload(): referenced an undefined
  `items` variable (only exists in unrelated, larger functions elsewhere in
  the file). Always raised NameError, silently swallowed by a surrounding
  try/except, so the PATCH_393 "publish AI-imported facade surfaces into an
  already-analysed result" feature has never actually run. Now passes []
  explicitly instead of the undefined name.
- module1/app.py, _build_result_from_staged_ai_takeoff(): referenced an
  undefined `analysis` variable when calling
  _apply_module1_canonical_contract(analysis, takeoff, performance). Always
  raised NameError, silently caught, so performance was always reset to
  _empty_ai_performance() instead of using the value just computed by
  calculate_performance() on this line. Now derives analysis from
  self.result.get("drawing_analysis") (falling back to {}), matching the
  working pattern already used at the equivalent manual-recalculation call
  site elsewhere in this file.

Files changed:
- module5/app.py (added `import re`)
- module1/app.py (_stage_ai_takeoff_payload, _build_result_from_staged_ai_takeoff)
- dev_checks/ (5 new files)
