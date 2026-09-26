PATCH_040 — 260920 UTC — v2.2.0
========================================

対象ファイル:
  - services/environment_engine_v9_1.py
  - services/construction_cost_engine_v9_4.py
  - dev_checks/patch_040_envelope_residual_and_price_basis_self_check.py（新規）

要望内容:
  AZRAS Compare で 2×6_Sample / AZRAS_Sample / RC_Rahmen_Sample を
  比較したところ、RCだけが全指標で外れ値になるとの報告。
    ・年間エネルギー 23,206.9 kWh（他2件は 15,869.3 / 15,536.5）
    ・200年累積CO2 1,545.2 t（他2件は 1,033.2 / 1,016.0）
    ・現在価値累積CF −122,787,838 円（他2件は −43,687,856 / −41,166,931）
  調査の結果、原因は1つではなく3系統に分かれた。うち本パッチで
  修正するのは (2-a) と (2-b) のコード側である。

────────────────────────────────────────
(2-a) 幻の無断熱外壁 — 実バグ
────────────────────────────────────────
原因:
  PATCH_402 は、Module 1 が light_wall の数量を返さない場合に、
  外皮不透明面積からRC外壁を差し引いた残りを軽量壁の「面積」として
  復元する（light_area_source = surface_opaque_area_fallback）。
  これは代替断熱シナリオが面積0で無効化されるのを防ぐための処置で
  あり、それ自体は正しい。
  ところがU値は assemblies["light_wall"] から取る。軽量壁が実在
  しない建物では、そこは thickness_mm = 0.0 のまま保存されており、
  u() の解決順で「明示U値 5.88235 W/m2K（無断熱）」が返る。
  結果として「合成した面積 × 無断熱U値」という、どの図面にも
  裏付けのない部位が生成される。

  RC_Rahmen_Sample 実測（修正前）:
    light_wall_area_m2_used  = 82.879   (surface_opaque_area_fallback)
    light_wall_u_W_m2K_used  = 5.882
    → 単独の熱貫流 82.879 × 5.882 = 487.5 W/K
    → 建物全体UA 622.7 W/K のうち 78%
  同じ建物の Module 1 building_performance は
  indicative_ua = 0.171 W/m2K、light_wall 面積 0.0 と報告しており、
  Module 2 だけが存在しない壁を作って無断熱扱いしていた。

  なお、まったく同じ欠陥に対する補正は rc_wall 側には既に存在する
  （「external_insulation の指定があるのに thickness が 0 に上書き
  された legacy JSON を 150mm で補正」）。今回は light_wall 側に
  同じガードが無い、片側だけの実装漏れである。
  2×6_Sample は逆に rc_wall_u = 5.882 だが rc_wall_area = 0.0 の
  ため無害で、この非対称性が発見を遅らせていた。

対応:
  light_u / roof_u / rc_u が確定した直後に light_wall 残余補正を
  追加した。発火条件は以下の全てを満たす場合に限る。
    ・light_area > 0
    ・light_u > 1.0（無断熱相当）
    ・light_area_source == "surface_opaque_area_fallback"（合成面積）
    ・light_wall の envelope_thermal_scenario が無効
  このとき面積はそのまま残し（実在する外皮であるため）、U値のみ、
  その建物が実際に解決できている不透明部位の断熱仕様（rc_wall →
  なければ roof）を採用する。採用元が1つも無い場合はU値を発明せず、
  条件を breakdown に記録して据え置く。
  Module 1 が light_wall 面積を明示している場合は「実データ」なので
  一切上書きしない。

検証（実Project 3件、実コード）:
                       修正前UA    修正後UA
    2×6_Sample          128.9       128.9  （補正不発火）
    AZRAS_Sample        129.8       129.8  （補正不発火）
    RC_Rahmen_Sample    622.7       146.0  （補正発火）
  RCのlight_wall U は 5.882 → 0.130（自身のRC外壁仕様）となり、
  当該部位の熱貫流は 487.5 → 10.8 W/K。
  修正後は屋根面積が大きい分だけRCが他2件をやや上回るという、
  物理的に妥当な並びになる。
  breakdown に light_wall_residual_correction を追加したので、
  補正の有無・採用元・補正前後の熱貫流が常に監査できる。

再計算について:
  Module 2 の 8760 時間計算は EPW を必要とするため、本パッチには
  再計算済みProject JSONを同梱していない。RC_Rahmen_Sample を
  Module 2 で再計算・保存すると、暖房負荷 29,396 kWh は概ね
  4,000〜6,000 kWh 程度へ下がり、年間電力 23,207 kWh は 17,000 kWh
  前後、運用CO2 9.98 t/年 は 7 t/年 前後になる見込みである
  （UA比と内部・日射取得の非線形性からの推定であり、確定値は
  再計算結果による）。

