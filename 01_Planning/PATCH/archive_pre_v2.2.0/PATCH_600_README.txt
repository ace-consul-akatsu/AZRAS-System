AZRAS Planning v1.0.600

600-MILESTONE COMPREHENSIVE REGRESSION AUDIT

Purpose
This is not merely a sequential PATCH. It is a milestone audit intended to
verify that recent fixes have not silently restored older behavior.

Audit coverage
- All Python source files compile.
- Module 1 import succeeds.
- Module 5 import succeeds.
- Review workbook helper imports.
- Construction-cost engine imports.
- AI provider aliases collapse to one current provider identity.
- AI_Evolution remains Current-only; old R* and Responses structures do not return.
- Exterior-wall Human Review still requires two independent answers.
- FINAL omitted-scope continuity remains active.
- carried_gap_keys is defined only in the proper FINAL-review path.
- Module 1 rebuild remains transactional.
- Collected-AI and Saved-M1 viewers remain available.
- Building-system changes purge old-system AI state.
- User-selected Building System / Structure / Method remains locked across PDF analysis.

Additional defects found by the audit
1. Human Review still contained a reader for the old decision_ledger even though
   PATCH 598 had changed the project to current-state-only retention.
2. Human Review formal apply still auto-generated dated Human Review JSON and
   Excel audit files, contradicting the new no-history policy.

Corrections
- Removed historical decision-ledger lookup from active Human Review logic.
- Stopped automatic Human Review JSON/Excel history generation.
- Current approved values are stored in Project JSON only.
- Review Excel remains available only when the user explicitly exports it.
- Updated UI/success messages to reflect the actual retention policy.

Retention authority after v1.0.600
KEEP:
1. Current values explicitly saved in the Project JSON by the user/designer.
2. Current imported AI responses, one current snapshot per AI provider.

DELETE / DO NOT ACCUMULATE:
- Historical human answer ledgers.
- Old HUMAN_REVIEW source references.
- Automatically generated dated Human Review history files.
- Superseded same-provider AI responses.
- Old AI state after Building System changes.

External/source files explicitly saved by the user are never deleted by this policy.
