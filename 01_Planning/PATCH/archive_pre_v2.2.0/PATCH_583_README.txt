AZRAS Planning PATCH 583

Purpose
- Complete the in-app human review workflow so normal users do not operate Excel manually.

Changes
1. Compound exterior-wall question is shown as two rows:
   AZR-0001-1 RC exterior wall area
   AZR-0001-2 2x6 exterior wall area
2. Each row can be answered and edited independently; both are required before formal apply.
3. ADD-xxxx items appear immediately in the left table after Save/Update.
4. Selecting an ADD row reloads its category/item/quantity/unit/notes so it can be edited later.
5. Existing formal ADD rows reappear in the same screen and update by ADD identity instead of duplicating.
6. Manual Excel export button was removed from this screen.
7. Formal apply automatically saves a UTC-dated Excel audit workbook in the project AI Takeoff/Human Review folder.
8. Project JSON remains the single current-state data source; Excel is retained only as dated audit history.
