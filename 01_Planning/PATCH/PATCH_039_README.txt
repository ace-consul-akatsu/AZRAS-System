PATCH_039 — 260920 UTC — v2.2.0
========================================

対象ファイル:
  - services/construction_cost_engine_v9_4.py
  - module5/app.py
  - data/construction_cost_database_v9_4.json
  - dev_checks/patch_039_cost_key_and_location_profile_self_check.py（新規）

要望内容:
  PATCH_038でModule 5の未単価問題は解消したが、そのレビュー時に
  併せて報告した2点の不整合が未対応のまま残っていた。
    (a) AI回答の location.planning_region が案件所在地（イリノイ州）
        ではなく「United States / New York」になる。
    (b) Module 1が数量を出している8項目が、どのcost_item_keyにも
        対応せず永久に「未単価」のままで、AI単価依頼にも入らない。
  この2点を修正する。

────────────────────────────────────────
(b) 原因 — cost_item_key の橋渡し漏れ
────────────────────────────────────────
  実プロジェクト 260919_S-Structure_Sample で extract_quantities() を
  実行すると、出力キーは13件のみだった。_quantity_cost_coverage_audit()
  が返す monetary_gap は9件あり、内訳は2系統に分かれていた。

  系統1：単価キーが存在しない（4件・実際の金額欠落）
    外部窓ガラス area 合計          40.98 m2  → 単価キーなし
    Ceiling glass wool insulation   374.35 m2 → 単価キーなし
    Parapet coping length           71.91 m   → 単価キーなし
    Eaves gutter length             27.102 m  → 単価キーなし

  系統2：親工種に含まれているのに親が特定できない（5件・二重計上の危険）
    AW-1〜AW-5 窓 / ガラス仕様未確定 窓 → 親 glass に金額行が無い
    SS-1 シャッター（pcs）              → 親 shutter に金額行が無い
    ビニル床シート系 213.84 m2          → 親が None
    K-type spandrel cladding 82.81 m2   → 親が None
    Suspended gypsum acoustic ceiling   → 親が None

  判定ロジックを実際に通して確認したところ、_takeoff_cost_key() の
  外装判定は "サイディング" "スパンドレル" 等の日本語トークンか、
  ("外壁" or "exterior wall") + ("面積" or "area") の組み合わせのみで、
  AI数量拾いレビューが生成した英語行名 "K-type GL-color steel
  spandrel cladding area on north facade" は小文字 spandrel を含むが
  日本語トークンに一致せず "外壁" も含まないため、どの分岐にも
  落ちていなかった。内装判定も同様に "tile carpet" "vinyl floor"
  "epoxy floor coating" "j-tone" のみで、"vinyl sheet" "acoustic
  ceiling board" は対象外だった。
  笠木・軒樋は、そもそも base_unit_costs_jpy の32キーのどこにも
  対応する工種が存在しなかった。

(b) 対応:
  1. 単価キーを3件新設した（base_unit_costs_jpy /
     COST_KEY_CANONICAL_UNIT / _method_allowed_keys の3箇所へ同時登録）。
       ceiling_insulation_area  m2  天井断熱（面積基準）
       parapet_coping           m   笠木
       rainwater_gutter         m   雨樋（軒樋・竪樋）
     いずれも pricing_status="unit_price_required"、JPY単価は0のまま
     登録する。既存の louver / oa_floor / ceiling_glass_wool と同じ
     扱いで、「数量はあるが単価は地域・仕様確認後に登録する」状態を
     明示するためであり、0円を単価として計上する経路は作っていない。

  2. _takeoff_cost_key() に4本の橋を追加した。意図的に狭くしてあり、
     「全体を代表する合計行」だけが金額の所有者になる。
       "外部窓ガラス … 合計" / "exterior window glass … total" → glass
       天井グラスウール面積 / ceiling + glass wool          → ceiling_insulation_area
       笠木 / parapet coping                                 → parapet_coping
       軒樋・竪樋 / eaves gutter・downpipe                   → rainwater_gutter
     AW-1個別行や「ガラス仕様未確定 窓 area」（合計行の内数）は
     "合計/total" を含まないため引き続きキーを持たない。これにより
     40.98 m2 と 30.48 m2 が両方 glass に積まれる二重計上は起きない。

  3. _quantity_cost_parent_scope() に、既に金額化されている親工種の
     内数であることを説明する規則を追加した。この関数は数量も単価も
     一切変更せず、所有関係を説明するだけである。
       spandrel / cladding+facade(m2)          → external_finish
       ビニル床シート / vinyl sheet(m2)         → interior_finish
       acoustic ceiling / ceiling board(m2)     → interior_finish
       category が floor/ceiling/wall finish    → interior_finish
       シャッター（m2以外＝本数行）             → doors
       スチールパーティション / PT-             → doors
       竪樋本数                                 → rainwater_gutter
     シャッターを doors に寄せたのは、doorsの採用数量が
     「Module 1各面のドア面積合計」＝シャッター見付を含む面積控え値
     であり、本数行は独立した金額所有者になり得ないためである。

  4. ceiling_glass_wool（m3）と ceiling_insulation_area（m2）は
     同一の物理層を別基準で測ったものなので、extract_quantities() の
     最後で排他制御を入れた。両方揃った場合は厚み明示のm3側を残し、
     m2側は excluded_quantities へ理由付きで退避する。換算は行わない
     （厚みが図示されていない場合に勝手な厚みを発明しないため）。

