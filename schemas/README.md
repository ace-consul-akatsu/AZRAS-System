# schemas

Public copies of the schemas used by AZRAS System v2.2.0. The software reads the originals inside the product folders; `tests/check_schemas.py` fails if a copy here differs from its original. The mapping is in [manifest.json](manifest.json).

| File | Describes |
|---|---|
| [project_schema_v3_0.json](project_schema_v3_0.json) | Project JSON 3.0 — the file saved by Planning and Evaluation and read by Compare |
| [AZRAS_AI_TAKEOFF_SCHEMA_v1.0.json](AZRAS_AI_TAKEOFF_SCHEMA_v1.0.json) | Quantity-takeoff answer returned by each AI |
| [AZRAS_AI_TAKEOFF_FINAL_REVIEW_SCHEMA_v1.0.json](AZRAS_AI_TAKEOFF_FINAL_REVIEW_SCHEMA_v1.0.json) | Final review after comparing the independent AI answers |
| [AZRAS_AI_Return_Metadata_Schema_v1.1.json](AZRAS_AI_Return_Metadata_Schema_v1.1.json) | Metadata each AI returns for longitudinal observation |

---

AZRAS System v2.2.0 が使うスキーマの公開用の写しです。ソフトは各製品フォルダ内の原本を読みます。写しが原本と異なると `tests/check_schemas.py` が不合格になります。対応関係は [manifest.json](manifest.json) にあります。
