PATCH_006 — module5/app.py: show/save/load a changelog of unit-cost changes on each AI-JSON import

Request: from Module 5's AI cost workflow (② ChatGPT調査JSON取込 / ④ 各AIの
JSONを順次取込 / ⑥ ChatGPT再確認JSON取込 → 終了 -- all three call the same
import_ai_cost_json()), show what actually changed in the adopted unit
costs on each import step, and allow saving that list and loading it back
later.

Added:
- _build_ai_cost_changelog(previous_adopted, previous_audit, new_adopted,
  new_audit, scope): diffs the unit-cost adoption state captured
  immediately before vs. immediately after one import call. Classifies
  each cost_item_key that changed as new / price_changed / status_changed
  / removed (unchanged items are omitted from the list). Uses the
  existing _ai_cost_candidate_total() helper so the "price" being compared
  is the same effective total already shown elsewhere in Module 5.
- _show_ai_cost_changelog(rows, session_meta): a Toplevel window with a
  Treeview listing the changed items (item name, change type, before/after
  price, before/after status, before/after reviewer), plus:
    - "変更履歴を保存" (Save changelog): writes
      <Project folder>/AI_Cost_Changelog/<UTC timestamp>_AZRAS_AI_COST_CHANGELOG_<project>.json
      (schema AZRAS_AI_COST_CHANGELOG_V1), auto-suffixing _2/_3/... on a
      same-minute collision, matching the existing save-file convention
      used elsewhere in this module/Module 2.
    - "変更履歴を読込" (Load changelog): opens a previously saved changelog
      JSON and repopulates the same list -- usable independently of
      whether an import just ran, so a saved changelog can be reviewed at
      any later time.
- import_ai_cost_json() now captures previous_adopted/previous_audit
  (deep copies of the unit-cost overlay's prior state) before running the
  reconciliation, and opens the changelog window automatically right after
  its existing summary messagebox, for every one of the ②/④/⑥ import
  steps (they all funnel through this same function).

Verified (Xvfb, headless):
- _build_ai_cost_changelog correctly classifies a price change
  (20,000->24,200, reviewer chatgpt->claude) and a brand-new price
  (unresolved->108,000) from synthetic before/after data.
- The changelog window renders with the correct rows and both buttons.
- The Save button writes a well-formed AZRAS_AI_COST_CHANGELOG_V1 JSON
  file to the expected path.
- The Load button (tested with filedialog.askopenfilename monkeypatched
  to avoid a headless modal) correctly reads that file back and
  repopulates the treeview from an initially-empty list.

pyflakes: one new issue was introduced and fixed during this patch
(an f-string with no placeholders on the status label); the final diff
introduces zero new pyflakes warnings beyond this file's pre-existing
baseline. All dev_checks/ scripts still pass.

Files changed:
- module5/app.py (_ai_cost_changelog_dir, _build_ai_cost_changelog,
  _show_ai_cost_changelog added; import_ai_cost_json updated to capture
  the before-state and open the changelog window)
