PATCH 569 — UTC cross-audit + AI quantity dependency consistency

Base: 1.0.568

Changes:
1. Cross-audited remaining generated timestamps/file stamps and normalized local-time uses to UTC.
2. Filename timestamp format remains YYMMDD_HHMM; seconds are not used.
3. AI approximate-cost request/recheck filenames now use UTC as well.
4. Module/report timestamps explicitly show UTC.
5. Removed legacy JST wording in the old app takeoff contract.
6. Added a mandatory dependency/total consistency gate to the AI takeoff request.
7. RC total must reconcile foundation + exterior RC + internal RC + other applicable RC components.
8. Reinforcement derived by kg/m3 must use the reconciled total RC volume.
9. Delivery method remains PDF/ZIP drawing + REQUEST PACKAGE ZIP + START TXT; Meta may receive extracted package contents.
