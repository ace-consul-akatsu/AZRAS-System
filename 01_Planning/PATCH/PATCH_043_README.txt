PATCH_043 — 260922 UTC — v2.2.0
========================================

対象ファイル:
  - core/project_store.py
  - core/project_coordinator.py
  - module0/app.py
  - module5/app.py
  - regional_analysis/module9_ui.py
  - core/detailed_configuration_ui.py
  - services/construction_cost_engine_v9_4.py
  - dev_checks/patch_043_comparison_copy_control_self_check.py（新規）

要望内容:
  03 Compare が比較グループフォルダー内に作る「比較用コピー」を、
  01 Planning 側で安全に扱えるようにする。コピーは Module 5 の
  再計算だけを許し、それ以外の入力は元Projectと同一に保つ。

対応:
  1. comparison_copy マーカー（AZRAS_COMPARISON_COPY_V1）を認識する
     comparison_copy_info / comparison_copy_block_reason を project_store に追加。
  2. update_module_and_propagate（Module 1・2・5 の保存経路）で、
     許可されていないModuleの保存を理由付きで拒否。
  3. 直接 save_project を呼ぶ経路にも同じ判定を追加。
       module0/app.py            Project情報の保存（保存先の移動も伴うため）
       core/detailed_configuration_ui.py  詳細構成の保存
       regional_analysis/module9_ui.py    地域解析（生成前に停止・一覧保存・復旧）
  4. Module 5 では、コピーに対する
       ・AI概算単価JSONの取り込み
       ・単価の手動編集
     を停止する。取り込みは単価の置き場を作り直すため、比較前提表で
     統一した単価が消えるため。
     ヘッダーに「【比較用コピー】…比較前提表: ファイル名（版）」を表示する。
  5. price_basis_fingerprint（PATCH_040）に比較前提表の単価を追加。
       basis_token = comparison_group_premise_book
                     （共通工種は前提表、工法固有工種は各ProjectのAI単価）
                   / mixed_comparison_group_and_regional_database
       comparison_group_priced_line_count / comparison_group_id /
       premise_book_file / premise_book_version を記録。

検証（実エンジン）:
  RC のコピーに前提表単価（ドア 204,816.92 円/㎡）を書き込んで再計算すると、
  単価 204,816.92・pricing_status comparison_group_confirmed・
  表示 confirmed_price・basis_token comparison_group_premise_book となる。
  併せて落とし穴も確認した。コピーに新しい project_id を振るとき、
  単価データ側の紐付けID（PATCH_038 project_binding）を書き換えないと、
  エンジンは単価を丸ごと破棄して内蔵DB単価で計算する。
  03 Compare 側で必ず書き換える実装にしてある。

横断監査:
  - 通常Projectの挙動は変わらない（マーカーが無ければ全て従来どおり）。
  - Module 5 保存結果へのキー追加のみ。02 Evaluation / 03 Compare の
    読取Contract変更なし。
  - 既存PATCHフォルダーは削除・整理・上書きしていない。

回帰確認:
  - dev_checks/既存20本: 全てPASS
    （azras_scope_leakage_regression のみ tkinter 不在で停止。修正前と同一）
  - PATCH_043追加self-check: PASS（29項目）
  - pyflakes: 修正前後で警告が完全一致（差分0行）
