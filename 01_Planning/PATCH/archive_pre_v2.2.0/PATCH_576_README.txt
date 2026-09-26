PATCH 576

Purpose
- Prevent physical construction scopes from disappearing when both deterministic Module 1 takeoff and AI review fail to produce a row.
- Append mandatory AZRAS scope gaps to Module 1 as unresolved review rows and therefore to the bottom of the Drawing Review Excel.
- Human-confirmed quantities become downstream-eligible for Module 5 pricing; unresolved gaps remain blocked/unpriced.

Mandatory coverage rows
1. Internal RC party-wall concrete
2. Internal 2x6 partition structural framing
3. Ceiling framing / structural substrate material
4. 1F floor substrate / framing material
5. 2F structural floor framing material
6. Roof structural framing material

Rules
- Absence is never converted to zero.
- Rows are only injected for AZRAS construction method.
- Existing semantically equivalent quantity rows suppress duplicates.
- Table 1 human edits set downstream_quantity_eligible=true.
- HUMAN_REVIEW_FINAL supports explicit approve_direct_quantity decisions for these coverage rows.
- Drawing Review Excel filename advances to v1.4.
