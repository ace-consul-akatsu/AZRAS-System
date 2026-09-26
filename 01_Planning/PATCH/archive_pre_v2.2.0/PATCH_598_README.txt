AZRAS Planning PATCH 598

RETENTION POLICY — CURRENT STATE ONLY

Keep:
1. Current values explicitly saved in Project JSON by the user/designer.
2. Current imported AI responses, one current snapshot per provider.

Delete:
- Historical human-answer ledgers.
- Old HUMAN_REVIEW source JSON/Excel references.
- Previous human-answer/manual-original values used only as history.
- Other duplicate/superseded human-review history.

Building System change:
- Delete all AI-imported active state belonging to the old building system.
- Delete AI_Evolution/Current working cache.
- Do NOT delete the user's external/source JSON files on disk.
- Keep current user-saved Project JSON values.

Reason:
Old state must not remain available for later code paths to accidentally consult.
The active Project JSON should contain current authority, not hidden historical authority.

Migration:
Older Projects are cleaned automatically when Module 1 is opened and again before save.
