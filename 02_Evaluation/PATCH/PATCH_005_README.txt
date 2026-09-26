PATCH_005 — 260920 UTC — v2.2.0
========================================

対象ファイル:
  - services/investment_engine_v9_5.py
  - dev_checks/patch_005_revenue_basis_disclosure_self_check.py（新規）

要望内容:
  複数Projectを 03 Compare で比較した際、3件とも単純投資回収が
  22年で一致し、現在価値累積CFだけがRCで約3倍悪化していた。
  調査の結果これはバグではなく、家賃設定の前提がそのまま出た
  ものだが、その前提が保存結果から読み取れないことが問題だった。

原因:
  Module 6 の家賃設定には2方式ある。
    rent_setting_method = "market_rent"  市場家賃を直接指定
    rent_setting_method = "gross_yield"  建設費×目標表面利回りで逆算（既定）
  gross_yield では
    base_gross_rent = initial_total × target_gross_yield_percent/100
  となるため、
    ・単純投資回収年が建設費に依存しなくなる
      （同じ利回りを設定した全Projectが同じ年に回収する）
    ・建設費の高い建物ほど自動的に高い家賃を与えられる
  という性質を持つ。単一Projectの検討としては妥当だが、
  建物間比較には使えない。
  この性質は settings に rent_setting_method / rent_setting_basis
  として保存されてはいたが、「比較可能かどうか」という判断に
  直結する情報として明示されておらず、下流製品が推測するしかなかった。

対応:
  Module 6 の結果に revenue_basis_disclosure を追加した。
  監査専用であり、キャッシュフロー・家賃・回収年は一切変更しない。
    rent_setting_method
    rent_setting_basis
    rent_derived_from_construction_cost   gross_yield のとき True
    target_gross_yield_percent            gross_yield のときのみ値を返す
    resolved_annual_rent_per_m2
    comparable_across_projects            market_rent のときのみ True
    comparison_note_ja / comparison_note_en
  注記には、gross_yield の場合は「市場家賃を直接入力へ切り替え、
  全Projectで同じ家賃を設定すること」という対処まで含めている。

  03 Compare 側（PATCH_003）はこのブロックを読み、前提が揃って
  いないProjectを比較しようとした時点で警告を出す。
  なお Compare 側は revenue_basis_disclosure が無い旧JSONでも
  settings.rent_setting_method から解決できるようにしてあるため、
  本パッチが未適用でも比較警告は機能する。

利用者側の対処:
  Module 6 で「市場家賃を直接入力」に切り替え、比較対象の全Project
  に同じ家賃を設定して再計算・保存すれば、
  「RCは建設費が高く家賃は同じ＝回収が明確に遅い」という
  正しい比較結果になる。コード側の追加設定は不要。

横断監査:
  - Module 6 保存結果へのキー追加のみ（削除・改名なし）。
    schema_version 3.0 の読取Contractは変更なし。
  - 00 Installer / 01 Planning への影響なし。
  - 03 Compare は本ブロックを任意参照（未存在でも動作）。
  - 既存PATCHフォルダーは削除・整理・上書きしていない。

回帰確認:
  - dev_checks/既存7本: 全てPASS
  - PATCH_005追加self-check: PASS（19項目）
  - Python compile: PASS
  - pyflakes: 修正前後で警告が完全一致（差分0行）
