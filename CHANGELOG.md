# Changelog — AZRAS System

This file records changes to the AZRAS System suite as a whole. Detailed patch notes and regression records of each product are in its `PATCH/` folder.

## v2.2.0 patch update — 2026-10-01

No product version change; the patch numbers are:

| Product | Version | Patch |
|---|---|---|
| AZRAS Installer | 5.0.4 | PATCH_004 |
| AZRAS Planning | 2.2.0 | PATCH_052 |
| AZRAS Evaluation | 2.2.0 | PATCH_014 |
| AZRAS Compare | 2.2.0 | PATCH_010 |

### Added

- **Planning — regional unit-price table (PATCH_052).** Projects in the same region used to get different AI unit prices for the same item, because each Project asked the AIs again. Module 5 can now register a Project's adopted multi-AI prices in one standalone, versioned table per region (`<JSON folder>/Regional_Unit_Price_Tables/AZRAS_UNIT_PRICE_TABLE_<region>_<YYYY-MM>.json`, not per construction method) and apply it to later Projects of that region before AI research. Prices are matched by item, spec (construction method only for formwork, concrete, reinforcing steel and phenolic foam), unit and scale class (gross floor area up to 300 m², up to 3,000 m², larger; boundaries editable in the table). Only unregistered items are sent to the AIs; a registered price is never overwritten (new prices need a new version), and no price is borrowed from another scale class. The Project's price-basis record carries the table version and SHA-256.
- **Compare — regional price-table check (PATCH_010).** Projects of the same region priced from different table versions, or with different prices for the same table entry, get a warning with the procedure to align them. Different regions and different scale classes are not conflicts.
- Self-checks for each change above; `tests/run_all.py` passes 82/82.

### Changed

- **Planning — drawing registration (PATCH_052).** The Module 1 *Add drawings* (図面追加) button was removed. When any drawing changes, the complete drawing set is loaded again with *Load PDF/ZIP* (several PDFs at once, or one ZIP), so AI results always belong to one drawing set.

## v2.2.0 patch update — 2026-09-30

Fixes after the baseline release, found while comparing the 2x6, AZRAS and RC Frame terrace-house samples. No product version change; the patch numbers are:

| Product | Version | Patch |
|---|---|---|
| AZRAS Installer | 5.0.4 | PATCH_004 |
| AZRAS Planning | 2.2.0 | PATCH_051 |
| AZRAS Evaluation | 2.2.0 | PATCH_014 |
| AZRAS Compare | 2.2.0 | PATCH_009 |

### Fixed

- **Planning — gross floor area (PATCH_051).** A per-dwelling finish-area note (`天井と床面積：37.60m2/戸`) was read as the building's floor area, giving 37.6 m² instead of 245.1 m² for the AZRAS sample; rent, heating/cooling and CO2 were then computed for a sixth of the building. Per-dwelling/per-room values and finish-area notes are no longer floor-area candidates; footprint × storeys is used when no written area fits the plan.
- **Planning — foundation earthwork (PATCH_050).** RC Frame projects had no earthwork: Module 5 read a ground-beam length key that nothing wrote, while Module 1 had measured the length on the foundation plan. 2x6 projects had no strip-foundation geometry: internal strip footings were never measured on the foundation plan. The foundation plan is now measured including internal strips, and excavation, backfill, imported fill, soil disposal, blinding concrete and sub-base reach Module 5 for all three methods. The 2x6 slab uses the area inside the stems, and the strip-footing concrete is included in the provisional foundation rebar.
- **Evaluation — Module 4 annual CSV (PATCH_011).** Saving failed with "dict contains fields not in fieldnames"; result CSVs now use the union of all row keys.
- **Evaluation — CSV file names (PATCH_012).** Module 6 and Module 7 proposed the same default file name and could overwrite each other.
- **Installer / Evaluation — missing Python packages (Installer PATCH_004, Evaluation PATCH_013).** Planning and Evaluation stopped at start-up on a Python without packages. The Installer now lists missing packages and shows the install command (it does not install); Evaluation has a `requirements.txt`.
- **Compare — price-basis warning (PATCH_008).** Comparison copies made with the premise book still got the "unit-price basis differs" warning; the premise-book lists now show buildings 1–7.

### Added

- **Compare — same-building check and persistent alert (PATCH_009).** The premise book compares gross floor area, footprint, storeys and dwelling units; a floor-area difference over 3 % or any storey/unit difference must be decided before copies are made. A red alert above every tab stays while comparison copies are not recalculated or are of different-sized buildings.
- **Planning / Evaluation — CSV language (Planning PATCH_049, Evaluation PATCH_014).** Result CSVs follow the UI language: Japanese headers and labels in Japanese, English output unchanged.
- Self-checks for each fix above; `tests/run_all.py` passes 80/80.

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
