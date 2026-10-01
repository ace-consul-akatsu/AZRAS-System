PATCH_055 — 261001 UTC — v2.2.0（地域単価JSON・地域プロファイルの保存先を指定／保存先の横断確認）
========================================

対象ファイル:
  - module5/app.py（保存先の共通の仕組み、保存時の確認画面、「ユーザーデータの保存先（一覧）」）
  - services/project_export_paths.py（configured_user_data_directory / set_configured_user_data_directory。PATCH_054 の関数名は残す）
  - services/regional_profile_catalog.py（指定フォルダーと既定フォルダーの両方を読む）
  - services/construction_cost_engine_v9_4.py（地域単価JSONの検索に指定フォルダーを追加）
  - dev_checks/patch_055_user_data_folders_self_check.py（新規）
  - VERSION.json / version_info_AZRAS_Planning.txt（自動生成）/ CHANGELOG.md

要望:
  1. 地域単価JSON（手動取込・編集）と地域プロファイル（追加分）も、地域単価表と同じように保存先を指定できるようにする。
  2. その他（02 Evaluation・03 Compare を含む）も確認する。

1. 対応内容
  原因: 2つともソフト本体の中（data\regional_cost、data\regional_profiles）に固定で保存していたため、
        完全版zipでフォルダーを差し替えると消えていた。
  ・保存の前に保存先の確認画面を表示：［この保存先に保存］［変更…］［既定に戻す］［キャンセル］
      - 「地域単価JSONを取込（手動）」「地域単価を編集（手動）」の保存
      - 「地域プロファイル追加」は入力画面に保存先の行（変更…／既定に戻す）を追加
  ・選んだフォルダーは記憶（AZRAS_Platform\storage_settings.json：
      regional_cost_user_directory / regional_profile_directory）。地域単価表（PATCH_054）と同じ仕組み。
  ・読み込みは「指定フォルダー」と「既定フォルダー」の両方から行う。差し替え前に保存したファイルや、
    ソフト同梱の地域単価JSON（JP_Nagoya_2026.json 等）も引き続き使われる。
      - Module 5 の計算（同じ地域の最新 data_date を採用）
      - 代表地域プロファイルの一覧（PATCH_053）
      - Module 5 の自動再計算
  ・地域単価表の欄に「ユーザーデータの保存先（一覧）」ボタン：3種類の保存先をまとめて表示・変更。

  おすすめ: 3つともソフトの外の同じ親フォルダー（例：Dropbox\015_AZRAS\AZRAS_UserData\…）にすると、
  ソフトの差し替えで消えず、パソコンが変わっても同じデータを使えます。

2. 確認結果（保存先の横断確認）
  01 Planning:
    ・Module 0 の Project JSON 保存フォルダーの下に固定されていたのは地域単価表のみ（PATCH_054 で対応済み）。
    ・ソフト本体の中に固定されていたのは上記2つのみ（今回対応）。
    ・それ以外（Module 1 の AI積算 R1 フォルダー、PDF取込、Module 5 の AI_CostProvider と変更履歴、
      Module 2 の 8760時間結果・比較、Module 9 の地域Project・気象データ、各ModuleのCSV・PDF）は、
      開いている Project JSON と同じ物件フォルダー、または保存ダイアログで選んだ場所に保存される。
  02 Evaluation（v2.2.0 patch 14）:
    ・保存はすべて Project JSON と同じ物件フォルダー、または保存ダイアログ。固定の保存先なし。変更不要。
    ・参考：Evaluation の自動再計算にも Module 5 の再計算処理があるが、Module 5 は Module 1 の下流としてしか
      再計算されない（Module 1 は Planning 側）ため、Evaluation から実行されることはない。
  03 Compare（v2.2.0 patch 10）:
    ・比較グループの作成・CSV保存はすべてダイアログで保存先を選ぶ。固定の保存先なし。変更不要。
  3製品共通（設定ファイル、データではない）:
    ・保存先設定 %APPDATA%\AZRAS_Platform\storage_settings.json、画面設定 Documents\AZRAS_Platform\ui_settings.json、
      表の列幅 ~\.azras_platform\table_widths.tsv。いずれもソフトの外にあるため差し替えで消えない。変更不要。

変更していないもの:
  - 既定の保存先（未指定なら従来どおりソフト内）、ファイル名・内容、地域単価表（PATCH_052/054）、PATCH_053。
