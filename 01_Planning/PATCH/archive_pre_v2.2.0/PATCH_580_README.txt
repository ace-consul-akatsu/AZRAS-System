AZRAS Planning PATCH 580

Purpose:
Correct the human-review UI model from one issue = one quantity to one issue = N required answer fields.

Implemented:
- Exterior wall allocation asks separately for RC exterior wall area and 2x6 exterior wall area.
- Both values are mandatory and stored as structured HUMAN_REVIEW_FINAL fields.
- Generic row-level human_review_fields metadata can define future multi-answer questions.
- Existing free-text two-value parser remains only for backward compatibility.
- Unanswered fields are not converted to zero.
