# -*- coding: utf-8 -*-
"""PATCH_003 self-check (03 Compare).

(1) Legend layout: series legends must be laid out from measured label widths,
    never a fixed pitch, and must not overlap or run off the plot area.
(2) Comparison premises: the revenue basis and the price basis of every loaded
    Project must be carried out of the JSON so a mismatch can be reported.
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

FAIL = []


def check(ok, label, detail=""):
    if ok:
        print(f"  [OK]   {label}")
    else:
        FAIL.append(f"{label} :: {detail}")
        print(f"  [NG]   {label} :: {detail}")


src = (ROOT / "main.py").read_text(encoding="utf-8")

print("PATCH_003 self-check")
print("-- 1. the fixed legend pitch is gone")
check("si*155" not in src, "the hard-coded 155 px legend pitch is removed")
check("_legend_layout" in src and "_measure" in src, "a measured legend layout exists")
check("from tkinter import font as tkfont" in src, "a font metric source is imported")

print("-- 2. the layout never overlaps and never overflows")
body = src[src.index("    LEGEND_FONT="):src.index("    def redraw(self):")]
ns = {}
exec("class L:\n" + body, ns)
L = ns["L"]
# Deterministic metric so the check does not need a display server.
L._measure = lambda self, t: int(sum(11 if ord(c) > 0x2000 else 6 for c in str(t)))
chart = L()

CASES = [
    ["2×6_Sample [2×6]", "AZRAS_Sample [AZRAS Platform]", "RC_Rahmen_Sample [Conventional RC]"],
    ["A", "B"],
    ["とても長い日本語のプロジェクト名称です [在来軸組構法]",
     "もうひとつの長い日本語のプロジェクト名称 [AZRAS Platform]"],
    ["Only one project [Method]"],
    [f"Project {i} [Method {i}]" for i in range(7)],
]
for names in CASES:
    for avail in (1200, 900, 640, 420, 150):
        place, rows, shown = chart._legend_layout(names, avail)
        check(len(place) == len(names) and len(shown) == len(names),
              f"every entry is placed ({len(names)} entries, avail={avail})",
              f"{len(place)}/{len(shown)}")
        spans = {}
        for si in range(len(names)):
            x, r = place[si]
            w = chart.LEGEND_SWATCH_W + chart.LEGEND_TEXT_GAP + chart._measure(shown[si])
            spans.setdefault(r, []).append((x, x + w))
        overlap = None
        overflow = None
        for r, items in spans.items():
            items.sort()
            for a, b in zip(items, items[1:]):
                if a[1] > b[0]:
                    overlap = (r, a, b)
            if items[-1][1] > avail + 0.5:
                overflow = (r, items[-1][1], avail)
        check(overlap is None, f"no overlap (n={len(names)}, avail={avail})", str(overlap))
        check(overflow is None, f"no overflow (n={len(names)}, avail={avail})", str(overflow))
        check(rows == max(r for r in spans) + 1, f"row count matches the placements (avail={avail})",
              f"{rows} vs {max(spans)+1}")

print("-- 3. the reported case specifically")
place, rows, shown = chart._legend_layout(CASES[0], 1000)
a = place[1][0] + chart.LEGEND_SWATCH_W + chart.LEGEND_TEXT_GAP + chart._measure(shown[1])
check(place[2][0] >= a,
      "AZRAS_Sample no longer runs into RC_Rahmen_Sample",
      f"AZRAS ends at {a}, RC starts at {place[2][0]}")
old_a = 78 + 1 * 155 + 20 + 5 + chart._measure(CASES[0][1])
old_b = 78 + 2 * 155
check(old_a > old_b, "the old fixed pitch did overlap, so this is the right defect",
      f"old AZRAS ended at {old_a}, old RC started at {old_b}")

print("-- 4. the legend height is reserved before the axes are drawn")
check(re.search(r"T=T\+max\(0,legend_rows-1\)\*self\.LEGEND_ROW_H", src) is not None,
      "wrapped legend rows push the plot top down")
check(src.index("legend_place,legend_rows,legend_text=self._legend_layout") <
      src.index("self.create_line(L,T,L,h-B)"),
      "the layout is computed before the axis frame is drawn")

print("-- 5. comparison premises are carried out of the JSON")
ext = (ROOT / "comparison" / "extractor.py").read_text(encoding="utf-8")
for key in ("rent_setting_method", "rent_derived_from_cost", "resolved_annual_rent_per_m2",
            "price_basis_token", "location_pricing_mode"):
    check(f"'{key}'" in ext, f"extractor exposes {key}")
check("price_basis_fingerprint" in ext, "the 01 Planning PATCH_040 fingerprint is read when present")
check("location_pricing_mode" in ext and "ai_approximate_cost_session" in ext,
      "a pre-PATCH_040 JSON still resolves a price basis from the pricing mode")

print("-- 6. the premise warning exists and changes no value")
check("比較前提の確認" in src and "'比較前提の確認':'Comparison Premise Check'" in src,
      "the premise dialog is defined and translated")
# PATCH_008: the price-basis grouping moved to comparison/price_basis.py,
# which main.py calls at load time.
_pb = (ROOT / "comparison" / "price_basis.py").read_text(encoding="utf-8")
check("rent_derived_from_cost" in src and "PBASIS.assess(self.projects)" in src and "price_basis_token" in _pb,
      "both premises are checked at load time")
check("値の書き換えや除外は行いません" in src and "No value is rewritten or excluded" in src,
      "the warning states that nothing is rewritten or excluded")

print()
if FAIL:
    print("[NG] PATCH_003 self-check FAILED:")
    for f in FAIL:
        print("   -", f)
    raise SystemExit(1)
print("PATCH_003_LEGEND_LAYOUT_AND_COMPARISON_PREMISE_PASS")
