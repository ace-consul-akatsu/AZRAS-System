PATCH_013 — 260930 UTC — v2.2.0（4製品横断監査の指摘対応）
========================================

対象ファイル:
  - requirements.txt（新規）
  - build_AZRAS_Evaluation.bat（不足時の案内文）
  - docs/maintenance/CURRENT_BUILD_GUIDE.txt（必要パッケージの行を追加）
  - dev_checks/language_combobox_liveness_self_check.py（新規・4製品共通）
  - VERSION.json / version_info_AZRAS_Evaluation.txt（自動生成）/ CHANGELOG.md

指摘1（重大）: パッケージの無い Python で起動できない
  パッケージを入れていない Python 3 で main.py を起動すると
  ModuleNotFoundError: No module named 'reportlab'（core/module_report.py）で停止した。
  起動時に実際に読み込むのは numpy・pandas（温熱・PV計算。project_coordinator 経由）と
  reportlab。01 Planning には requirements.txt があるが、この製品には無かった。
  → requirements.txt を追加：numpy / pandas / reportlab（必須）、
    pyflakes / jsonschema（dev_checks 用、「used by dev_checks only」と注記）。
  → 00 Installer PATCH_004 がこのファイルを読み、不足パッケージとインストール用コマンドを表示する
    （自動インストールはしない）。
  → build_AZRAS_Evaluation.bat は不足時に「python -m pip install -r requirements.txt pyinstaller」を案内。

指摘2（中）: 言語選択欄が空白になる不具合の検査が無い
  この不具合（StringVar が回収されて言語欄が空白になる）は本製品の Module 4/6 で見つかったが、
  検査スクリプトは他の3製品にしか無かった。
  → 4製品共通の dev_checks/language_combobox_liveness_self_check.py を追加（合格）。

確認:
  - 新しい Python（パッケージ無し）で起動 → 停止を再現。
    Installer が表示するコマンドを実行後 → 起動成功（xvfb で確認）。
  - dev_checks 20本すべて PASS、full_self_check.py PASS、pyflakes 未定義名なし。

変更していないもの:
  計算・Project JSON・画面。
