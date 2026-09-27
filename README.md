# AZRAS System v2.2.0

**English** | [日本語](README.ja.md)

<!-- After Zenodo issues the DOI, replace XXXXXXX (the "all versions" concept DOI) and uncomment:
[![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.XXXXXXX.svg)](https://doi.org/10.5281/zenodo.XXXXXXX)
-->
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

AZRAS System is an open-source desktop suite for planning, evaluating and comparing buildings over a **200-year life cycle**. It starts from construction drawings printed to PDF and carries a project through quantity takeoff, environmental and energy analysis, repair/renewal/demolition scenarios and long-term business evaluation, then compares construction methods, specifications and locations side by side.

It is provided free of charge on the premise of use for **AI research and business purposes**.

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

## Sample data

Drawing sets of the same building plan in three construction methods, printed to PDF — ready to load into AZRAS Planning:

- [AZRAS (RC Upright Method)](examples/260805_AZRAS.pdf)
- [Timber 2×6](examples/260805_2x6.pdf)
- [Conventional RC frame](examples/260805_RC_Rahmen.pdf)

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
