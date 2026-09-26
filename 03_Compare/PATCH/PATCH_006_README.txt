PATCH_006 — 260923 UTC — v2.2.0
========================================

対象ファイル:
  - main.py
  - comparison/extractor.py
  - comparison/premise_book.py
  - comparison/premise_book_ui.py
  - comparison/display_ja.py（新規・日本語表示名。表示専用）
  - dev_checks/patch_006_japanese_display_no_english_self_check.py（新規）
  - VERSION.json

要望内容:
  03_Compare の表・グラフを日本語表示にしたとき、英語が混ざる。

原因と修正:
  1. 起動時の言語は英語。注記（【ご注意】①～⑤）・年ボタン（50年～200年）・
     集計表見出しなどを英訳済みの文字で作っていたため、日本語へ切り替えても
     英語のまま残っていた。→ 画面部品は日本語正本で作り、英語で作られた部品も
     逆引きで日本語へ戻るようにした。集計表の見出しも言語切替のたびに更新。
  2. 月間グラフの縦軸単位 kWh/month・t-CO₂/month → kWh/月・t-CO₂/月。
  3. 表見出し「年間Energy kWh」→「年間エネルギー kWh」（CSVも同じ）。
  4. 工法名は英語名だけを読んでいた → 01 Planning が保存している
     construction_method_(detail_)name_ja を表示（例：[Conventional RC]→[一般RC]）。
     構造は内部ID（rc_frame）→ 構造名（RCラーメン構造）。用途の既定値 Residential→住宅。
  5. 世界地域別比較の都市名（Sapporo→札幌、Berlin→ベルリン 等）。
  6. 7. 比較前提表：工種キー・単位（lump_sum→一式）・種別・Module 6 設定名・
     設定値（market_rent→市場家賃を直接入力）・構造部位・「Cancel」を日本語化。
     所在地/通貨不一致の警告コードも日本語化。
  7. 不具合：比較前提表の project_label() が存在しない項目
     construction_method_name を読んでおり、常に内部ID（[rc_frame]）表示になっていた。
     保存される前提表のラベルは英語正本（construction_method_detail_name_en）に修正。
  8. 画面の版表示が 1.1.17 直書きだった → VERSION.json（2.2.0）から読む。

変更していないもの:
  - 保存値・比較キー（label）・前提表JSONの判定ロジック・計算は一切変更なし。
  - 日本語名は 01 Planning の construction_method_profiles.json /
    construction_cost_database_v9_4.json、02 Evaluation の lang/ja.json と
    Module 6 画面ラベルから転記。都市名・用途名の和名は標準的な表記を追加。
    対応表に無い値は推測せずそのまま表示する。
  - 残す英字（意図的）：CO₂・kWh・m² 等の単位、JSON、Project、Module、EPW、CF、JPY、
    AZRAS Platform（01 Planning 側の日本語名も同じ表記）、参照先データパス名。

確認:
  - 新規 dev_check：英語起動→日本語切替→比較実行→全タブの表示文字を走査し、
    許可リスト外の英単語ゼロを確認。英語へ戻した時に日本語が残らないことも確認。
  - 既存 dev_checks 5本＋新規1本 すべて PASS、pyflakes 警告なし。
