AZRAS Planning PATCH 599

Reported problem:
The user selected AZRAS Platform before loading the PDF, but after PDF loading /
Drawing Analysis the UI returned to General Building.

Root cause:
Drawing registration persisted only `structure_type` and did not persist the
complete selected construction identity. At the same time, the drawing
auto-detection path was still allowed to update structure/profile information
for a fresh Project. This allowed a later restore/profile-resolution path to
fall back to General Building.

Correction:
1. Explicit user construction selection is authoritative.
2. Building System + Structure + Method + Building Type are persisted together.
3. PDF recognition cannot replace an explicitly selected construction system.
4. Drawing Analysis locks the pre-analysis construction selection and restores
   it before calculation-profile resolution and before final save.
5. The rule applies equally to:
   - AZRAS Platform
   - General Building / timber
   - General Building / steel
   - General Building / RC
   - other registered construction methods

PDF recognition may still report that a drawing appears inconsistent with the
selected construction method, but it may not silently change the user's choice.

Regression:
PATCH 599 + previous five PATCH range checked.
