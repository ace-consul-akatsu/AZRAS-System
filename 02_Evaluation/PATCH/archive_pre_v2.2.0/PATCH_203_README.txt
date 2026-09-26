AZRAS Evaluation PATCH 203

Purpose
- Restore the independent Repair / Renewal / Demolition Cost screen that had been hidden from the Evaluation top screen.

Changes
- main.py: add third top-screen button and import Module7App.
- module7/app.py: correct window module number to 7.
- lang/ja.json, lang/en.json: restore user-facing Module 7 title.
- No repair/renewal calculation formulas were recreated; the existing Module 7 engine and Project JSON connection are reused.
- 200-year Environment and 200-year Business remain unchanged.
