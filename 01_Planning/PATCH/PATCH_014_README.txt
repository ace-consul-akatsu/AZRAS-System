PATCH_014 — services/pdf_drawing_analyzer_v5_2.py + module1/app.py: fixed a
~3.64x building-footprint overestimate and a widespread canonicalization
placeholder leak, both found while investigating 260915_RC_Rahmen_Sample.

--------------------------------------------------------------------------
1) detect_dimensions() width_mm selection bug (services/pdf_drawing_analyzer_v5_2.py)
--------------------------------------------------------------------------
Reported: Module 1's own drawing analysis computed footprint_m2=445.9143
(width_m=34.567 x depth_m=12.9) for a drawing whose actual building
envelope, confirmed against the PDF (three repeated "40.85m2" unit labels
plus 12900mm/9500mm dimension lines), is 12.9m x 9.5m = 122.55m2 -- an
overestimate of about 3.64x that propagated into every footprint-dependent
downstream quantity (slab concrete, ceiling/floor areas, etc.) and into
the Building Performance panel's gross floor area.

Root cause: detect_dimensions() scans the extracted PDF text for repeated
4-6 digit numbers and ranks them by (frequency, value) to find the two
building-envelope dimensions, correctly excluding numbers that are clean
subdivisions of a larger repeated number (e.g. a 4300mm grid bay that is
exactly 1/3 of a 12900mm overall width). depth_mm already picked its
candidate correctly with `max(opts, key=lambda v:(freq[v], v))`. width_mm,
however, used a bare `float(max(overall))` -- this ignored the frequency
ranking `overall` had already been sorted by, and instead picked
whichever candidate had the single largest raw numeric value, regardless
of how rarely it occurred.

In this project's source PDF, the extracted text (via pypdf) happened to
contain a "34567" digit string appearing exactly twice -- the minimum
frequency threshold for candidacy, and unrelated to any real building
dimension (most likely stray/incidental text picked up during PDF text
extraction; it does not correspond to anything on the visible drawing).
Because 34567 > 12900 (the real, 9-times-repeated overall width), the old
code selected it as width_mm even though it was the least-supported
candidate in the whole set.

Fix: width_mm now uses the same `max(overall, key=lambda v:(freq[v], v))`
ranking already used for depth_mm, so the most-frequently-repeated
dimension wins, and raw value only breaks ties between equally-frequent
candidates.

Verified against 260915_RC_Rahmen_Sample's drawing text: candidate
frequencies were {12900: 9, 9500: 8, 4300: 8 (subdivision, excluded),
5000: 3, 34567: 2, 11600: 2, 4500: 2}. Before the fix: width_mm=34567.
After the fix: width_mm=12900, depth_mm=9500 -> footprint=122.55m2,
matching the drawing's explicit per-unit area labels (3 x 40.85m2).

--------------------------------------------------------------------------
2) _canonical_hard_english() dictionary-completeness leak (module1/app.py)
--------------------------------------------------------------------------
Reported: several item names and evidence/rationale strings displayed as
the literal fallback text "English canonical migration unresolved for
item/evidence; see source_text_original.item/evidence" instead of a real
English translation, in both the on-screen Module 1 table and in the AI
request/response JSON files, across all 4 independent AI reviewers (since
they all received the same already-broken text in the request package).

Root cause: _canonical_hard_english() runs the japanese source text
through _LEGACY_CANONICAL_EN_REPLACEMENTS (a flat JP->EN phrase-fragment
dictionary, longest-key-first substring replace) and only falls back to
the placeholder marker if Japanese characters remain afterward. This
fallback behavior is intentional (it is relied on elsewhere in this file
as an explicit "needs translation" signal) -- the actual bug is that the
dictionary was missing whole-phrase entries for several item names and
evidence sentences used in this construction-method's drawing set.

Fix: added the missing entries (6 item names, 21 evidence sentences)
found via a full audit of 260915_RC_Rahmen_Sample's project JSON,
following the existing "add a full-phrase entry so it outranks any
shorter fragment matches" pattern already used throughout this dictionary
(e.g. the existing "外壁部の双方に同じ外装下地仕様がPDF明記" entry).

This is a dictionary-completeness fix, not a logic change; the same class
of gap can recur with new construction methods/vocabularies and should be
closed the same way (add the missing phrase, do not touch the fallback
mechanism itself).

--------------------------------------------------------------------------
3) ChatGPT final re-check request template: new mandatory rule 11
--------------------------------------------------------------------------
Reported: when ChatGPT's final re-check correctly detected that an AZRAS
Planning baseline dimension was wrong (see fix #1 above -- this was
observed on 260915_RC_Rahmen_Sample before fix #1 was applied), it had no
rule telling it what to do about the many downstream items that depend on
that baseline, so it returned quantity:null for most of them instead of
recomputing them from the corrected value. This looked like "the AI
stopped filling in unresolved items" when it was actually the recheck
instructions having a gap for this specific situation.

Fix: added rule 11 to the [MANDATORY FINAL RULES] section of the
recheck-request template (the f-string in module1/app.py that builds the
"CHATGPT FINAL RE-CHECK REQUEST" text): when the reviewing AI corrects a
baseline governing value, it must state the corrected value explicitly
(evidence_status:"corrected_baseline") and recompute every downstream
item whose formula is a simple, mechanical function of that value,
reserving quantity:null for items that genuinely cannot be derived even
from the corrected baseline. Template version bumped v1.0 -> v1.1 in the
generated text so future recheck JSON responses are traceable to which
rule set produced them.

--------------------------------------------------------------------------
Verification
--------------------------------------------------------------------------
- All .py files in this package still compile cleanly (py_compile, 0
  errors across the full source tree).
- Fix #1 re-run against the actual extracted PDF text of
  260805_RC_Rahmen.pdf reproduces footprint_m2=122.55 (previously 445.9143).
- Fix #2 dictionary additions verified against the exact Japanese source
  strings recorded in 260915_RC_Rahmen_Sample's source_text_original
  fields; no remaining "canonical migration unresolved" occurrences for
  those six items in a re-run of the canonicalization pass.

Not covered by this patch (flagged for separate follow-up, not silently
guessed at):
- underground_foundations (isolated footing / grade-beam concrete)
  quantity: independent AI candidates disagreed sharply (7.2 / 19.45 /
  31.57 m3) even before the footprint bug is considered. This needs a
  fresh AI re-check against the corrected footprint plus a human check of
  the foundation schedule, not a code fix.
- A separate "storeys: 3" ceiling-gypsum aggregation path exists alongside
  the normal 2-storey path and currently mixes two different candidate
  loft-area values (21.933 vs 24.51 m2). Not touched by this patch.
