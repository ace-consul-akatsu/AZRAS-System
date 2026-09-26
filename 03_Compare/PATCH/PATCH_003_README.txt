PATCH_003 — 260920 UTC — v2.2.0
========================================

対象ファイル:
  - main.py
  - comparison/extractor.py
  - dev_checks/patch_003_legend_layout_and_comparison_premise_self_check.py（新規）

要望内容:
  2×6_Sample / AZRAS_Sample / RC_Rahmen_Sample の3件比較で
    (1) 全グラフの凡例で「AZRAS_Sample [AZRAS Platform]」が
        「RC_Rahmen_Sample [Conventional RC]」に重なって読めない
    (2) RCだけが全指標で外れ値になる
  の2点。(2)の原因のうち本製品の責任範囲は「比較前提の不一致を
  利用者に伝えていないこと」である。

────────────────────────────────────────
(1) 凡例の重なり
────────────────────────────────────────
原因:
  LineChart.redraw の凡例描画が固定ピッチだった。

    x0 = L + si*155

  系列ラベルは「プロジェクト名 [工法名]」で利用者データであり、
  幅に上限が無い。155pxを超えるラベルはそのまま次スロットへ
  食い込む。報告された組み合わせを実測すると
    2×6_Sample [2×6]                   幅 121px  → 収まる
    AZRAS_Sample [AZRAS Platform]      幅 199px  → 155pxを44px超過
  となり、si=1 のラベル終端 332px が si=2 の開始 388px…ではなく
  旧式では si=1 開始233px+199px=432px、si=2 開始 388px となって
  44pxぶん重なる。5つのグラフすべてが同じ関数を使っているため、
  同じ位置に同じ重なりが出ていた。

対応:
  凡例レイアウトを実測幅ベースに置き換えた。
    ・_measure()      tkfont.Font(...).measure() でラベル実幅を取得。
                      フォント管理が使えない場合のみ文字種別推定に
                      フォールバックする（全角11px/半角6px、@8pt）。
                      推定側は全角寄りに倒してあるので過小評価しない。
    ・_legend_layout()  左から順に配置し、プロット幅を超えたら次の
                      行へ折り返す。1項目がプロット幅より長い場合は
                      省略記号で切り詰めてキャンバス外へ出さない。
    ・折り返し行数に応じて T（プロット上端）を 14px×(行数-1) 下げる。
                      これを軸の描画より前に行うので、2行目の凡例が
                      最上段グリッド線の上に描かれることはない。

検証（dev_check、表示サーバー不要）:
  ラベル1〜7件 × プロット幅 1200/900/640/420/150px の25通りで
    ・全項目が配置されること
    ・同一行内で重なりが無いこと
    ・行末がプロット幅を超えないこと
    ・返り値の行数と実配置が一致すること
  を検証。報告された3件の組み合わせについては、旧固定ピッチでは
  実際に重なっていたことも同時に検証している（退行検知のため）。

────────────────────────────────────────
(2) 比較前提の不一致を通知
────────────────────────────────────────
原因:
  比較の意味を決める前提が2つあり、どちらもJSONから取り出されて
  いなかったため、利用者に伝える手段が無かった。

  家賃の前提:
    3ProjectともModule 6が rent_setting_method = "gross_yield"、
    target_gross_yield_percent = 8.0 で、家賃を建設費から逆算して
    いた（逆算後 7,096 / 10,599 / 24,651 円/㎡年）。
    利回り固定なら単純投資回収年は建設費に依存しないため、3件とも
    22年で一致するのは計算上の必然であり、建設費が高いProjectほど
    家賃も自動的に高く設定される。これは単一Project検討としては
    正しいが、建物間比較としては成立しない。

  単価根拠の前提:
    2×6 / AZRAS は location_pricing_mode =
    ai_approximate_cost_session_local_currency（施工込み一本値）、
    RC は automatic_city_initial_estimate（材料/労務/機械の分離単価）
    で、単価水準そのものが異なる（XPS 75,600 対 179,880 円/m3 等）。
    建設費差の一部は工法差ではなく価格根拠差である。

対応:
  extractor に前提を出力させた。
    rent_setting_method / rent_derived_from_cost /
    target_gross_yield_percent / resolved_annual_rent_per_m2 /
    price_basis_token / location_pricing_mode
  price_basis_token は 01 Planning PATCH_040 の
  module5.price_basis_fingerprint.basis_token を読む。
  PATCH_040 以前に保存されたJSONには存在しないため、その場合は
  従来から保存されている location_pricing_mode から解決する
  （後方互換。読めない場合は 'unknown'）。

  読込直後に「比較前提の確認」警告を1回出す。
    ・家賃を建設費から逆算しているProjectがある場合、その一覧と
      逆算後の家賃、および「市場家賃を直接入力へ切り替え、全Project
      で同じ家賃を設定する」という具体的な対処を表示。
    ・price_basis_token が揃っていない場合、根拠ごとにProjectを
      グルーピングして表示。
  既存の「02 Evaluation 未計算確認」「税金取扱いの確認」と同じ
  タイミング・同じ扱いで、グラフや集計の値は一切変更・除外しない。
  ダイアログ題名は TEXT_EN に英訳を追加済み。

  実データ検証（3件のProject JSON、実コード）:
    2×6_Sample        gross_yield / ai_approximate_cost_session
    AZRAS_Sample      gross_yield / ai_approximate_cost_session
    RC_Rahmen_Sample  gross_yield / regional_cost_database
  → 家賃前提・単価根拠前提の両方が発火することを確認。

────────────────────────────────────────
横断監査
────────────────────────────────────────
  - 本製品は read_only_consumer であり、Project JSONへの書き込みは
    行っていない。schema_version 3.0 の読取Contractは変更なし。
  - extractor の返り値はキー追加のみ（削除・改名なし）。
  - 01 Planning PATCH_040 / 02 Evaluation PATCH_005 と対で機能するが、
    どちらが未適用でも本パッチ単独で動作する（後方互換の解決経路あり）。
  - 既存PATCHフォルダーは削除・整理・上書きしていない。

回帰確認:
  - dev_checks/既存2本: PASS
  - PATCH_003追加self-check: PASS（139項目）
  - Python compile: PASS
  - pyflakes: 修正前後で警告が完全一致（差分0行）
