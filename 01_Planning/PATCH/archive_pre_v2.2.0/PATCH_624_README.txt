AZRAS Planning PATCH 624

Cause found
- Reported by the developer: Gemini's response to an AZRAS AI takeoff request
  wrapped the entire reply inside an outer key literally named
  "AZRAS_AI_TAKEOFF" (i.e. {"AZRAS_AI_TAKEOFF": {"metadata":..., ...}}),
  omitted the takeoff_items array entirely (returned only drawing
  title-block/spec text, no quantities), and used a malformed
  required_filename missing the project's date prefix.
- Gemini's own stated root cause: it did not fully parse the schema/manifest
  files bundled inside the request ZIP and fell back to a generic
  summary-style wrapper.
- AZRAS-side gap identified from this: AZRAS_AI_START_R1.txt (the first, and
  possibly only, file some AI reviewers reliably read before opening the
  accompanying ZIP) stated "Root schema MUST be exactly AZRAS_AI_TAKEOFF"
  but did not explicitly say the top-level JSON keys must be flat, did not
  explicitly require a takeoff_items array, and did not explicitly forbid
  wrapping the response in an outer key named after the schema value. This
  was a real gap in the request design, not the AI's competence.

Behavior
- module1/app.py: the START.txt's "HARD AZRAS OUTPUT CONTRACT" section now
  explicitly lists the exact top-level key set (schema, schema_version,
  canonical_language, canonical_schema_version, project, required_filename,
  analysis, building_profile, takeoff_items), explicitly states that
  "schema" is a string value and not an outer wrapper key name, and
  explicitly mandates a non-empty takeoff_items array with one row per
  mandatory PRE_TAKEOFF local_id.
- This is a defensive redundancy: the full requirement was already present
  in the request ZIP's AZRAS_AI_TAKEOFF_REQUEST.txt (which includes a
  complete structural example). The change makes the same requirement
  recoverable from the single START.txt file alone, independent of whether
  a given AI reviewer fully parses every file inside the ZIP.

Verified
- python -m py_compile passes for module1/app.py.
- The generated START.txt (manually re-rendered) contains the new
  contract text with no f-string/formatting errors.

Not changed in this patch
- The request ZIP's own AZRAS_AI_TAKEOFF_REQUEST.txt, response template,
  and metadata schema are unchanged. No PRE_TAKEOFF generation, quantity
  calculation, or import/validation logic changed.