────────────────────────────────────────
(2-b) 価格根拠の混在 — 監査情報の欠落
────────────────────────────────────────
原因:
  同じ建物でも、Projectごとに単価の出所が違っていた。
    2×6_Sample   location_pricing_mode = ai_approximate_cost_session_local_currency
    AZRAS_Sample 同上
    RC_Rahmen_Sample          = automatic_city_initial_estimate
  前者はAI概算単価ワークフローが確定した「施工込み一本値」、後者は
  内蔵の日本都市初期値で「材料/労務/機械に分離」された単価である。
  このため 2×6/AZRAS は direct_labor_cost = 0 と表示されるが、これは
  労務費の欠落ではなく、PATCH_466 の規定どおり一本値を分解せずに
  material 側へ入れているだけである。
  単価水準も出所によって実際に異なる（XPS 75,600 対 179,880 JPY/m3、
  フェノールフォーム 100,929 対 165,679 JPY/m3）。
  しかし保存結果には「どちらの根拠で値付けされたか」を1フィールドで
  示すものが無く、複数Project比較が価格根拠差を工法差として読んで
  しまう状態だった。

対応:
  Module 5 の保存結果に price_basis_fingerprint を追加した。
  監査専用であり、単価・数量・金額は一切変更しない。
    basis_token : ai_approximate_cost_session |
                  regional_cost_database |
                  mixed_ai_and_regional_database | no_priced_lines
    location_pricing_mode / priced_line_count / ai_priced_line_count
    unit_price_source_counts / pricing_status_counts /
    pricing_structure_counts / component_split_available
    comparison_note_ja / comparison_note_en
  比較側は basis_token でグルーピングすれば、根拠が揃っていない
  Project同士の比較を拒否するか、少なくとも注記できる。

  実データ適用の手当てについては、別途
  「AI概算単価 JSON（RC_Rahmen_Sample 用）」を同梱の成果物として
  提供する。これを Module 5 の建設費 Cost Provider から取り込めば、
  3Projectとも basis_token = ai_approximate_cost_session に揃う。
  なお、RCの建設費が木造・AZRASより高いこと自体は数量差
  （コンクリート129.4 m3、型枠943.1 m2）に由来する実体差であり、
  価格根拠を揃えてもこの差は残る。揃えることで消えるのは
  「出所が違うことによる見かけの差」だけである。

────────────────────────────────────────
本パッチに含めなかったもの
────────────────────────────────────────
(1) Compare の凡例重なり:
    5つのグラフ全てで同位置に発生しており、系列凡例が固定ピッチの
    x座標で配置され、長いラベル "AZRAS_Sample [AZRAS Platform]" が
    次スロットへ食い込んでいる。共通の凡例描画関数の問題だが、
    当該コードは 03 Compare 側にあり、本製品（01 Planning）には
    存在しない。01 Planning の ui/graph.py には凡例描画が無いことを
    確認済み。03 Compare を受領すれば、tkFont.Font.measure() による
    実測幅レイアウト（不足時は2段折り返し）へ差し替える。

(2) 投資回収・現在価値の前提:
    3Projectとも target_gross_yield_percent = 8.0 で、家賃が建設費
    から逆算されている（resolved_annual_rent_per_m2 = 7,096 /
    10,599 / 24,651）。利回り固定なら単純回収年は建設費に依存しない
    ため、3件とも22年で一致するのは計算上の必然であり、RCの
    現在価値累積CFが約3倍悪いのも絶対額がスケールした結果である。
    これはバグではなく前提の帰結だが、比較としては
    「RCだから市場が3.5倍の家賃を払う」という成立しない仮定を含む。
    該当ロジック（resolved_annual_rent_per_m2 /
    target_gross_yield_percent）は 02 Evaluation 側の Module 6 に
    あり、本製品の services/investment_engine_v9_5.py には存在しない
    ことを確認済み。02 Evaluation を受領すれば、
      ・revenue_basis（yield_derived / explicit_market_rent）の明示
      ・利回り逆算時の比較警告
    を追加する。
    暫定対応としては、Module 6 で利回り逆算をやめ、3件共通の実勢
    家賃を固定して再計算すればコード修正なしで正しい比較になる。

────────────────────────────────────────
横断監査
────────────────────────────────────────
  - 00 Installer: Contract変更なし。修正不要。
  - 02 Evaluation: Module 5保存結果へキー追加のみ（削除・改名なし）。
    読取Contract変更なし。修正不要。
  - 03 Compare: 同上。price_basis_fingerprint は任意参照。
  - 既存PATCHフォルダーは削除・整理・上書きしていない。
    01 Planning へ PATCH_040 のみ追加。

回帰確認:
  - dev_checks/既存17本: 全てPASS
    （azras_scope_leakage_regression のみ本サンドボックスに tkinter が
      無いためImportErrorで停止。修正前のソースでも同一の停止になる
      ことを確認済みで、パッチ起因ではない）
  - PATCH_040追加self-check: PASS（24項目）
      1. 合成残余への無断熱U値適用が解消されること
      2. Module 1が明示した軽量壁数量は上書きされないこと
      3. ユーザーの断熱シナリオは上書きされないこと
      4. 採用元が無い場合にU値を発明しないこと
      5. 木造（実在する断熱軽量壁）が影響を受けないこと
      6. price_basis_fingerprint が4状態を正しく判定すること
  - Python compile: PASS（all_python_sources_compile_self_check 70本）
  - pyflakes: 修正前後で警告が完全一致（差分0行）
