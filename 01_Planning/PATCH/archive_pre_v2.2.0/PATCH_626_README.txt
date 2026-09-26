AZRAS Planning PATCH 626

Cause found: reported and diagnosed together with the developer, using the
developer's actual Project JSON as evidence. The "AZRAS ceiling gypsum
board13mm" row (and its two linked substrate rows) showed 30.934 m2 -- far
below a plausible value for a 245 m2 (3-unit, 2-storey) building -- while
sibling rows (loft soffit 21.589, stair soffit 9.346) were correct.

Root cause, confirmed against the actual Project JSON:
- _reconcile_takeoff_with_current_pdf() computes the 1F and 2F ceiling
  components from its own internal "footprint" variable. For this project's
  plan dimensions, that internal footprint resolves to 0 (the function's
  only non-zero footprint-detection path is a hard-coded check for one
  specific 22400x27000mm plan; it does not generally derive footprint from
  arbitrary plan dimensions). This yields 1F ceiling = 0 and 2F ceiling
  (under-roof) = 0 at the time these rows are first written.
- _synchronize_current_analysis_geometry(), which runs AFTER
  _reconcile_takeoff_with_current_pdf() in the same analysis pass, correctly
  resolves footprint_m2 = 122.55 (confirmed in the developer's actual Project
  JSON: width_m=12.9 x depth_m=9.5 = 122.55) from building_scale/
  floor_areas_m2. It updates profile.geometry.footprint_m2, but it does not
  go back and recompute the ceiling rows that were already written with the
  stale footprint=0.
- Net effect: the final saved ceiling total (30.934 m2 = loft 21.589 + stair
  soffit 9.346 only) silently omits both the 1F and 2F flat-ceiling
  components, understating the true quantity by roughly 240 m2 for this
  project.

Behavior
- module1/app.py: new method _repair_stale_ceiling_rows(rows, footprint_m2,
  profile), called from _publish_canonical_geometry_to_project() immediately
  after quantity_takeoff is republished with the final synchronized
  geometry.
  - Locates the ceiling-gypsum-board row and its stair-opening / loft-soffit
    / stair-soffit sibling rows by fuzzy (whitespace/case-insensitive
    substring) item-name matching, so it is resilient to the exact wording
    used by the canonicalization step.
  - Only acts when a positive footprint is now known AND the current
    ceiling total is not already resolved to a plausible value (specifically:
    it is skipped whenever the existing total already exceeds loft+stair
    soffit, i.e. whenever the 1F/2F components already appear to be
    included). A drawing set where the narrow original detection already
    worked is left completely untouched.
  - Recomputes 1F ceiling = footprint - stair floor opening area, 2F ceiling
    = footprint x roof slope factor (read from
    profile.analysis.roof_geometry.slope_factor, falling back to 1.0 only if
    that is unavailable), and the ceiling total = 1F + 2F + loft soffit +
    stair soffit -- the same formula _reconcile_takeoff_with_current_pdf
    itself already uses, just evaluated with the corrected footprint.
  - Cascades the corrected total into the two dependent substrate rows
    ("ceiling substrate applicable area" and "... member length"),
    preserving the existing furring pitch when derivable from the row's own
    prior area/length ratio, defaulting to the existing 303mm provisional
    pitch otherwise.

Verified
- python -m py_compile passes for module1/app.py.
- Standalone logic test using the developer's actual figures (footprint
  122.55, stair opening 5.899256, loft soffit 21.588773, stair soffit
  9.345511, slope factor 1.0012492) recomputes the ceiling total to
  270.288118 m2 (1F 116.650744 + 2F 122.703089 + loft 21.588773 + stair
  9.345511), replacing the stale 30.934284 m2.
- Standalone logic test confirms an already-correctly-resolved ceiling row
  (total already exceeding loft+stair soffit) is left unmodified.

Not changed in this patch
- The underlying footprint-detection gap inside
  _reconcile_takeoff_with_current_pdf() (it only resolves footprint for one
  hard-coded plan-dimension pair) is not fixed at its source in this patch;
  this patch repairs its downstream symptom (stale ceiling rows) once the
  correct footprint becomes available from the separate, more general
  synchronization pass. A deeper fix to make the reconciliation pass itself
  derive footprint generally would be a larger, separate change.
