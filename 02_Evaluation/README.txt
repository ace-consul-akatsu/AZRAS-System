AZRAS Evaluation Version 2.2.0 (patch number: see "patch" in VERSION.json)

Current product role:
Planning creates and saves the authoritative Project JSON.
Evaluation reads Planning's saved formal results and calculates/saves approved
long-term evaluation results.
Compare reads Evaluation's saved results only.

Current data flow:
01 AZRAS Planning -> 02 AZRAS Evaluation -> 03 AZRAS Compare

Evaluation responsibility boundary:
- Planning owns drawing analysis, AI/human quantity resolution, canonical
  quantity_takeoff, 8760-hour results and construction cost.
- Evaluation must not reconstruct missing quantities from raw AI payloads.
- Evaluation must not apply retired 04 Feasibility adjustment data.
- Retired monolithic Module 8 and future Disaster/Module 9 are not active
  Evaluation dependencies.
- Missing Planning results remain missing and must be corrected in Planning.

Evaluation screens:
- Repair / Renewal / Demolition Scenario
- 200-year Environment
- Repair / Renewal / Demolition Cost
- 200-year Business

All monetary outputs are planning/comparison estimates, not contract prices or
formal quotations.
