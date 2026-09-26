AZRAS Planning PATCH 589

AI_Evolution storage correction

Before:
AI_Evolution/
  R1/
  R2/
  R3/
  R4/
  ...

After:
AI_Evolution/
  Current/
    request / manifest / package / START
    Responses/
      CURRENT_chatgpt_AZRAS_AI_ANSWER_OBSERVATION.json
      CURRENT_claude_AZRAS_AI_ANSWER_OBSERVATION.json
      CURRENT_gemini_AZRAS_AI_ANSWER_OBSERVATION.json
      CURRENT_meta_AZRAS_AI_ANSWER_OBSERVATION.json

Rules
- Re-running drawing analysis / generating the current AI request does not create R5, R6, etc.
- Current is replaced.
- Legacy R1/R2/... folders are automatically deleted when the next current package is generated.
- Project JSON retains only current AI_Evolution state.
- Same-provider observations replace the previous current response.
- No old round history is retained by this mechanism.
