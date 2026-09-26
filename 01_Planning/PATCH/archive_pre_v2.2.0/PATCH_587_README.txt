AZRAS Planning PATCH 587

Purpose
- Handle AI services that return an otherwise valid AZRAS takeoff JSON but omit root schema.

Behavior
1. schema == AZRAS_AI_TAKEOFF
   -> normal existing collection flow.
2. schema missing
   -> AZRAS performs a narrow structural recognition check:
      - non-empty takeoff_items
      - analysis object
      - project
      - AZRAS-specific item-field shape
      - overlap with active PRE_TAKEOFF local_ids
   -> when recognized, collect as evidence only.
   -> contract status: noncompliant_evidence_only
   -> issue: missing_root_schema_inferred_for_evidence_only
   -> formal_eligibility: false
3. conflicting/non-empty unsupported schema
   -> reject as before.
4. arbitrary JSON with missing schema
   -> reject.

Important
- The original AI claim is not silently converted into a compliant response.
- Formal quantities are not changed at independent-AI collection stage.
