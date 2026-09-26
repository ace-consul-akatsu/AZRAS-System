AZRAS Planning PATCH 595

Observed symptom
The Human Review screen previously showed many unresolved questions, but after
a later ChatGPT FINAL JSON import only three structural rows remained.

Root cause
Two different things happened:
1. Some previous questions legitimately left the Unknown/Conflict list because
   the current drawing/FINAL review produced numeric estimated or confirmed rows.
2. More seriously, genuinely omitted physical scopes discovered by first-round
   AI responses (electrical/mechanical/plumbing/fire etc.) could disappear if
   the FINAL JSON simply forgot to return them. The importer treated absence as
   silence and therefore no review row survived.

PATCH 595 rule
Absence never means resolved.

If first-round evidence contains `local_id:null` + `resolution_action:add_new`
for a recognized physical scope and the ChatGPT FINAL JSON does not address that
scope at all, AZRAS preserves one unresolved audit row for it. The first-round
AI value is NOT formally adopted; the row is retained only as an unresolved
scope requiring final/human resolution.

This protects audit completeness while preserving the rule that independent AI
answers are evidence only.
