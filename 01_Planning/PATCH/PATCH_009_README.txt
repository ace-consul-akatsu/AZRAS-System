PATCH_009 — module2/app.py: hide non-comparative metrics from the 8760-hour comparison graph

Reported: the graph's metric dropdown (added in PATCH_003) listed items
like "Module 1 version", "上流構造数量状態", "AI積算元" (a filename), and
"8760使用 軽量外壁面積 m2" (light-weight wall area) that showed 0.00 for
every single saved scenario in this RC-only project (no light wall exists
at all, so this area never changes regardless of which insulation
material/thickness is compared).

Root cause: display_rows mixes three kinds of entries in the underlying
8760-comparison result table: genuine numeric energy/performance metrics,
pure text/audit fields (version strings, filenames, match/changed flags),
and physical-quantity "根拠" (basis) numbers that are frequently identical
across every scenario for a given project (only the insulation spec
changes between saved comparisons, not the building geometry). The graph
dropdown was populated from every display_rows label with no filtering at
all, so selecting a text field produced an empty chart, and selecting an
always-0/always-the-same quantity produced a flat, comparison-free chart.

Fix: metrics are now built by checking every candidate label across all
loaded payloads: a label is kept only if (a) its value parses as a number
in every payload that has it (any non-numeric occurrence excludes it
entirely), and (b) it actually varies across the saved scenarios (or only
one scenario is loaded so far, in which case variance cannot yet be
judged and it is kept). If no metric passes this filter, a warning is
shown instead of opening an empty graph.

Verified: with synthetic display_rows mixing text fields ("Module 1
version", "AI積算元"), a constant-zero area ("8760使用 軽量外壁面積 m2"),
and a genuinely varying metric ("年間暖房負荷 kWh"), only the varying
numeric metric remains in the final dropdown list.

pyflakes: no new issues. All dev_checks/ scripts still pass.

Files changed:
- module2/app.py (show_comparison_graph: metric list now filtered)
