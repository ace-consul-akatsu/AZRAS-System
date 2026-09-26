AZRAS Planning PATCH 574

1. AI response filename auto-normalization
   - On independent AI JSON collection, AZRAS reads root required_filename.
   - It cross-checks the required filename minute against analysis.evolution_observation.response_timestamp.
   - It derives the canonical AI token from analysis.ai_reviewer.
   - It creates/uses the formal canonical filename:
     YYMMDD_HHMM_AZRAS_AI_Takeoff_<project>_<token>.json

2. Provider/browser differences absorbed by AZRAS
   - Gemini-style generic browser filenames are normalized automatically.
   - Meta-style hyphenated transport filenames are normalized automatically.
   - Known provider aliases are canonicalized (MetaAI -> meta).
   - Claude/ChatGPT files already using the canonical name pass through unchanged.

3. Evidence preservation
   - AZRAS does not overwrite the original provider/browser download when a new canonical copy is needed.
   - The canonical copy contains the normalized root required_filename.
   - Filename normalization metadata is stored with the import contract validation.

4. Safety gates
   - Unsafe path-like required_filename/project values are rejected.
   - A canonical-name collision with different content is rejected rather than overwritten.
   - UTC timestamp mismatch is rejected before normalization.

Base: 1.0.573
Target: 1.0.574
