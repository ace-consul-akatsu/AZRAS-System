PATCH_009 — 260924 UTC — v2.2.0
========================================

対象ファイル:
  - module6/app.py
  - services/investment_engine_v9_5.py
  - VERSION.json
  - dev_checks/patch_009_market_rent_validation_json_self_check.py（新規）

修正1 — 市場家賃方式の入力エラー:
  市場家賃方式では「表面利回り (%)（市場家賃から算出）」欄は入力値ではなく
  計算結果であり、初回計算前は空欄になる。従来の共通 empty_fields 判定が
  この空欄を必須入力として扱い、target_gross_yield_percent の入力エラーを
  出していた。

  PATCH_009では必須項目を家賃設定方式ごとに判定する。
    ・表面利回り逆算方式: annual_rent_per_m2 は非必須
    ・市場家賃直接入力方式: target_gross_yield_percent は非必須
  したがって市場家賃を入力すれば、そのまま投資評価計算を実行できる。

修正2 — Project JSONの意味を明確化:
  市場家賃方式では target_gross_yield_percent は計算前提ではないため、
  summary上の active target は null とする。一方、モードを表面利回り方式へ
  戻したときに以前の入力値を復元できるよう、利用者の入力値は別キーで保存する。

  市場家賃方式の保存例:
    summary.rent_setting_method = "market_rent"
    summary.target_gross_yield_percent = null
    summary.stored_target_gross_yield_percent = 8.0
    summary.target_gross_yield_active = false
    summary.implied_gross_yield_percent = <市場家賃から算出した値>
    summary.gross_yield_value_source = "market_rent_derived"

  表面利回り逆算方式の保存例:
    summary.rent_setting_method = "gross_yield"
    summary.target_gross_yield_percent = 8.0
    summary.stored_target_gross_yield_percent = 8.0
    summary.target_gross_yield_active = true
    summary.implied_gross_yield_percent = 8.0
    summary.gross_yield_value_source = "target_input"

後方互換性:
  result.settings.target_gross_yield_percent は従来どおり利用者の保存値を保持する。
  新たに settings.target_gross_yield_active を追加し、その値が実計算に使われたかを
  明示する。既存キーの削除・改名はしない。project_schema_v2_0.json は
  module_outputs を自由objectとして保持する既存契約のため、schema変更は不要。
  01 Planningの変更も不要。

影響範囲:
  - 02 Evaluation / Module 6のみ実変更。
  - 01 Planning: 変更なし。
  - 03 Compare: implied_gross_yield_percent等の新しい単独事業指標を読まないため変更なし。
  - Project JSON全体schema versionの変更なし。
