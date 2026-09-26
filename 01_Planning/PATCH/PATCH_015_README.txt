PATCH_015 — services/pdf_drawing_analyzer_v5_2.py + module1/app.py: general
(structure-agnostic) footprint corroboration check, and AI-vs-baseline
geometry cross-check at import time. Follow-up to PATCH_014.

--------------------------------------------------------------------------
① General-purpose repeated-unit-area corroboration (all structure types)
--------------------------------------------------------------------------
Context: after PATCH_014 fixed detect_dimensions()'s width_mm tie-break bug,
the question was raised whether to generalize the existing Steel-only
safety net (_detect_repeated_overall_plan_dimensions(), added in PATCH_85)
to every structure type. Testing that idea directly against
260915_RC_Rahmen_Sample's extracted text first: that function only
considers 5-digit (10000-50000mm) tokens and has no subdivision-exclusion,
so on this PDF it would have picked the same 12900 / 34567(mm) pair as
"overall dimensions" (its 4-digit-only 9500 depth is invisible to it) --
i.e. it would NOT have caught this bug either. Generalizing it as-is would
have been a false sense of safety, so it was not simply extended.

Instead, added _extract_repeated_unit_area_m2(text) + a corroboration step
inside detect_dimensions() itself (so it runs for every structure, not
gated by an if-branch): if the drawing repeats an identical bare area
label (e.g. three "40.85m2" unit labels on a terrace-house plan) 2+ times,
that total (value x count) is compared against the width x depth footprint.
A disagreement beyond +/-15% overrides footprint_m2 with the repeated-label
total (an explicit drawing fact outranks an inferred dimension product,
per AZRAS's own stated evidence-priority order) and invalidates width_m/
depth_m (set to None, added to missing_geometry_fields) rather than
silently leaving stale numbers next to a corrected footprint. Every
correction is recorded in a new dimensions["_conflicts"] list.

Two false starts worth recording so they are not repeated:
- First version's regex required "m2" as one contiguous token. pypdf's
  text extraction on this project's source PDF actually splits the
  superscript across a line break ("40.85m\n2"), so it matched nothing.
  Fixed to `m\s?2`.
- Second version used a floor of 3.0 m2 for candidate values, which
  matched repeated window-opening area labels (e.g. "5.25m2" x3 on the
  elevation sheet) and incorrectly overrode a now-correct 122.55m2
  footprint with 15.75m2. Raised the floor to 15.0 m2 (below any
  plausible building/unit footprint, above typical window/door areas)
  before re-verifying against the real project text.

Verified: reproduces footprint_m2=122.55 on 260915_RC_Rahmen_Sample (no
conflict logged, since PATCH_014's width/depth fix and this check now
agree). Separately verified that if the PATCH_014 width_mm fix were
reverted, this check independently catches and corrects the resulting
445.9143 footprint back to 122.55 -- i.e. this is a real second line of
defense, not a duplicate of PATCH_014.

--------------------------------------------------------------------------
③ AI-self-reported geometry vs. AZRAS baseline cross-check at import time
--------------------------------------------------------------------------
Context: it was proposed to add a dedicated AI call just to sanity-check
drawing scale. On review this would have been redundant: every independent
AI reviewer already computes and returns its own
building_profile.geometry.footprint_m2 as part of the normal takeoff
response schema (confirmed directly in this project's round-1 responses:
Claude returned footprint_m2=445.9143, having trusted AZRAS's baseline;
ChatGPT returned footprint_m2=122.55, having independently re-derived it
from the drawing). AZRAS was already receiving this number from every
reviewer and simply never compared it to its own baseline until the
downstream item quantities disagreed and someone reviewed the recheck
output by hand.

Fix: in _stage_ai_takeoff_payload() (where each AI JSON is imported), each
payload's building_profile.geometry.footprint_m2 is now compared against
the current AZRAS Planning baseline footprint. A disagreement beyond
+/-15% appends a structured entry to a new self.result["ai_geometry_conflicts"]
list (reviewer name, both footprint values, ratio, a Japanese explanation,
requires_confirmation:true) rather than silently proceeding. This is
additive only -- it does not change any existing calculation path, gate
any import, or block a save; it surfaces the disagreement for the same
kind of review the existing "_conflicts" / "warnings" lists already get
elsewhere in this module. No new AI call, no new network/API cost.

Not yet wired into the Module 1 UI (no on-screen indicator reads
ai_geometry_conflicts yet) -- that is a small follow-up (a warning banner
or a Table 1 row, similar to the existing thickness-conflict banner in
detect_insulation()) that was left out of this patch to keep it additive
and low-risk; the data is being captured correctly and is inspectable in
the saved Project JSON today.

--------------------------------------------------------------------------
② Vector-based footprint (NOT attempted in this patch -- flagged honestly)
--------------------------------------------------------------------------
This file already does real vector-geometry reconstruction (via PyMuPDF/
fitz reading actual drawn lines and fills) for RC wall networks, floor
frames, foundations, roof geometry, and stair voids
(extract_generic_rc_wall_plan_takeoff, _rc_floor_frame_vector_takeoff,
_reconstruct_rc_wall_network_from_fill, etc. -- see _generic_vector_axis_lines
for the shared line-extraction primitive). Doing the same for the overall
building footprint (deriving the outer envelope directly from drawn lines
instead of inferring it from repeated dimension text) is a real, durable
improvement and probably the "right" long-term fix -- but it requires
reliably identifying which page is the relevant plan sheet, resolving the
page's drawing scale (pt-per-mm) independent of the text-based method this
patch is meant to stop relying on exclusively, and distinguishing the
building's true outer boundary from dimension lines, hatching, grid axes,
and furniture in the same vector data. That is a properly-scoped follow-up
task in its own right, not something to rush into the same patch as ①/③
without dedicated testing against multiple drawing sets. Recommend treating
it as PATCH_016 once ①/③ have been exercised against a few more real
projects.

--------------------------------------------------------------------------
Verification
--------------------------------------------------------------------------
- All .py files in this package still compile cleanly (py_compile, 0
  errors across the full source tree, including PATCH_014's changes).
- ① verified against the actual extracted text of 260805_RC_Rahmen.pdf,
  both in the already-fixed state (no conflict, footprint=122.55) and
  with PATCH_014's fix hypothetically reverted (conflict correctly fires,
  footprint corrected to 122.55 independently).
- ③ verified by hand against 260915_RC_Rahmen_Sample's actual round-1
  Claude/ChatGPT JSON files: Claude's footprint_m2=445.9143 vs a corrected
  AZRAS baseline of 122.55 now produces a ratio of 3.64, which exceeds the
  +/-15% threshold and would have surfaced this exact conflict at import
  time, before any recheck round was needed.
