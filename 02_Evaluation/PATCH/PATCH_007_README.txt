PATCH_007 — 260922 UTC — v2.2.0
========================================

対象ファイル:
  - services/repair_demolition_cost_engine_v9_6.py
  - data/repair_demolition_cost_assumptions_v9_6.json（component_cost_sources 追加）
  - dev_checks/patch_007_lifecycle_component_cost_self_check.py（新規）

要望内容:
  同じ建物で工法だけを変えた比較において、Module 7 の更新費が
  「建設費総額 × 固定割合」で計算されていたため、同一の設備・仕上げでも
  構造が高い工法ほど更新費が高く出ていた。明細ベースへ改める。

原因:
    share = db["component_shares"].get(component_key, .02)
    comp  = initial * share        # initial = Module 5 建設費総額
  部位の実際の単価を見ず、総額に固定割合を掛けていた。実データでは
  同じエアコンの1回あたり更新費が 2×6 1.32M に対し RC 2.44M（1.85倍）、
  冷蔵庫まで 0.24M 対 0.44M となり、構造費の差が200年間すべての
  設備・仕上げ更新に掛け算で波及していた。

対応:
  1. 部位ごとの新設費を Module 5 の明細から求める。対応表は
     component_cost_sources として assumptions JSON に置き、編集可能。
       構造          concrete / reinforcing_steel / formwork / dimension_lumber /
                     structural_plywood / clt / structural_steel / phc_pile / 土工事一式
       窓・建具      glass / tempered_glass / doors / shutter / louver
       屋根          roofing / parapet_coping / rainwater_gutter
       外装インフィル external_finish / external_finish_rc / external_finish_timber
       間取りインフィル interior_finish / gypsum_board / ceiling_lgs / oa_floor
       断熱          phenolic_foam / xps / roof_glass_wool / ceiling_glass_wool /
                     ceiling_insulation_area / vapor_barrier
       空調・換気    設備一式「空調」を share 比で分割
       照明・コンセント 設備一式「電気」を share 比で分割
       建物全体      Module 5 建設費総額（工法差が出て当然の部位）
       全インフィル  非構造部位の合計＋どの部位も持たない設備一式（重複計上なし）
     金額の水準は従来どおり総額基準に合わせるため、明細（直接工事費＋設備）
     から総額への比率を掛ける。変えたのは配分であり水準ではない。

  2. 明細が無い部位（冷蔵庫など、Module 5 に対応する行が存在しないもの）は
     従来の「総額×割合」ではなく、工法で変わらない部位から求めた
     基準額に割合を掛ける。
       基準額 ＝ Σ(工法不変部位の明細ベース金額) ÷ Σ(その割合)
       工法不変部位 ＝ 空調・換気・照明・コンセント・窓・間取りインフィル
     屋根・断熱・外装は工法で正当に変わるため基準額には使わない。
     工法不変部位が1つも値付けされていない場合のみ従来方式に戻し、
     その部位を legacy_share_components に列挙する。

  3. 人が値を指定する settings["component_cost_overrides"] と、
     旧方式を再現する settings["component_cost_method"]="legacy_total_share"
     を用意した（監査・退行確認用）。

  4. 結果に component_cost_basis_audit（部位ごとの金額と根拠）、
     method_neutral_fallback_components、legacy_share_components、
     nonstructural_reference_cost を追加。

検証（実Project 3件・実エンジン）:
  単価統一とRCの窓・設備額の補正を反映した状態では、同一部位が一致する。
    部位（1回分）        旧方式 2×6/AZRAS/RC        新方式 2×6/AZRAS/RC
    空調設備             1.63M / 2.14M / 2.96M      2.91M / 2.91M / 2.91M
    窓・ガラス・建具     2.37M / 3.12M / 4.31M      7.78M / 7.78M / 7.78M
    冷蔵庫               0.30M / 0.39M / 0.54M      0.55M / 0.54M / 0.54M
    屋根                 2.08M / 2.73M / 3.77M      1.24M / 1.24M / 1.65M（RCは屋根面積大）
    断熱                 1.19M / 1.56M / 2.16M      3.70M / 4.58M / 7.19M（RCは外断熱）
  200年更新費総額は 2×6 209.6M→278.0M、AZRAS 199.7M→294.6M、
  RC 335.8M→313.8M となった（旧方式は非構造部位を構造費に連動させていた分、
  RCを過大・木造を過小に出していた）。

  併せて Module 5 の計上漏れも見える化された。2×6 と AZRAS は外装仕上げの
  行を持たないため、外装インフィルが method_neutral フォールバックになる。
  これは元Projectの数量・単価を直すべき範囲差であり、03 Compare の
  範囲差リストにも「外装仕上げ（いずれか）」として挙がる。

横断監査:
  - Module 7 の結果へのキー追加のみ。イベント構造・税処理は不変。
  - Module 6 は Module 7 の年次表を読むため、Module 7 → Module 6 の順で
    再計算が必要（03 Compare の整合性確認が検知する）。
  - 01 Planning / 03 Compare のContract変更なし。

回帰確認:
  - dev_checks/既存9本: 全てPASS
  - PATCH_007追加self-check: PASS（34項目）
  - full_self_check.py: 修正前と同一の結果（本サンドボックスに tkinter が
    無いことによる5件のみ。パッチ起因ではない）
  - pyflakes: 修正前後で警告が完全一致（差分0行）
