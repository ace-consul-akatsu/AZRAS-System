AZRAS Planning PATCH 628

Cause found: reported via screenshot -- "各階床面積" (floor area by storey)
was blank and "延べ床面積" (gross floor area) showed 0.00 m2, even though
footprint_m2 (122.55) and storeys (2) were both already correctly resolved
for the same project.

Root cause: inside _synchronize_current_analysis_geometry(), the canonical
gross_floor_area_m2 was only derived from
final_geom.get("floor_area_m2") / scale.get("gross_floor_area_m2") /
sum(floor_areas_m2). None of those three sources is ever populated for a
building whose plan dimensions do not match the one hard-coded 22400x27000mm
special case elsewhere in the analysis pass (the same class of gap already
found and worked around for the ceiling rows in PATCH_626/627). The existing
"floor_areas_m2 = [gfa/storeys]*storeys" fallback could not help either,
since it only runs once gfa is already positive -- gfa was 0, so the
fallback never triggered, leaving both figures at 0.00 m2 even though the
footprint itself was known.

Behavior
- module1/app.py: gross_floor_area_m2 now has one more fallback candidate --
  footprint_m2 x storeys -- used only when floor_area_m2,
  gross_floor_area_m2, and the floor_areas_m2 sum are all unavailable. Once
  gfa is resolved this way, the existing per-floor fallback
  (floor_areas_m2 = [gfa/storeys]*storeys) fires as before, so
  "各階床面積" now shows one entry per storey.

Verified
- python -m py_compile passes for module1/app.py.
- Using the developer's actual figures (footprint_m2=122.55, storeys=2),
  the new fallback resolves gross_floor_area_m2 to 245.10 m2 and
  floor_areas_m2 to [122.55, 122.55], instead of 0.00 m2 / empty.

Not changed in this patch
- No change to how footprint_m2 itself is resolved (already correct for
  this project, per PATCH_626/627's diagnosis). This only adds a further
  fallback for gross/per-floor area, which previously had no path back to a
  known-good footprint value.
- This is a simplifying assumption (every floor equals the footprint area)
  used only as a last-resort fallback; it does not override an
  independently-resolved, unequal per-floor breakdown when one exists.
