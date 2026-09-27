# tests

Run every check from the repository root:

```
python tests/run_all.py
```

| Script | Checks |
|---|---|
| `run_all.py` | Runs each product's own self-checks (`dev_checks/`, `full_self_check.py`) inside its folder, then the checks below |
| `check_cross_product.py` | Planning → Evaluation → Compare Project JSON hand-off; Evaluation → Compare market-rent contract; launcher targets |
| `check_schemas.py` | `schemas/` copies are identical to the originals in the products |
| `check_disclaimer.py` | `docs/DISCLAIMER*.md` carry exactly the text of the Word versions |
| `check_filenames.py` | Every file and folder name is plain ASCII (so no ZIP tool can garble it) |

The product checks need the packages in `requirements.txt`. A check that cannot run counts as a failure.

---

リポジトリのルートで `python tests/run_all.py` を実行すると、全製品の自己検査と、製品間の接続・スキーマの写し・免責文の一致をまとめて検査します。実行できなかった検査は不合格として扱います。
