AZRAS Planning PATCH 577

- Review Excel: separate 30-row ADD-xxxx user/designer additional-item section.
- Editable input columns: C category, D item, Q instruction, S approved value, T unit, U decision maker, V date, Y notes/traceability.
- Column Y is explicitly free-entry.
- HUMAN_REVIEW_FINAL direct approved ADD-xxxx decisions create formal Module 1 quantity rows.
- Added rows are downstream quantity eligible. Cost Key mapped rows flow to construction cost; unmapped rows remain unit-cost-not-acquired (never silently zero-priced).
- Existing mandatory-scope audit remains active and separate.
