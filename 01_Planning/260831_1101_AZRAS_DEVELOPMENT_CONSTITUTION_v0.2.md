# AZRAS DEVELOPMENT CONSTITUTION
Version: 0.2
Status: Governing Development Specification

## 1. Purpose
This file records the highest-level development rules and current architecture of AZRAS.
All AZRAS development, audits, patches, refactoring, and specification changes must be checked against this file before implementation.
This is not a PATCH changelog. Routine fixes and temporary implementation details must not be added here.

## 2. Authority and Change Control
- The developer/user makes final decisions on AZRAS architecture, development methods, product boundaries, and major implementation choices.
- Before any time-consuming task, large data build, mass item-by-item processing, or major restructuring, consult the developer/user first.
- Present alternatives, expected workload, advantages/disadvantages, and effects on existing code/data so the developer/user can choose the method.
- Do not change an established calculation method, data structure, ownership rule, pricing method, or product architecture during implementation without prior consultation.
- If a change becomes necessary, stop before implementation and identify the reason, affected modules/data, obsolete code/data that may remain, migration/deletion requirements, and regression-audit scope.
- If repeated PATCHes, regressions, side effects, or architectural inconsistency appear, report the problem early rather than continuing a PATCH chain.

## 3. Current Product Architecture

### 3.1 01_AZRAS_Planning
The current `01_AZRAS_Planning_Basic` is planned to become `01_AZRAS_Planning`.

`01_AZRAS_Planning` contains BOTH Cost Provider paths below. They are not separate Planning and Professional products.

#### A. Paid Cost Provider
- Apply country/region-specific unit prices obtained from paid commercial cost-data providers to quantities calculated by Module 1.
- With a sufficiently complete design-document set, including architectural, structural and MEP drawings, support preparation of detailed construction-cost estimates.
- The output assists preparation/checking of detailed estimates usable toward construction contracting and remains subject to professional verification.

#### B. AZRAS Approximate Cost Provider
- Calculate approximate construction cost without requiring a paid cost-data-provider contract.
- Use for early planning and feasibility based on a limited drawing set such as plans, elevations, sections, finish schedules and door/window schedules.
- Support country/region, construction-method and climate differences.
- Supply approximate construction-cost inputs to project/business planning and long-term/200-year analysis.

### 3.2 AZRAS Professional
AZRAS Professional is NOT the paid Cost Provider.

Its intended direction is to use AZRAS project/calculation data to assist with country-specific environmental assessment, review, certification and application documentation, including populating application-form fields where AZRAS already has defensible corresponding data.

Detailed scope must be agreed before implementation.

## 4. Quantity and Cost Separation
- Module 1 is fundamentally the quantity/evidence layer.
- Preserve defensible physical quantities extracted or calculated from drawings, including detailed quantities that may later be useful.
- Do not delete a useful physical quantity merely because the approximate cost method does not price it separately.
- Pricing responsibility belongs to the Cost Provider layer.
- The same underlying quantity information should be reusable by both Paid and Approximate Cost Providers wherever technically appropriate.
- Avoid duplicate cost counting.
- Do not invent unit prices.
- Before introducing a large new unit-price taxonomy or individually pricing a large number of materials, consult the developer/user.

## 5. Quantity Certainty
- Drawing-confirmed quantities: normal/confirmed status.
- Rationally estimated quantities: retain a numeric quantity and mark provisional/estimated (yellow under the agreed UI convention).
- Only quantities for which even a rational estimate cannot be established should be unresolved/requiring human confirmation (red under the agreed UI convention).
- Physical quantities must not be replaced by text-occurrence counts.

## 6. Multi-AI Quantity Reconciliation
- For 2 AI quantity results, use the larger quantity.
- For 3 or more AI results, when an identical quantity has a strict majority (>50%), use the majority quantity.
- Where no majority exists, use the separately agreed conservative reconciliation rule unless/until the developer/user approves a change.
- Do not change this policy silently.


## 7. Verifiable Facts and Inference Control
- Do not substitute inference, assumption, prediction, or plausible completion for a fact that can be directly obtained or verified.
- When a required fact is obtainable from a source, file, drawing, current-time source, existing code, database, project record, or other authoritative evidence, retrieve and verify it before using it.
- This rule applies to all development information, including timestamps, filenames, PATCH numbers, versions, quantities, unit prices, specifications, existing code behavior, file existence, data structures, and prior approved decisions.
- Never present an inferred value as a confirmed fact.
- If direct verification is not possible, explicitly classify the information as one of:
  1. Confirmed fact;
  2. Explicit assumption / rational estimate;
  3. Unknown / requires confirmation.
- Rational estimation remains permitted where AZRAS specifications explicitly allow it, but the estimate must remain identifiable as estimated/provisional and must not overwrite confirmed source information.
- When a tool or authoritative source can provide the required fact, using an inference instead is a development error.
- For timestamps used in filenames or development records, obtain the actual current time at the moment of file generation; do not derive or guess it from conversation context.
- Until the public-release transition, existing timestamp naming conventions remain unchanged. Past files and timestamps must not be retroactively renamed or corrected.
- At public release, the official AZRAS documentation will define UTC (Coordinated Universal Time) as the standard timestamp basis for subsequent development, PATCHes, and formal management files.

## 8. Development and Audit Discipline
Before modifying code:
1. Read this Constitution.
2. Identify the currently approved architecture relevant to the task.
3. Determine whether the work is a normal implementation/bug fix or a method/architecture change.
4. If it is a method/architecture change or a potentially large/time-consuming task, consult the developer/user before implementation.

During implementation:
- Audit related/similar code paths when fixing a defect; avoid endless isolated PATCHes for the same defect family.
- Preserve previously verified normal behavior through regression tests.
- Do not allow temporary compatibility logic, obsolete schemas, old pricing rules, or superseded classifications to accumulate without identifying them for cleanup.
- When a developing problem suggests the chosen method is wrong or becoming disproportionately expensive, report it early.

## 9. PATCH Rules
- PATCH filenames use `YYMMDD_HHMM_<ProductName>_PATCH_<sequence>.zip`.
- Preserve sequential PATCH numbering.
- PATCH ZIPs contain only files required to apply the change.
- Do NOT include unnecessary explanatory documents, audit reports, test reports, changelogs, or other development paperwork in distribution PATCH ZIPs unless specifically requested or operationally required.
- Development/audit records may be kept separately from the distribution PATCH.
- Do not create a PATCH merely to record discussion.

## 10. UI Verification
- Perform code review, automated checks and regression testing as far as reasonably possible before asking the developer/user to open the application.
- Request screenshots/manual UI confirmation only at meaningful checkpoints where actual rendering or environment-specific behavior must be verified.

## 11. Governing Principle
AZRAS development prioritizes:
1. correctness;
2. verified facts over inference wherever direct verification is possible;
3. consistency with approved architecture;
4. preservation of useful source quantities/evidence;
5. prevention of double counting and fabricated data;
6. explicit separation of confirmed facts, estimates/assumptions, and unknowns;
7. minimum unnecessary development work;
8. early consultation before expensive or architectural decisions;
9. maintainability and clean removal/migration of superseded logic.

If a proposed implementation conflicts with this file, stop and resolve the conflict with the developer/user before proceeding.
