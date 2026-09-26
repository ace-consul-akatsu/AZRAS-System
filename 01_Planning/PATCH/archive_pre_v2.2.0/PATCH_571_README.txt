PATCH 571
- Merge Module 0 City and Address UI into one authoritative City / Location field (project_location).
- New Project JSON stores common.project_location as the authoritative location.
- city/address are compatibility mirrors only; downstream code prefers project_location.
- Approximate Cost request now uses the complete unified location.
- Regional analysis, Google Maps query, location bundle and integrated report prefer the unified field.
- Existing old JSON can still open through legacy city/address fallback, but new formal validation data should be recreated from v1.0.571.
