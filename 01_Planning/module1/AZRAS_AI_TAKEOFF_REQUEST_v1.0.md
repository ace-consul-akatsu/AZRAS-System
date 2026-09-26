# AZRAS AI TAKEOFF REQUEST v1.0 — English Canonical

This file is the common instruction reference for requesting drawing quantity takeoff from an AI in AZRAS Planning Module 1.

## Authoritative workflow
Project JSON → Module 1 → load PDF/ZIP and drawings → Drawing Analysis / Quantity Calculation → establish confirmed / estimated / unresolved rows → Start AI Takeoff → send the generated English-canonical request plus PDF/ZIP → receive AZRAS_AI_TAKEOFF JSON → import by `local_id` → review → final import.

The current Planning quantity table is authoritative. AI output is an evidence/completion layer. It must not overwrite confirmed rows, duplicate confirmed quantities, or silently interpret an absent scope as zero.

## Language contract
- Generated request instructions and canonical fields MUST be English.
- Japanese or other source-language drawing text MAY be preserved only as source evidence, e.g. `source_text_original`.
- Do not copy source-language drawing text into `canonical_item`, `canonical_category`, `canonical_specification`, or `canonical_calculation_basis`.
- If a canonical English translation cannot be determined safely, keep the source text in the source-evidence field and mark the canonical field unresolved in English.

## Quantity contract
- Preserve every required `local_id`.
- Do not return confirmed items as new `takeoff_items`.
- Do not infer zero from omission.
- Use `null` when a required fact cannot be verified.
- Keep units dimensionally consistent.
- State evidence and calculation basis for each proposed quantity.

## Multi-AI workflow
1. Generate the first-round AI takeoff request from AZRAS Planning.
2. Collect independent AI responses.
3. Import each response under its canonical provider identity.
4. Generate the ChatGPT re-check request containing the current Planning baseline and current AI responses.
5. Resolve remaining conflicts by current evidence and, when required, human review.
6. Import only the FINAL JSON as the formal AI completion result.

The runtime-generated request displayed by AZRAS Planning is the authoritative request for the current Project. This reference file does not replace the generated Project-specific request.
