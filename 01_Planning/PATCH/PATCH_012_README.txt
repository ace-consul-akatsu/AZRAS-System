PATCH_012 — module2/app.py: always show 現状仕様 (baseline) as the leftmost bar in the 8760-hour comparison graph

Reported: two bars in the comparison graph happened to show the same
value (0.19) for a metric neither saved scenario had changed, and it was
unclear whether either bar specifically represented the "current/original
design" baseline. They did not -- both bars were "alternative" values from
scenarios that simply hadn't touched that particular part, coincidentally
matching baseline by chance. There was no dedicated baseline bar at all.

Fix: redraw() now always prepends one additional bar, labeled "現状仕様"
(ja) / "Current specification" (en), using the baseline value (column
index 1) from the first saved payload that has the selected metric.
Baseline is the same design across every saved comparison for a given
project, so any one payload's baseline value is representative; it does
not need to be read from every payload. This bar is always first,
followed by the existing per-scenario alternative-value bars in their
existing order.

Verified: with two synthetic payloads (one matching baseline exactly, one
differing), the chart's labels are ['現状仕様', <scenario 1>, <scenario 2>]
and values are [0.19, 0.19, 0.89] -- baseline appears once, first, followed
by both scenarios' own alternative values.

pyflakes: no new issues. All dev_checks/ scripts still pass.

Files changed:
- module2/app.py (show_comparison_graph.redraw only)
