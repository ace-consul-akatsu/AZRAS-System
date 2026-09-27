# Changelog — AZRAS System

This file records changes to the AZRAS System suite as a whole. Detailed patch notes and regression records of each product are in its `PATCH/` folder.

## v2.2.0 — 2026-09-24 (baseline release)

First public release of AZRAS System, published as a baseline after a cross-product audit of all four products.

| Product | Version | Patch |
|---|---|---|
| AZRAS Installer | 5.0.4 | PATCH_003 |
| AZRAS Planning | 2.2.0 | PATCH_048 |
| AZRAS Evaluation | 2.2.0 | PATCH_010 |
| AZRAS Compare | 2.2.0 | PATCH_007 |

### Fixed

- **Compare — market-rent contract.** In market-rent mode Compare reported the inactive target-yield preference as the target yield and listed it as a premise difference; comparison copies now keep the Evaluation save shape (`target_gross_yield_active = false`, preference kept).
- **Planning / Evaluation — Windows EXE build.** The PyInstaller version resource was plain text that PyInstaller cannot read, which stopped the build; it is now generated from `VERSION.json`. The Planning EXE also showed a fallback version and left the AI protocol, schema and template files out of the AI request package.
- **Planning — AI request package.** The Japanese longitudinal-observation protocol was looked up under a file name that did not exist and was never sent; the English protocol lacked two of its sections.
- **Planning / Evaluation — Project JSON schema.** The published schema fixed `schema_version` to 2.0 while the products save 3.0; `project_schema_v3_0.json` describes the current format.
- **Planning — duplicate dictionary keys** in the display-label table.
- **Self-checks.** The undefined-name check passed when it could not run; it now fails.

### Changed

- **Versions.** `VERSION.json` is the single source of truth in every product; README, NOTICE, build files and the screens state the same version.
- **License.** All products are under the MIT License (copyright ACE Comprehensive Consulting Co., Ltd.); each product's `LICENSE.txt` and License window match the repository `LICENSE`.
- **Publication.** Real client and project names were removed from the source.

### Added

- Self-checks in every product for version consistency, duplicate keys, undefined names and license text; Project JSON schema consistency in Planning and Evaluation.
- Repository: `tests/` (one-command check of all products and of the connections between them), `schemas/`, `examples/`, `docs/` with the disclaimer and the detailed documents in English and Japanese, `CITATION.cff`.
