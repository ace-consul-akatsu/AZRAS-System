# -*- coding: utf-8 -*-
"""PATCH_050: foundation geometry reaches Module 5 earthwork for every method.

Found on real projects (2x6 and RC Frame) whose Module 5 reported
"foundation_preparation_group: missing_quantity" although the geometry existed:
  RC   - Module 1 publishes the ground-beam length only as
         rc_vector_takeoff.foundation.net_ground_beam_length_m; Module 5 read
         member_geometry.ground_beam_length_m, which nothing writes.
  2x6  - the foundation centerline was "perimeter + party walls x depth" and
         never measured internal strips on the foundation plan; the result also
         used key names Module 5 does not read.

This check fails when:
  1. an RC profile with a resolved vector ground-beam length (and no
     member_geometry length) yields no earthwork, or the source is not recorded;
  2. a 2x6 foundation_geometry in the Module 1 shape (scalar concrete_volume_m3,
     centerline_total_m, footing_base_width_mm ...) yields no earthwork;
  3. the plan-vector detector, run on a synthetic 2-cell strip-foundation plan
     (8.0 x 3.0 m centerlines, stem 180, base 600, heights 300 + 200), does not
     return centerline 25.0 m (perimeter 22.0 + internal 3.0), slab area inside
     the stems 21.545 m2 and the Module 5 contract keys;
  4. Module 1 does not use the stem-inside slab area or leaves the strip-footing
     concrete out of the provisional foundation rebar.

Run: python dev_checks/foundation_earthwork_contract_self_check.py
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from services.construction_cost_engine_v9_4 import _foundation_earthwork_geometry  # noqa: E402

errors: list[str] = []

# 1. RC ground-beam length from the vector foundation takeoff
rc = {"geometry": {"footprint_m2": 122.55}, "construction": {
    "member_geometry": {"source": "pdf_text_explicit_only", "isolated_footing_mm": [1500, 1500, 400],
                        "ground_beam_mm": [350, 500], "isolated_footing_count": 8},
    "rc_vector_takeoff": {"foundation": {"status": "vector_foundation_grid_resolved_requires_confirmation",
                                         "net_ground_beam_length_m": 60.65}}}}
ew = _foundation_earthwork_geometry(rc, "rc_frame")
if not ew:
    errors.append("RC: no earthwork although the vector ground-beam length exists")
else:
    exc = float(ew["quantities"]["excavation_m3"])
    if abs(exc - 56.855) > 0.01:
        errors.append(f"RC: excavation {exc:.3f} != 56.855 (8 footings 19.404 + beams 37.451)")
    if ew.get("drawing_supported", {}).get("ground_beam_length_source") != "rc_vector_takeoff.foundation.net_ground_beam_length_m":
        errors.append("RC: ground-beam length source not recorded")

# 2. 2x6 geometry in the Module 1 row shape
fg = {"status": "resolved_from_current_pdf_geometry", "foundation_type": "strip_foundation_with_slab_on_ground",
      "centerline_total_m": 96.794, "footing_base_width_mm": 600.0, "footing_base_thickness_mm": 200.0,
      "stem_height_mm": 300.0, "concrete_volume_m3": 16.842}
ew2 = _foundation_earthwork_geometry({"geometry": {"footprint_m2": 122.55},
                                      "construction": {"foundation_geometry": fg}}, "wood_frame")
if not ew2:
    errors.append("2x6: no earthwork from a Module 1-shaped foundation_geometry")
elif abs(float(ew2["quantities"]["excavation_m3"]) - 96.794 * 1.2 * 0.65) > 0.01:
    errors.append(f"2x6: excavation {ew2['quantities']['excavation_m3']:.3f} != L x 1.2 x 0.65")

# 3. plan-vector detector on a synthetic drawing
try:
    import fitz  # PyMuPDF
    from services.pdf_drawing_analyzer_v5_2 import detect_2x6_strip_foundation_plan_vector
except Exception as exc:  # noqa: BLE001
    errors.append(f"detector test could not start: {exc!r}")
    fitz = None
if fitz is not None:
    mm = 1.0 / 35.2778          # pt per mm at 1:100 (1 pt = 0.3528 mm paper)
    ox, oy = 200.0, 250.0        # plan origin (pt)
    doc = fitz.open()
    page = doc.new_page(width=842, height=842)
    font = "japan"

    def rect_lines(x0, y0, x1, y1):
        for a, b in (((x0, y0), (x1, y0)), ((x0, y1), (x1, y1)), ((x0, y0), (x0, y1)), ((x1, y0), (x1, y1))):
            page.draw_line(fitz.Point(*a), fitz.Point(*b), width=0.42)

    for i in range(2):                               # two 4.0 x 3.0 m centerline cells
        cx0, cy0 = ox + i * 4000 * mm, oy
        cx1, cy1 = cx0 + 4000 * mm, oy + 3000 * mm
        s, b = 90 * mm, 300 * mm                     # stem face / footing edge offsets
        rect_lines(cx0 + s, cy0 + s, cx1 - s, cy1 - s)
        rect_lines(cx0 + b, cy0 + b, cx1 - b, cy1 - b)
    page.insert_text((600, 420), "布基礎伏せ図", fontname=font, fontsize=9)
    for text, x, y in (("布基礎", 60, 770), ("180", 70, 620), ("600", 70, 745), ("500", 30, 690),
                       ("300", 120, 670), ("200", 120, 710)):
        page.insert_text((x, y), text, fontname=font, fontsize=8)
    page.insert_text((60, 800), "土間厚100+高性能発泡ポリスチレン厚100", fontname=font, fontsize=8)
    with tempfile.TemporaryDirectory() as tmp:
        pdf = Path(tmp) / "strip.pdf"
        doc.save(str(pdf)); doc.close()
        r = detect_2x6_strip_foundation_plan_vector(pdf, {"width_m": 8.0, "depth_m": 3.0})
    if not r or r.get("status") != "resolved_from_current_pdf_geometry":
        errors.append(f"detector did not resolve the synthetic plan: {r and r.get('status')} {r and r.get('reason')}")
    else:
        br = r["centerline_length_breakdown_m"]
        if abs(br["total"] - 25.0) > 0.05 or abs(br["perimeter"] - 22.0) > 0.05 or abs(br["internal"] - 3.0) > 0.05:
            errors.append(f"centerline breakdown wrong: {br}")
        if abs(r["slab_area_inside_stems_m2"] - 21.545) > 0.05:
            errors.append(f"slab area inside stems {r['slab_area_inside_stems_m2']:.3f} != 21.545")
        want = {"footing_base_width_mm": 600.0, "stem_width_mm": 180.0, "stem_height_mm": 300.0,
                "footing_base_thickness_mm": 200.0}
        for k, v in want.items():
            if r.get(k) != v:
                errors.append(f"{k} = {r.get(k)} (expected {v})")
        if r.get("foundation_type") != "strip_foundation_with_slab_on_ground" or not r.get("dimensions_mm"):
            errors.append("detector result lacks the Module 5 contract keys")
        elif not _foundation_earthwork_geometry({"geometry": {"footprint_m2": 24.0},
                                                 "construction": {"foundation_geometry": r}}, "wood_frame"):
            errors.append("detector result is not accepted by Module 5 earthwork")

# 4. Module 1 source contract
src = (ROOT / "module1" / "app.py").read_text(encoding="utf-8")
if '"strip-footing concrete"}' not in src.replace('"strip-footing concrete" }', '"strip-footing concrete"}'):
    errors.append("Module 1 provisional foundation rebar does not include strip-footing concrete")
if "slab_area_inside_stems_m2" not in src:
    errors.append("Module 1 slab concrete does not use the area inside the stems")

if errors:
    for e in errors:
        print("[NG]", e)
    sys.exit(1)
print("[OK] RC ground-beam length reaches Module 5 earthwork (source recorded)")
print("[OK] 2x6 Module 1 foundation geometry reaches Module 5 earthwork")
print("[OK] foundation plan measured incl. internal strips (synthetic plan 22.0 + 3.0 m)")
print("[OK] Module 1 slab uses the stem-inside area; strip concrete included in rebar")
sys.exit(0)
