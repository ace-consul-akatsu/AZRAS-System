# -*- coding: utf-8 -*-
"""PATCH_051: a per-unit or finish-area note is never the building's floor area.

Real case (AZRAS terrace house, 3 dwellings, 2 storeys, 12.9 x 9.5 m): the note
「天井と床面積：37.60m2/戸 3戸：112.8㎡」 was read as the gross floor area, so
the Project carried 37.6 m2 (18.8 per floor) instead of 245.1 m2 and every
per-m2 result downstream (rent, heating/cooling, CO2) used a sixth of the building.

This check fails when:
  1. a per-dwelling / per-room value (m2/戸, m2/室, m2 x n戸) or a finish-area
     note (天井と床面積, 床仕上面積, 壁・天井面積) is returned as a whole-building area;
  2. a plain 延床面積 / 延べ床面積 / 床面積 / 建築面積 note is no longer returned;
  3. detect_dimensions() on text with only such notes does not give
     footprint x storeys (245.1 m2) but one of the small notes;
  4. an explicit whole-building 延床面積 note stops being used.

Run: python dev_checks/per_unit_finish_area_not_gross_floor_area_self_check.py
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from services.pdf_drawing_analyzer_v5_2 import _extract_area_values, detect_dimensions  # noqa: E402

errors = []
for text in ("天井と床面積：37.60m2/戸", "LDK：24.36m2/戸", "BR1：14.52m2/戸", "床面積：40.85m2×3戸",
             "床面積：20.0m2/室", "床仕上面積：80m2", "壁・天井面積：50m2", "天井と床面積 37.6㎡"):
    got = _extract_area_values(text)
    if got:
        errors.append(f"not a building area but returned: {text!r} -> {got}")
for text, want in (("延床面積：245.10m2", 245.1), ("延べ床面積 245.1㎡", 245.1),
                   ("床面積：120.5m2", 120.5), ("建築面積：122.55m2", 122.55)):
    if _extract_area_values(text) != [want]:
        errors.append(f"building area lost: {text!r} -> {_extract_area_values(text)}")

base = ("配置図兼1階平面図 2階平面図 12900 12900 12900 9500 9500 9500 "
        "LDK：24.36m2/戸 BR2：14.85m2/戸 BR1：14.52m2/戸 天井と床面積：37.60m2/戸 3戸：112.8㎡ loft：8.17m2/戸")
d = detect_dimensions(base)
if not (d.get("floor_area_m2") and abs(d["floor_area_m2"] - 245.1) < 0.01):
    errors.append(f"per-unit notes only: floor area {d.get('floor_area_m2')} (expected 245.1 = 12.9 x 9.5 x 2)")
if d.get("floor_areas_m2") and any(abs(v - 122.55) > 0.01 for v in d["floor_areas_m2"]):
    errors.append(f"per-floor areas {d['floor_areas_m2']} (expected 122.55 each)")
d2 = detect_dimensions(base + " 延床面積：245.10m2")
if not (d2.get("floor_area_m2") and abs(d2["floor_area_m2"] - 245.1) < 0.01 and "gross_floor_area" not in d2.get("missing_geometry_fields", [])):
    errors.append(f"explicit 延床面積 not used: {d2.get('floor_area_m2')} {d2.get('missing_geometry_fields')}")

if errors:
    for e in errors:
        print("[NG]", e)
    sys.exit(1)
print("[OK] per-unit / finish-area notes are not taken as the building floor area")
print("[OK] footprint x storeys used when no whole-building note exists; explicit 延床面積 still used")
sys.exit(0)
