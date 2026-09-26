PATCH 568 — AI takeoff delivery/validation hardening + UTC naming

Base: 01_AZRAS_Planning_Basic_v1.0.567_corrected

Changes
1. AI takeoff send set is standardized as three attachment groups:
   - drawing PDF/ZIP files
   - AZRAS_AI_REQUEST_PACKAGE_Rx.zip
   - AZRAS_AI_START_Rx.txt
   If an AI service cannot read ZIP directly (observed with Meta AI), extract only the request ZIP and attach its files individually; keep the same drawings and START TXT.
2. A short external START TXT is generated automatically for every AI observation round.
3. Returned AI JSON filename time basis is UTC, format YYMMDD_HHMM. Seconds are not used.
4. response_timestamp must be UTC ISO8601 and its UTC minute must match the filename prefix.
5. AI request now requires exact root schema AZRAS_AI_TAKEOFF and forbids vendor-specific schemas/ITEM-001 identifiers.
6. Every PRE_TAKEOFF estimated/unresolved/first-round-independent local_id is a mandatory returned worklist item, exactly once.
7. Added import-side contract validation. Schema-compatible but incomplete responses are preserved as evidence and marked noncompliant_evidence_only; formal values are not changed during collection. Schema-incompatible JSON remains rejected.
8. Added explicit ambiguity guard for visually similar drawing values (e.g. 2.55 vs 2.59): cross-check before adopting; otherwise unresolved/conflicting.
9. AI workflow timestamps in Module 1 use UTC.
10. Response template canonical schema updated to 2.6 with completion_gate fields.

No change to deterministic quantity formulas or formal ChatGPT FINAL adoption authority.
