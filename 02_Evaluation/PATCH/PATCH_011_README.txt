PATCH_011 — 260929 UTC — v2.2.0（Module 4 年別結果CSV保存エラーの修正）
========================================

対象ファイル:
  - services/long_term_environment_engine_v9_3.py（0年目の行に3列を追加）
  - core/csv_export.py（新規・結果CSVの共通書き出し）
  - module4/app.py（年別結果CSV保存・イベント別結果CSV保存）
  - module6/app.py（キャッシュフローCSV保存）
  - module7/app.py（イベント別費用CSV保存）
  - dev_checks/csv_export_fieldnames_self_check.py（新規）
  - VERSION.json / version_info_AZRAS_Evaluation.txt（自動生成）/ CHANGELOG.md

症状:
  Module 4「年別結果CSV保存」で次のエラーが出て保存できない。
    ValueError: dict contains fields not in fieldnames:
    'climate_temperature_offset_C', 'operational_change_factor', 'climate_energy_factor'
  （writeheader の後で停止するため、ヘッダー行だけのCSVが残る場合あり。そのファイルは破棄してください）

原因:
  CSVの列見出しを「1行目（0年目＝初期建設）」のキーだけで作っていた。
  0年目の行には、1〜200年目の行にある気候関連3列が無かったため、2行目で停止。

修正（方針①：3列をCSVに出力する）:
  1. 0年目の行にも3列を追加（全行が同じ列構成）。
       climate_temperature_offset_C … 将来気候系列の0年目の値
       climate_energy_factor        … 将来気候系列の0年目の値
       operational_change_factor    … 1.0（基準）
     0年目は運用なし（運用CO2・運用エネルギーは従来どおり0）。参考値であり、
     他の計算結果は一切変わりません。
  2. core/csv_export.py：全行のキーの和集合（出現順）を列見出しにする共通処理。
     PATCH_011より前に保存したProject JSON（0年目に3列が無い）も保存でき、
     その場合0年目の3列は空欄になります。列が落ちることはありません。
     Module 4（年別・イベント別）、Module 6、Module 7 のCSV保存に適用。
  3. dev_checks/csv_export_fieldnames_self_check.py：
     「1行目だけで列見出しを作るコード」「0年目の列不足」「年別CSVに3列が出ない」
     のいずれかがあれば FAIL。

注意:
  既存のProject JSONの0年目の3列を埋めたい場合は、Module 4 を再計算・保存してください。

検証:
  - dev_checks 18/18 PASS、full_self_check PASS
  - Module 4 画面で「年別結果CSV保存」「イベント別結果CSV保存」を実行（新規計算／旧保存データの両方）→ 201行・3列出力を確認
  - 01 Planning / 03 Compare / 00 Installer は変更なし（各 dev_checks PASS）。
    03 Compare は annual_timeline の特定列のみ読むため影響なし。
