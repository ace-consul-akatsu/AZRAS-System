AZRAS Planning PATCH 537

1. Module 1 true-north pre-save gate
- When True North Rotation (°) is blank, Module 1 warns immediately and does not save/publish the Module 1 result.
- The warning explains that Module 2 directional 8760 analysis and Module 9 regional Project generation require true north.
- 0° is valid only when the user explicitly enters/confirm it; blank is never converted to 0°.

2. Module 5 dependency scope correction
- Module 5 no longer treats a true-north/orientation-only Module 1 edit as a cost change.
- Module 5 dependency fingerprint ignores north/orientation metadata only.
- Quantity, area, construction detail, and MEP quantity changes still invalidate Module 5 and require recalculation.

Expected workflow after correcting only true north:
Module 1 save -> Module 2 recalculate/save -> Module 9 regional Project generation.
Module 5 does NOT need recalculation unless cost-relevant Module 1 data also changed.

Regression check:
- north-only Module 1 edit: Module 5 cost fingerprint unchanged
- quantity edit: Module 5 cost fingerprint changes
