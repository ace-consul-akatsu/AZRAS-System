PATCH_014 — 260930 UTC — v2.2.0（CSVの日本語出力）
========================================

対象ファイル:
  - core/csv_export.py（拡張・01 Planning と同一）
  - lang/csv_ja.json（新規・CSV用の日本語見出し／コード値）
  - module3/app.py（タイムラインCSV）
  - module4/app.py（年別結果CSV・イベント別結果CSV）
  - module6/app.py（キャッシュフローCSV）
  - module7/app.py（イベント別積算CSV）
  - dev_checks/csv_language_self_check.py（新規・01 Planning と同一）
  - VERSION.json / version_info_AZRAS_Evaluation.txt（自動生成）/ CHANGELOG.md

要望内容:
  01 Planning の詳細数量CSVと同様に、その他のCSVも日本語を出せるように。

方針:
  - CSV は「保存したときの画面の言語」で出力する。
      英語 … 見出し・値とも従来とまったく同じ（内部キーが見出し）。
      日本語 … 見出しを lang/csv_ja.json で日本語化。工事種別・単価状態などの
               コード値も日本語化。数値は一切変えない。
  - 訳が無い列は空欄にせず英語のまま出す（dev_checks で検出）。
  - Project JSON・計算結果の内部データは英語正本のまま（表示のみの変更）。
  - 共通処理は core/csv_export.py（01 Planning と 02 Evaluation で同一ファイル）。

変更:
  1. Module 3 タイムラインCSV：見出し、工事種別・範囲・対象部位を日本語（画面の表と同じ名称）。
  2. Module 4 年別結果CSV：見出し、区分（新築時/年次）を日本語。
     Module 4 イベント別結果CSV：見出し、工事種別・CO₂計上区分・対象部位を日本語。
  3. Module 6 キャッシュフローCSV：見出しを日本語（38列）。
  4. Module 7 イベント別積算CSV：見出し、工事種別・対象部位（画面と同じ関数）、
     消費税の扱い・費用計上区分を日本語。
  - 最終動作確認CSVはすでに日本語対応済みのため変更なし。

確認:
  - dev_checks 全21本 PASS、full_self_check.py PASS。
  - 新規 csv_language_self_check：Module 3/4/6/7 の全列に日本語見出しがあり重複なし、
    英語出力が従来と同一。否定テスト：見出し1件削除・重複1件 → NG を確認。
  - 実際の保存関数を呼ぶ動作確認（日本語・英語）：Module 3・4（年別・イベント別）・6・7。
  - 計算・Project JSON の変更なし。
