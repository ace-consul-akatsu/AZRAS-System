AZRAS Evaluation PATCH 204

Purpose
- Restore the missing lifecycle-scenario screen that precedes lifecycle-cost calculation.

Restored workflow
1. 200-year Environment (Module 4)
2. Repair / Renewal / Demolition Scenario (Module 3)
3. Repair / Renewal / Demolition Cost (Module 7)
4. 200-year Business (Module 6)

Implementation
- Exposes the existing Module3App from the Evaluation launcher.
- Uses the existing renewal_scenario_engine_v9_2.py and existing Module 3 Project JSON save path.
- Does not recreate or change the lifecycle scenario formulas.
- Keeps PATCH 203 Module 7 restoration intact.
