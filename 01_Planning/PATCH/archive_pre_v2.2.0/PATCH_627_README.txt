AZRAS Planning PATCH 627

Cause found: reported by the developer using an actual re-run
(260914_AZRAS_002.json) after applying PATCH_626 -- the ceiling row was
still 30.934284 m2, unchanged.

Root cause: PATCH_626 attached the ceiling repair call inside
_publish_canonical_geometry_to_project(), which is only reached from
save_output() (the "Project JSONを更新保存" button). The "図面解析・数量計算"
(Drawing Analysis / Quantity Calculation) button -- the path the developer
actually used, and the path that runs _reconcile_takeoff_with_current_pdf()
followed by _synchronize_current_analysis_geometry() in the same pass --
never calls _publish_canonical_geometry_to_project() at all. The repair
code was correct but was placed on a call path the reported scenario never
takes.

Behavior
- module1/app.py: the call to _repair_stale_ceiling_rows(...) now happens
  at the end of _synchronize_current_analysis_geometry() itself, using that
  function's own already-resolved canonical["footprint_m2"] and
  final_profile. Since _synchronize_current_analysis_geometry() is the
  single function called from all three places that need it (Drawing
  Analysis / Quantity Calculation, an AI-supplement rebuild, and Project
  JSON save), the repair now runs on every one of them.
- The now-redundant repair call inside _publish_canonical_geometry_to_project
  (which calls _synchronize_current_analysis_geometry() first) was removed
  to avoid dead duplicate logic.

Verified
- python -m py_compile passes for module1/app.py.
- Confirmed against the developer's actual 260914_AZRAS_002.json that
  profile.analysis.roof_geometry.slope_factor (1.0012492197250393) and
  profile.geometry.footprint_m2 (122.55) are both present and correctly
  resolved at the point _synchronize_current_analysis_geometry() runs, so
  the repair now has everything it needs at the call site that actually
  executes during Drawing Analysis / Quantity Calculation.

Not changed in this patch
- The repair formula/logic itself (_repair_stale_ceiling_rows) is unchanged
  from PATCH_626 -- only where it is called from.
