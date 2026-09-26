AZRAS Planning PATCH 538

Fixes:
1. Module 9 active-Project storage rebinding for Project-local Data/EPW/coefficient paths.
2. Module 9 blank-list recovery from already-generated regional Project JSON provenance.
3. Japanese UI localization of RC-MRF canonical quantity names in Module 1 and Module 5.

Important:
- Regional JSON recovery uses regional_derivation.base_project_id/base_project_file. It does not guess by filename.
- Existing EPW files are not deleted or moved. Future EPW downloads are written under the currently active Project's Data/<method>_気象情報/<country>.
- Internal canonical data stays English; only presentation is translated.
