AZRAS Planning PATCH 584

Purpose:
Prevent Meta AI / similar services from stopping at prose because attached TXT instructions are treated as reference data.

Change:
- Added [AIチャット起動文をコピー] / [Copy chat activation prompt].
- Attach the normal drawings + request package + START TXT.
- Then paste the copied activation prompt DIRECTLY into the AI chat message and send it.
- The direct message explicitly requires exactly one AZRAS_AI_TAKEOFF JSON and forbids prose/questions/next-step offers.
- START TXT is retained for audit/history; it is not relied upon as the only execution trigger.

No prior AI or human answer is injected. Independent comparison is preserved.
