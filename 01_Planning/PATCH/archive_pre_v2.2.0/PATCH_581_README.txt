AZRAS Planning PATCH 581

Purpose:
Complete the in-app human-review flow through deterministic rebuild and Module 5 cost linkage.

Implemented:
- Persist human-confirmed direct quantities before Project JSON save and before a full drawing rebuild.
- Recreate user/designer-added ADD scopes after the deterministic PDF takeoff rebuild.
- Preserve ADD identity, quantity, unit, decision maker/date, notes, Cost Key and pricing status.
- Recognize an explicit human-approved user-added Cost Key as the Module 1 -> Module 5 bridge.
- Add a safe exact mapping for クロス張り -> interior_finish.
- Leave user-added scopes without a defensible Cost Key as explicit unpriced/unmapped monetary gaps; never substitute zero.
- Mark Module 5 as requiring recalculation after HUMAN_REVIEW_FINAL changes Module 1 quantity authority.

Regression:
- Multi-answer exterior-wall decision: RC 113.16 m2 + 2x6 114.48 m2 remains two independent structured values.
- User-added クロス張り 213.204 m2 survives save/rebuild persistence and maps to interior_finish.
- An unmapped user-added physical quantity is not priced and is reported as one monetary gap.
