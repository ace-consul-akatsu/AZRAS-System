AZRAS Compare Version 2.2.0 (patch number: see "patch" in VERSION.json)

Official product slot: 03_AZRAS_Compare

Current responsibility boundary:
01 AZRAS Planning -> 02 AZRAS Evaluation -> 03 AZRAS Compare

Compare is a read-only consumer of saved Project JSON results.
It does not:
- replace missing Evaluation results with zero,
- estimate missing Evaluation results,
- reconstruct missing quantities from AI evidence,
- recalculate 200-year environmental results,
- recalculate 200-year business/present-value results,
- apply retired 04 Feasibility adjustments.

Evaluation completion:
- 200-year environment + 200-year business saved: Complete
- one saved: Partial
- neither saved: Not calculated

Current AZRAS v2.2.0 products:
00 Installer / 01 Planning / 02 Evaluation / 03 Compare

Present-value recovery graph requires the saved Evaluation v2.2.0 (field present since former Evaluation 1.0.209) cumulative discounted holding-period CF. Older Project JSONs without that saved field remain Not calculated; Compare does not reconstruct it.

Language presentation update (former Compare 1.1.17, carried into v2.2.0):
- Japanese and English UI presentation paths are explicitly separated.
- Dynamic chart titles, warnings, status labels, table headings, and CSV presentation headers follow the selected UI language.
- Project names, locations, currencies, units, and saved Project JSON data remain source values and are not rewritten.
- No Evaluation-owned calculation logic was added to Compare.
