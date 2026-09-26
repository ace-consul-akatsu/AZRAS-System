AZRAS Planning PATCH 573

1. Meta AI identity protection
   - Removed provider-specific completed filename examples from the generated request.
   - Added actual-responder identity hard gate.
   - Canonical Meta AI filename token is now `meta` (legacy `metaai` is recognized but noncompliant for new output).

2. Gemini/browser filename fallback
   - Every response must include root `required_filename`.
   - Generic browser filenames are accepted as transport names only when required_filename, ai_reviewer and UTC timestamp are internally consistent.

3. Import-side identity enforcement
   - If an attachment filename claims an AZRAS AI suffix that disagrees with analysis.ai_reviewer/required_filename, collection is rejected.

4. Claude finding incorporated
   - Opening request rules now require spatial association of opening type labels and area rows, not PDF text order.
   - Local PDF opening extractor is upgraded separately in this patch to use spatial door-label association before text-order fallback.

5. False-100% completeness prevention
   - Request requires omitted physical scopes to be represented as unresolved rows when quantity-defining drawings are absent.
   - Import validation flags electrical pages with no electrical rows, RC scope with no reinforcement row, complete disciplines with unresolved scopes, and 100% reports that coexist with unresolved scopes.

Base: 1.0.572
Target: 1.0.573
