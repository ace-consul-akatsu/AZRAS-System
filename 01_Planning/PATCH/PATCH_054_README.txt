PATCH_054 — 261001 UTC — v2.2.0（Module 5 地域単価表の保存先を指定）
========================================

対象ファイル:
  - module5/app.py（登録時の保存先確認ダイアログ、保存先の表示と変更ボタン）
  - services/project_export_paths.py（保存先の記憶：configured_price_table_directory / set_configured_price_table_directory）
  - dev_checks/patch_054_price_table_folder_self_check.py（新規）
  - dev_checks/patch_052_regional_unit_price_table_self_check.py（新しいダイアログに「この保存先で登録」と答える1行を追加）
  - VERSION.json / version_info_AZRAS_Planning.txt（自動生成）/ CHANGELOG.md

要望:
  AZRAS_UNIT_PRICE_TABLE_Japan_Nagoya_2026-10.json が、案件の保存場所（C:\AZRAS_v2.2.0\JSON\…）とは
  全く別の場所（Dropbox\015_AZRAS\AZRAS_v2.2.0\260923_JSON\Regional_Unit_Price_Tables）に保存された。
  登録の段階で保存先を指定できるようにする。

原因:
  地域単価表の保存先は「Module 0 で設定した Project JSON 保存フォルダー（AppData の設定）」の下の
  Regional_Unit_Price_Tables に固定されていた。開いている Project JSON の場所とは無関係なため、
  以前に設定した Dropbox のフォルダーに保存された。

対応:
  1. 「AI採用単価を地域単価表へ登録」を押すと、最初に保存先の確認画面を表示する。
       ［この保存先で登録］［変更…］［既定に戻す］［キャンセル］
     同じ地域の表の有無（追加／新しい版）も、選んだフォルダーで判定する。
  2. 選んだフォルダーは記憶し（AZRAS_Platform\storage_settings.json の regional_price_table_directory）、
     以後の「地域単価表を適用」「登録」「内容を確認」すべてで使う。選んだフォルダーにそのまま保存する
     （Regional_Unit_Price_Tables を自動で付け足さない）。
  3. 地域単価表の欄に現在の保存先（指定／既定）を表示し、「地域単価表の保存先を変更」ボタンを追加。
  4. 「適用」で表が見つからない場合、別のフォルダーにあれば保存先を変更するよう案内する。

変更していないもの:
  - Project JSON の保存フォルダー設定（Module 0）。
  - 未指定の場合の保存先（従来どおり <Project JSON 保存フォルダー>\Regional_Unit_Price_Tables）。
  - 地域単価表のファイル名・内容・版の付け方（PATCH_052）。PATCH_053 の内容。

既に作られた表について:
  Dropbox に保存された AZRAS_UNIT_PRICE_TABLE_Japan_Nagoya_2026-10.json は、使いたいフォルダーへ
  移動（またはコピー）し、「地域単価表の保存先を変更」でそのフォルダーを選べば、そのまま使えます。
