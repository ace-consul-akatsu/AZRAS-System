PATCH_002 — module1/app.py: harden AI takeoff request template against cross-provider schema drift

Background: Gemini's actual response to a 260915_RC_Rahmen_Sample R1 request
deviated from the AZRAS_AI_TAKEOFF schema in several ways:
- canonical_language: "ja" instead of the required fixed "en"
- project: an object with name/architect/architect_in_charge instead of the
  required flat string project identifier
- takeoff_items rows using invented field names (element_category,
  element_type, specifications) and short member-mark local_id values
  (e.g. "F1", "1C1") instead of the required schema fields and integer
  local_id
- an analysis object containing only ai_reviewer/timestamp_utc, omitting
  drawing_coverage/completeness_audit/quantity_resolution_audit/completion_gate
- (in an earlier response) explaining in prose why it could not create a
  downloadable file before providing the JSON, instead of returning the raw
  JSON only

Fix: _ai_takeoff_request_text() in module1/app.py (the function that
generates AZRAS_AI_TAKEOFF_REQUEST.txt for every R1 round) now includes a
new [CROSS-PROVIDER SCHEMA HARDENING] section, inserted immediately before
[REQUIRED JSON STRUCTURE] so it is the last thing the reviewing AI reads
before writing its output. It names Gemini's specific observed failures as
WRONG/RIGHT pairs and closes with an instruction to re-compare the AI's own
output key-by-key against [REQUIRED JSON STRUCTURE] before returning.

Verified by rendering _ai_takeoff_request_text() standalone: the new
section renders with {project_name} correctly substituted and no leftover
template braces.

This is a prompt-wording change only; no schema, validation, or takeoff
calculation logic was changed.

Files changed:
- module1/app.py (_ai_takeoff_request_text only)
