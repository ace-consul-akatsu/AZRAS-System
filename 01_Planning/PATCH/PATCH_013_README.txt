PATCH_013 — module2/app.py: deduplicate identical saved comparisons in the 8760-hour comparison graph

Reported: the graph showed 4 bars (baseline + 3), but two of them
("屋根:Phenolic foam50mm / 外壁（軽量壁）:Phenolic foam50mm / 床・土間:XPS0mm",
5241.28) had the exact same label AND the exact same value -- a genuine
duplicate, not two different scenarios. This came from two saved
comparison files (260916_0214 and 260916_0332) that recorded the identical
scenario and identical results.

Fix: after gathering all saved comparison payloads (and before adding the
live/unsaved one), payloads are now deduplicated by a key combining the
scenario label (_scenario_label) and every metric's alternative value
across the whole display_rows table. If two saved files produce the same
key, only the first (chronologically earliest, since files are read in
sorted/timestamp order) is kept; later exact duplicates are dropped
before the chart is drawn. The live/unsaved snapshot is also checked
against this same dedup key so it does not add a redundant bar either.

Verified: with two duplicate payloads (identical scenario label 190mm
Phenolic foam roof at values 2515.492/5241.285) and one genuinely
different payload (100mm Phenolic foam, 4080.97), the dedup logic keeps
the first duplicate and drops the second, leaving 2 final payloads.

pyflakes: no new issues. All dev_checks/ scripts still pass.

Files changed:
- module2/app.py (show_comparison_graph: payload gathering now deduplicates)
