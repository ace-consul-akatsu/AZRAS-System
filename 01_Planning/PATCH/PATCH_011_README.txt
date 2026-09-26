PATCH_011 — module5/app.py: organize the construction-cost AI workflow into the same 4-folder layout as Module 1's takeoff workflow

Request: use the same folder structure already used by Module 1's AI
takeoff round (<Project>/R1/01_Request for Estimate, 02_AI response,
03_Request for Recheck, 04_Final determination) for Module 5's
construction-cost AI request/response workflow too.

Added _ai_cost_round_root() / _ensure_ai_cost_round_layout(), mirroring
Module 1's _ai_round_root()/_ensure_ai_round_layout() exactly in shape,
rooted at <Project folder>/AI_CostProvider/R1 (kept as its own root
rather than sharing Module 1's R1 folder, since takeoff and cost are
different AI exchanges with different schemas and should not be mixed in
the same folder).

Redirected each existing save/browse location to the matching subfolder:
- show_ai_cost_request (button (1), primary ChatGPT research request) and
  show_ai_cost_review_request (button 3, other-AI independent-review
  request) -> 01_Request for Estimate (both are part of the initial
  estimate-gathering round, sent to every AI, matching Module 1's "send
  to every AI" R1/01 convention).
- show_ai_cost_recheck_request (button 5, ChatGPT final re-check request)
  -> 03_Request for Recheck.
- import_ai_cost_json's file-browse dialog (buttons 2/4/6) now opens in
  02_AI response by default instead of the flat AI_CostProvider folder.

Added _copy_ai_cost_json_to_round_folder(): a best-effort (never-raising)
copy helper. import_ai_cost_json now copies every newly-imported AI
cost-response JSON into R1/02_AI response, mirroring Module 1's own
per-project evidentiary record-keeping of each independent AI response
(this does not change the existing "no shared/global price cache"
design -- that principle concerns a cross-project database, not a
per-project copy of the files already being imported). When the imported
session's research_role is "primary_recheck" (the ChatGPT final re-check
response, imported via button 6), the same file is additionally copied
into 04_Final determination, since that import is the one that becomes
the formally adopted price basis -- matching Module 1's use of
04_Final determination for the formally adopted takeoff JSON.

Verified: _ensure_ai_cost_round_layout() creates all four folders at the
expected paths under a synthetic project folder; _copy_ai_cost_json_to_round_folder
correctly copies a synthetic JSON file into the responses folder.

pyflakes: no new issues. All dev_checks/ scripts still pass.

Files changed:
- module5/app.py (_ai_cost_round_root, _ensure_ai_cost_round_layout,
  _copy_ai_cost_json_to_round_folder added; show_ai_cost_review_request,
  show_ai_cost_recheck_request, _save_ai_cost_request_txt,
  import_ai_cost_json updated to use the new folder layout)