(b) 実プロジェクト検証:
  260919_S-Structure_Sample.json に対して実コードで検証した。
                         修正前      修正後
    cost_item_key 件数    13         17
    monetary_gap 件数      9          0
    included_in_cost_line  9         13
    included_in_parent    28         40
  新たに金額化対象になった数量:
    glass                    40.98  m2
    ceiling_insulation_area 374.35  m2
    parapet_coping           71.91  m
    rainwater_gutter         27.102 m
  いずれも次回のAI概算単価依頼（[CURRENT PROJECT PRICE SCOPE]）へ
  自動的に含まれる。既存13工種の採用数量は1件も変化していない。

────────────────────────────────────────
(a) 原因 — 代表都市プロファイルの取り違え
────────────────────────────────────────
  construction_cost_engine_v9_4.resolve_location_profile_from_project()
  は、登録済み代表都市に一致しない場合、国別の基準都市へ落とす。
  米国の基準都市は "United States / New York" で、登録済み米国
  プロファイルは New York と Los Angeles の2つしかないため、
  Indian Head Park（イリノイ州60525）は都市一致に失敗しNYが選ばれる。
  ここまでは設計どおりだが、
    ・「都市一致」なのか「国フォールバック」なのかを返しておらず、
    ・Module 5のAI依頼テンプレートが、その代表都市名を
      location.planning_region としてそのままAIに渡していた。
  このためChatGPTは忠実にNYを返し、返ってきたJSONだけを見ると
  案件がニューヨークにあるように読める状態になっていた。

  なお金額への影響範囲も確認した。PATCH_462/475により、外貨案件では
  AI現地単価が material_index / labor_index を通らず
  local_installed_all_in として直接使われるため、NY係数が単価へ
  掛かることはない。また benchmark_usd_per_m2 はコード上どこからも
  参照されていない（非JPY案件の妥当性診断は PATCH_432 により
  benchmark=None となる）。よって実害は
    ・productivity_index 95.0 による想定工期
    ・表示・AI連携上の地域名
  に限られる。今回は存在しない地域単価を捏造せず、
  「どう到達したかを正しく申告する」方向で修正した。

(a) 対応:
  1. resolve_location_profile_from_project() の戻り値に
       match_level（matched_city / country_reference_fallback / unresolved）
       profile_is_project_city
       profile_is_country_fallback
     を追加した。既存キーは変更していないので、呼び出し側の互換性は保たれる。

  2. Module 5のAI依頼JSONテンプレートを次のように変更した。
       "planning_region"                    ← 案件所在地（_authoritative_project_cost_location）
       "representative_cost_profile"        ← AZRAS側の代表都市（従来のregion）
       "representative_cost_profile_basis"  ← matched_project_city 等の到達方法
     依頼本文にも "Planning regional profile basis:" の1行を追加した。
     ヘッダーには従来から「案件住所が地理的価格決定の権威である」旨が
     書かれており、今回JSON側の表記をその宣言に一致させた形になる。

  3. Module 5ヘッダーの案件所在地表示に、国フォールバック時のみ
     警告を併記する（_cost_profile_proxy_notice）。
     「代表プロファイル United States / New York は案件所在地の都市では
       ありません（国の基準都市による自動選択）。地域係数・生産性・工期は
       参考値として扱い、単価はAI概算単価／現地見積で確定してください。」
     日本語/英語の両方を用意した。都市一致時は何も表示しない。

(a) あえて実施しなかったこと:
  "United States / Chicago" プロファイルの新規登録は行わなかった。
  material_index / labor_index / productivity_index / benchmark を
  埋めるだけの一次情報が今回の調査で得られず、NYやLAから比率で
  推定した数値を登録すると、AZRASが単価について守っている
  「根拠のない数値を発明しない」原則に反するためである。
  シカゴ（またはイリノイ）の RSMeans City Cost Index、および
  Turner & Townsend GCMI の USD/m² が入手できた時点で、
  data/regional_cost/US_Chicago_YYYY.json と locations への追加だけで
  登録できる。今回の match_level 実装により、登録後は自動的に
  matched_city へ切り替わり警告も消える。

────────────────────────────────────────
横断監査
────────────────────────────────────────
  - 00 Installer: Contract変更なし。修正不要。
  - 02 Evaluation: Module 5保存結果の読取Contract変更なし。修正不要。
  - 03 Compare: Module 5保存結果の読取Contract変更なし。修正不要。
  - extract_quantities() / resolve_location_profile_from_project() の
    既存戻り値キーは削除・改名していないため、他Moduleへの影響なし。
  - 既存PATCHフォルダーは削除・整理・上書きしていない。
    01 PlanningへPATCH_039のみ追加。

回帰確認:
  - dev_checks/既存16本: 全てPASS
    （azras_scope_leakage_regression のみ本サンドボックスに tkinter が
      無いためImportErrorで停止。修正前のソースでも同一の停止になる
      ことを確認済みで、パッチ起因ではない）
  - PATCH_039追加self-check: PASS（38項目）
  - Python compile: PASS（all_python_sources_compile_self_check 69本）
  - pyflakes: 修正前後で警告が完全一致（差分0行）
