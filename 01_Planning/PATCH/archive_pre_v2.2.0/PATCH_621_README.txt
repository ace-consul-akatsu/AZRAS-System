AZRAS Planning PATCH 621 (consolidated)

Delivered as a full replacement ZIP (v1.0.621), not a diff PATCH, per the
new delivery method. This single number consolidates three rounds of
fixes made in the same review pass:

1. AI-Takeoff contract messages (module1/app.py)
   - New _AI_CONTRACT_ISSUE_LABELS / _AI_CONTRACT_FALLBACK_REASON_LABELS
     tables (ja/en) and _humanize_ai_contract_issues() /
     _humanize_ai_contract_fallback_reason() helpers.
   - The schema-missing rejection message, the AI-identity hard-rejection
     message, and the "collected as evidence" success message no longer
     join or embed raw internal codes (e.g. "takeoff_items_missing_or_
     empty", "required_filename_timestamp_mismatch_response_timestamp").
     They now show a short human sentence instead. The raw codes are
     unchanged in the saved contract_validation JSON for audit.

2. Generic exception dialogs (module0/app.py, module1/app.py,
   module1/drawing_recognition_viewer.py, module2/app.py,
   module5/app.py, screening/app.py, regional_analysis/module9_ui.py)
   - New core/error_text.py: friendly_exception_text(exc, language).
     ValueError (already hand-written human text by project convention)
     passes through unchanged; any other exception type is wrapped with
     a short generic framing sentence, with the raw type/message kept
     only as a secondary detail line.
   - Applied at every remaining messagebox.showerror(...,str(exc)) /
     str(e) site. A full-tree search after this patch confirms zero
     remaining raw occurrences.

3. English-canonical UI default (core/i18n.py)
   - The I18N class's own defensive default (used only if a caller
     passes no language / an unrecognized code) now comes from
     core/canonical_language.py (CANONICAL_LANGUAGE = "en") instead of a
     separately hard-coded "ja". main.py already passed
     CANONICAL_LANGUAGE explicitly, so this removes a latent, now-closed
     inconsistency rather than changing observed startup behavior.

Verified
- python -m py_compile passes for every .py file in this ZIP.
- lang/ja.json and lang/en.json key parity unchanged (758/758).
- No PATCH_587/PATCH_620 AI-takeoff accept/reject logic changed.

Not changed in this patch
- No quantity, schema, or calculation logic changed anywhere in this ZIP.
