AZRAS Planning PATCH 591

AI_Evolution regression stabilization

Correct current structure:
AI_Evolution/
  Current/
    <request files>
    <manifest>
    <request package ZIP>
    <START TXT>
    CURRENT_chatgpt_AZRAS_AI_ANSWER_OBSERVATION.json
    CURRENT_claude_AZRAS_AI_ANSWER_OBSERVATION.json
    CURRENT_gemini_AZRAS_AI_ANSWER_OBSERVATION.json
    CURRENT_meta_AZRAS_AI_ANSWER_OBSERVATION.json

The following structures are forbidden and automatically removed:
  AI_Evolution/R1
  AI_Evolution/R2
  AI_Evolution/R3
  ...
  AI_Evolution/Current/Responses

Root cause of the recurrence:
PATCH 589 corrected the request-package path to Current, but the separate
AI-observation writer still contained the older `.../<round>/Responses` path.
Therefore importing AI responses recreated Responses even though request
generation no longer created R1/R2/R3.

PATCH 591 removes that split implementation. Both request generation and
response observation storage now use one centralized workspace normalizer.

Regression matrix also verifies:
- PATCH 588: AI provider aliases remain canonicalized.
- PATCH 589: R1/R2/R3 history remains disabled.
- PATCH 590: AZR-0001 remains a mandatory two-answer review item.
- PATCH 591: Responses is not created; observations are directly under Current.
