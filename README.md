# AZRAS System v2.2.0 — Experimental Research Release

**English** | [日本語](README.ja.md)

<!-- After Zenodo issues the DOI, replace XXXXXXX (the "all versions" concept DOI) and uncomment:
[![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.XXXXXXX.svg)](https://doi.org/10.5281/zenodo.XXXXXXX)
-->
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

> **This repository is an experimental, AI-assisted software development record. It is not production-ready software.**
> A cross-audit of v2.2.0 found known inconsistencies in the calculation results. They are intentionally documented below as part of the research record.
> **Estimated construction costs and construction-method comparisons from this release must not be used for design, construction, investment or business decisions.**

AZRAS System is an open-source desktop suite for planning, evaluating and comparing buildings over a **200-year life cycle**. It starts from construction drawings printed to PDF and carries a project through quantity takeoff, environmental and energy analysis, repair/renewal/demolition scenarios and long-term business evaluation, then compares construction methods, specifications and locations side by side.

It is provided free of charge on the premise of use for **AI research and business purposes**.

## Status of this release — published unfinished, on purpose

AZRAS was developed from June 2026 by an architect with no programming background, entirely through conversations with several AIs (ChatGPT, Claude, Gemini, Meta AI and others). The four products now total about 90,000 lines of Python, built up over more than 600 patches.

To verify the results, the same building (same floor plan, same exterior) was processed in three construction methods — **2×6**, **AZRAS** and **RC Rahmen** (the drawings are in [examples/](examples/)) — and ChatGPT and Claude were asked to cross-audit the final Project JSON files. The audit found numerous defects, although each earlier fix had been reported by the AIs as complete, had passed their audits, and the full test suite (`tests/run_all.py`, 85/85) was passing.

When asked directly, both AIs named the same root cause: fixes had been made symptom by symptom in conversation, while the structure underneath — the same values stored in several places, two separate construction-cost calculations, matching by item names — let the same kinds of errors come back through other paths.

A finished version will take more time. This release is therefore published **deliberately in its unfinished state**:

- as a lesson and a development history for future work,
- as research material on the current limits of AI-assisted software development, and
- as a fixed, citable record of what AI could and could not do as of 2026.

Release path: **GitHub release → automatic archiving on Zenodo → DOI**.

### Three things kept separate

1. **The architectural concept** — the AZRAS building system and the RC Upright Method (patent JP 2005-240511). The software defects below are **not** findings about the validity of the construction method.
2. **The software implementation** — this release, with the known limitations below.
3. **The AI development experiment** — the record of how the software was built with AI, and where that process broke down.

### Known limitations (confirmed in the cross-audit)

- **Geometry differs between modules:** for the same building, the canonical window area was 55.74 m² while the Module 2 input was 0 m².
- **Quantities silently dropped:** insulation quantities were aggregated for the roof only; wall insulation was missing.
- **Price tables:** tables with the same version name had different contents.
- **Duplicate calculation paths:** two separate pieces of code performed the same construction-cost calculation.
- **Method-independent items priced by method:** the unit price of the same window differed by 28% between construction methods.
- **Unit-price scope:** some material-only unit prices were treated as if they included installation. **This is part of the reason the AZRAS method currently shows a lower total.**
- **Overall effect:** for the same building, the estimated total shifted by several million yen.
- **The audits were also wrong:** several of the AIs' own audit findings turned out to be untrue when checked against the code.

Some of these were partly fixed in later development builds (October 2026). Those builds are not part of this release, and the root cause remains.

### What would be needed (not yet implemented)

- **One canonical owner** for geometry, openings, quantities, prices and construction method. Every module reads from it and keeps no copy of its own; AI answers and old snapshots are kept only as evidence.
- **Automatic invariant checks** — e.g. window total = sum by orientation; every Module 1 quantity is either costed or excluded with a reason. Saving, Evaluation and Compare stop on any contradiction.
- **Regression tests with known answers**, using the 2×6, RC and AZRAS cases as reference fixtures.
- **Design rules decided and written down before implementation**, not inside conversations.

The conversations in which ChatGPT and Claude acknowledged the root cause are published in English as [When AI Says "Done"](docs/en/07_AZRAS_When_AI_Says_Done_EN.pdf). An earlier episode of the same kind (September 2026) is recorded in the official development history below.

## What it does

- **Quantity takeoff from PDF drawings** — AZRAS reads the drawings itself and hands the items it cannot resolve to AI.
- **Multiple independent AIs, evidence first** — the same request package can be answered by several AI services (e.g. ChatGPT, Claude, Gemini). Each answer is kept as a separate candidate with its evidence and calculation basis. Only like quantities in like units are compared, the result is **never decided by majority vote**, and anything unresolved goes to human review. Every quantity is classified as confirmed, assumed/provisional, or to be verified.
- **Longitudinal observation of AI** — the identical drawing set and request can be resent to AIs at later dates. SHA-256 hashes prove the drawings are the same, so changes in AI drawing-reading ability can be observed over time.
- **Environment and energy** — CO2 emissions and energy use from 8,760-hour regional weather data, including insulation-specification comparisons.
- **200-year evaluation** — repair, renewal and demolition scenarios and costs, and a 200-year business cash flow with present-value analysis.
- **Comparison** — the same plan under different construction methods, specifications or climates, from saved results only.

AZRAS Planning **does not call AI-service APIs**. It exports request files that the user exchanges with the AI services of their choice, and it imports the returned JSON under explicit validation.

## Products

| Folder | Product | Role |
|---|---|---|
| `00_Installer` | AZRAS Installer 5.0.4 | Checks the environment, creates the AZRAS desktop icon, launcher |
| `01_Planning` | AZRAS Planning 2.2.0 | Planning conditions, drawing analysis, quantities, AI takeoff, Project JSON |
| `02_Evaluation` | AZRAS Evaluation 2.2.0 | 200-year environment, renewal scenarios and costs, 200-year business |
| `03_Compare` | AZRAS Compare 2.2.0 | Read-only comparison of saved Project JSON results |

Data flow: **01 Planning → 02 Evaluation (calculates and saves) → 03 Compare (reads saved results only)**. The products exchange data only through Project JSON (schema 3.0, [schemas/project_schema_v3_0.json](schemas/project_schema_v3_0.json)).

## Requirements

- Windows 10 / 11
- Python 3.13 (64-bit) from [python.org](https://www.python.org/) — Tkinter is included
- Python packages: see [requirements.txt](requirements.txt)

## Getting started

1. Download this repository (**Code → Download ZIP**) and extract it, keeping the folder layout.
2. Install the Python packages from the extracted folder:
   ```
   py -m pip install -r requirements.txt
   ```
3. Run `00_Installer\run_AZRAS_Installer_without_build.bat`. It checks Python and can create the AZRAS icon on the desktop and Start menu.
4. Start AZRAS from that icon, or run `00_Installer\run_AZRAS_Launcher_without_build.bat`, and choose Planning, Evaluation or Compare.

Each product can also be started on its own with the `run_AZRAS_<Product>_without_build.bat` file in its folder.

Windows executables can be built with `build_AZRAS_Planning.bat` and `build_AZRAS_Evaluation.bat` (PyInstaller); the EXE version resource is generated from `VERSION.json`.

## Documentation

Detailed documents in English and Japanese (Word):

| Document | English | 日本語 |
|---|---|---|
| Overview | [EN](docs/en/01_AZRAS_Overview_v2_2_0_EN.docx) | [JA](docs/ja/01_AZRAS_Overview_v2_2_0_JA.docx) |
| User manual | [EN](docs/en/02_AZRAS_User_Manual_v2_2_0_EN.docx) | [JA](docs/ja/02_AZRAS_User_Manual_v2_2_0_JA.docx) |
| Key features | [EN](docs/en/03_AZRAS_Key_Features_v2_2_0_EN.docx) | [JA](docs/ja/03_AZRAS_Key_Features_v2_2_0_JA.docx) |
| Development constitution (rules for modifying AZRAS with AI) | [EN](docs/en/04_AZRAS_Development_Constitution_v0_4_EN.docx) | [JA](docs/ja/04_AZRAS_Development_Constitution_v0_4_JA.docx) |
| How AZRAS can be developed further | [EN](docs/en/05_AZRAS_Further_Development_v2_2_0_EN.docx) | [JA](docs/ja/05_AZRAS_Further_Development_v2_2_0_JA.docx) |
| Official development history, June – 7 Sep 2026 | [EN](docs/en/06_AZRAS_Official_Development_History_v2_0_EN.docx) | [JA](docs/ja/06_AZRAS_Official_Development_History_v2_0_JA.docx) |
| Official development history, update from 7 Sep 2026 | [EN](docs/en/06_AZRAS_Official_Development_History_v2_4_EN.docx) | [JA](docs/ja/06_AZRAS_Official_Development_History_v2_4_JA.docx) |
| When AI Says "Done" — the conversations in which ChatGPT and Claude acknowledged the root cause (PDF) | [EN](docs/en/07_AZRAS_When_AI_Says_Done_EN.pdf) | — (original conversations are in Japanese) |

## Sample data

Drawing sets of the same building plan in three construction methods, printed to PDF — ready to load into AZRAS Planning:

- [AZRAS (RC Upright Method)](examples/261001_0150_AZRAS.pdf)
- [Timber 2×6](examples/261001_0150_2x6.pdf)
- [Conventional RC frame](examples/261001_0150_RC_Rahmen.pdf)

The complete sample projects processed with v2.2.0 — Project JSON with saved results, regional variants, and the full multi-AI takeoff round with the independent answers of ChatGPT, Claude and Meta AI — are published as a separate dataset on Zenodo (CC BY 4.0). <!-- Add the dataset DOI here after registration. -->

## How to cite

If you use AZRAS System in research, please cite it. GitHub's **"Cite this repository"** button (from [CITATION.cff](CITATION.cff)) gives APA and BibTeX formats.

> Akatsu, M. (2026). *AZRAS System* (Version 2.2.0) [Computer software]. ACE Comprehensive Consulting Co., Ltd. https://github.com/ace-consul-akatsu/AZRAS-System

```bibtex
@software{akatsu_azras_system_2026,
  author    = {Akatsu, Makito},
  title     = {AZRAS System},
  version   = {2.2.0},
  year      = {2026},
  publisher = {ACE Comprehensive Consulting Co., Ltd.},
  url       = {https://github.com/ace-consul-akatsu/AZRAS-System}
}
```

A DOI will be added here once the release is archived on Zenodo.

## Disclaimer

**This release is a research record.** The cost and comparison results in particular contain the known errors listed above.

All calculation, analysis and comparison results are reference information for planning, comparison and research. They do not guarantee design performance, structural safety, legal compliance, costs, construction periods or investment outcomes, and agreement among several AIs does not guarantee correctness. Users must verify inputs, AI answers and results themselves and consult qualified professionals for important decisions.

Please read the full disclaimer before use:

- [Disclaimer of Use (English)](docs/DISCLAIMER.md)
- [利用にあたっての免責（日本語）](docs/DISCLAIMER.ja.md)

Word versions for printing and formal distribution are in [docs/](docs/).

If the Japanese and English versions differ, the Japanese version prevails.

## License

[MIT License](LICENSE) — Copyright (c) 2026 ACE Comprehensive Consulting Co., Ltd.

## Repository layout

| Path | Contents |
|---|---|
| `00_Installer/` … `03_Compare/` | The four products |
| `docs/` | Disclaimer (Markdown and Word, English and Japanese); `docs/en/`, `docs/ja/` detailed documents |
| `schemas/` | Public copies of the schemas the products use (Project JSON 3.0, AI takeoff) |
| `examples/` | Drawing sets of the same plan in three construction methods |
| `tests/` | One-command check of all products and of the connections between them |

## For developers

- Run every check with one command from the repository root: `python tests/run_all.py` — each product's own self-checks (`dev_checks/`) plus the repository checks (schema copies, disclaimer text, Project JSON hand-off, market-rent contract, launcher). A check that cannot run counts as a failure.
- `VERSION.json` is the single source of truth for each product's version.
- Patch notes and regression records are in each product's `PATCH/` folder.
- The files in `schemas/` are copies; the software reads the originals inside the product folders. `tests/check_schemas.py` keeps them identical.

## Related

- Website: https://ace-consul-akatsu.github.io
- AZRAS building system (RC Upright Method) — design concept and verification data: [Adaptive-Zero-Rebuild-Asset-System-AZRAS](https://github.com/ace-consul-akatsu/Adaptive-Zero-Rebuild-Asset-System-AZRAS)

---

Developed by **ACE Comprehensive Consulting Co., Ltd.** (株式会社ACE総合コンサル), Kasugai, Aichi, Japan.
