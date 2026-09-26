PATCH_024 — 260918 UTC — v1.0.629
========================================

対象ファイル:
  - module1/app.py（新規 AZRAS_AI_STANDARD_RULES_V2_EN 定数、
    _ai_takeoff_request_text / _ai_takeoff_recheck_request_text へ挿入）
  - module5/app.py（新規 AZRAS_AI_STANDARD_RULES_V2_EN 定数、
    _ai_cost_request_text / _ai_cost_review_request_text /
    _ai_cost_recheck_request_text へ挿入）

経緯:
  PATCH_023に続き、マルコ氏より「AZRAS AI依頼文 標準ルール(v2)」
  （回答時間10分制限＋権限最小化・サンドボックス化・人間承認・監視の
  4項目）を、別添付ではなく依頼文本文に直接埋め込むよう依頼された。
  これは事前のやり取りで「本文に直接入れる方式を推奨する」と回答した
  内容の実装。

対応:
  両ファイルに共通のモジュールレベル定数
  AZRAS_AI_STANDARD_RULES_V2_EN（英語canonical、5項目）を新設し、
  AZRASが生成する全AI依頼文の「Project: ...」行の直後に共通ヘッダー
  として挿入した。
    1. 回答時間10分以内を目標とし、超過見込み時は中間報告のうえ続行
       可否を確認する。ただし精度を犠牲にしてまで10分に収めることは
       優先しない。
    2. 権限の最小化（認証を要する閉域網への接続・ログイン試行・認証
       情報の推測使用を一切行わない、提供資料と一般公開Web以外の
       データ取得を行わない、無許可の外部システム書き込み/実行を
       行わない）
    3. サンドボックス化（提供資料・一般公開Web情報の範囲に限定、
       外部システムに実害が及ぶ操作を行わない）
    4. 人間承認チェックポイント（スコープ外操作が必要な場合は実行
       せず承認を求める。10分制限到達時も同様）
    5. 監視・異常検知（未許可アクセス試行等が必要になった場合は実行
       せず報告する。参照した情報源を記録する）

  挿入先は以下の5関数（AZRASが生成する全AI依頼文）:
    - module1: _ai_takeoff_request_text（一次図面解析依頼）
    - module1: _ai_takeoff_recheck_request_text（最終再確認依頼、
      PATCH_023で構造変更済み）
    - module5: _ai_cost_request_text（建設費一次調査依頼）
    - module5: _ai_cost_review_request_text（建設費他AI再調査依頼）
    - module5: _ai_cost_recheck_request_text（建設費ChatGPT再確認
      依頼、PATCH_023で構造変更済み）

効果:
  「AZRAS AI依頼文 標準ルール(v2)」ドキュメントの4項（実運用への適用
  方法）で示した「共通ヘッダーとして依頼文冒頭に追記する」方針を、
  別添付ではなく実際のコード生成物として実装した。以降、AZRASが生成
  する全てのAI依頼文（一次調査・独立レビュー・最終再確認のいずれも）
  に本ヘッダーが自動的に付与される。

再発防止:
  未実装（dev_checksへの回帰テスト追加は次パッチで対応予定 — 5関数
  すべての生成テキストにAZRAS_AI_STANDARD_RULES_V2_ENが含まれることを
  確認する自己チェックを想定）。

注記:
  ドキュメント側の1項（依頼構造の簡略化）はPATCH_023で別方式
  （confirmed_matching_items等によるコード側の実データ圧縮）として
  既に実装済みのため、本パッチのヘッダーには文言として含めていない。
  本ヘッダーはあくまで2〜5項（時間目標・権限・安全性）のみを対象と
  する。
