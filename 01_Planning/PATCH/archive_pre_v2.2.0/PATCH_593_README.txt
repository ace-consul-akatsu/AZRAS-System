AZRAS Planning PATCH 593

Problem:
The Drawing Analysis / Quantity Calculation warning could report that one or
more AI responses were already imported even while the visible quantity table
was blank. There was no UI for inspecting the persistent AI-provider store.

Correction:
- Added `収集済みAI回答確認 / View Collected AI`.
- It reads current independent-AI snapshots directly from Project JSON and does
  not require a Module 1 result.
- It shows provider, source JSON, import time, analysis status, item count and
  quantity-answer rows.
- The rebuild warning now states the exact count/provider names and explicitly
  distinguishes AI evidence data from the Module 1 quantity result.

This does not merge independent AI answers into formal quantities. Formal
publication still requires the ChatGPT final re-check / FINAL JSON workflow.
