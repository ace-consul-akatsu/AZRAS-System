AZRAS Compare PATCH 17 / v1.1.17

Purpose:
Complete the Japanese/English presentation-language separation identified by the language/canonical-purity re-audit.

Changes:
- expanded English UI translation coverage
- translated dynamic chart titles, warnings, status text, table headings, and save notifications
- English month labels when English UI is selected
- localized presentation headers in exported comparison CSV
- ASCII default CSV filename
- preserved Project names/locations/source data without forced translation
- no calculation or responsibility-boundary change

Regression scope:
PATCH 17 plus previous five Compare corrections / current responsibility boundary:
- read-only Project JSON consumer
- no lifecycle CO2 recalculation
- no discounted CF recalculation
- no missing-value zero fill
- no retired Feasibility logic
- saved Module 4/Module 6 series only
