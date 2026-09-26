# AZRAS AI Longitudinal Observation Protocol v1.1

This companion protocol allows the same AZRAS drawing set and the exact same request to be
resent to multiple AI systems and at later dates, so changes in drawing-reading and quantity
takeoff capability can be observed longitudinally.

## Mandatory conditions for the AI
- Answer independently using only the drawings and request contained in this package.
- Do not infer or use previous-round answers, other AI answers, or AZRAS longitudinal comparisons.
- Evidence priority: explicit drawing facts > cross-drawing reconciliation > drawing-based calculation > estimate.
- If the drawings do not support a defensible value, return null / unresolved rather than inventing a number.
- analysis.ai_reviewer must identify the AI that actually performed the review.
- When known, set analysis.evolution_observation.ai_model_version to the exact model/version; otherwise null.
- When known, set analysis.evolution_observation.response_timestamp to an ISO8601 timestamp; otherwise null.
- Return exactly one normal AZRAS_AI_TAKEOFF JSON file. Do not create a separate comparison JSON.

## AZRAS-side only
previous_record_id, changed_from_previous, change_summary, cross_ai_variance_note,
human_review, and final_adopted_value are computed/stored by AZRAS after collection and must
not be self-assessed by the responding AI.

## Reproducibility
For a later observation under identical conditions, resend this request ZIP unchanged and attach the drawing PDFs/ZIPs separately.
The Manifest stores SHA-256 hashes of the request and every drawing file so the identical drawing set can be verified.

## R1 folder rules
AZRAS's only active storage area is `R1` directly under the Project.
The first send-out to each AI is collected in `R1/01_Request for Estimate`.
Each AI's independent answer JSON is saved in `R1/02_AI response`.
Recheck requests go in `R1/03_Request for Recheck`; the final JSON formally adopted goes in `R1/04_Final determination`.
Do not send other AIs' answers with the first independent request; that breaks the independent-comparison condition.
R2 is reserved for future use and is not created at this stage.

## Response-format hard gate
The AI must not return a drawing summary, explanatory prose, clarifying questions, or proposals for next steps.
The answer is exactly one `AZRAS_AI_TAKEOFF` JSON file.
If open points remain, do not stop to ask; record `quantity:null`, `evidence_status:"unresolved"`, `missing_inputs`, and `checked_sources` inside the JSON and return it.
Use `AZRAS_AI_TAKEOFF_RESPONSE_TEMPLATE_v1.0.json` in the request ZIP as the answer skeleton.


## PATCH 573 identity / filename rule
- `analysis.ai_reviewer` must identify the actual responding AI, determined from its own service/runtime identity.
- Root `required_filename` is mandatory and must use the same actual AI token and UTC completion minute.
- Canonical Meta AI token is `meta`; do not copy `chatgpt`, `claude`, or another provider token from examples.
- If the service/browser cannot control the downloaded filename, the generic transport filename is allowed only when `required_filename` is valid and internally consistent.
