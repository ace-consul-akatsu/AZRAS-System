PATCH_041 — 260921 UTC — v2.2.0
========================================

対象ファイル:
  - services/construction_cost_engine_v9_4.py
  - module1/app.py
  - dev_checks/patch_041_equipment_calibration_and_opening_ownership_self_check.py（新規）

要望内容:
  260918_2_6_Sample / AZRAS_Sample / RC_Rahmen_Sample の保存値検証で
  判明した、01 Planning 側の2件の不具合を修正する。

────────────────────────────────────────
(1) 円建てAI設備額に市場補正が二重に掛かる
────────────────────────────────────────
原因:
  _market_calibration_factor_2026 は、共通DBの設備既定値
  （default_cost_jpy）を2026年愛知の市場水準へ引き上げるための係数
  である。単価行では PATCH 072 により「検証済み現地単価は補正を
  バイパス」しており、外貨の設備パッケージも PATCH 463 で
  「現在市場価格なので補正しない」としていた。
  ところが円建ての設備パッケージだけは、価格の出所を見ずに
  無条件で補正していた。AI概算単価（既に2026年市場価格）や、
  利用者が既定値を書き換えた価格まで 0.612（木造・AZRAS）／
  0.845（RC）倍されていた。

  実データでの影響（AI設備額は同一）:
                AI設備額      保存値      係数    過小計上
    2×6        10,127,105   6,194,169   0.612   −3.93M
    AZRAS      10,324,515   6,314,918   0.612   −4.01M
    RC         10,324,516   8,727,318   0.845   −1.60M
  AZRAS と RC は同一の設備額を入れているのに、係数が工法で変わる
  ため RC が 2.41M 高く表示され、工法差として比較に出ていた。

対応:
  _equipment_price_is_current_market() を新設し、補正の前に判定する。
    ・ai_approximate_cost_session_local_currency → 現在市場価格（補正しない）
    ・database_default_jpy                       → 既定値（従来どおり補正）
    ・ui_local_currency で値が DB既定値と一致   → 未編集の既定値（従来どおり補正）
    ・ui_local_currency で値が DB既定値と異なる → 利用者・AI入力の現在価格（補正しない）
  Module 5 の UI は円建て案件で DB既定値を事前入力して
  ui_local_currency を付けるため、「値が既定値のままか」だけが
  確実な判別手段である。未編集の既定値の挙動は一切変わらない。
  補正しなかった行には market_calibration_source_2026 =
  current_market_package_price_no_recalibration を記録する。

検証（実Project 3件、実エンジンで Module 5 を再計算）:
                 修正前          修正後
    2×6 設備   6,194,169  →  10,127,098
    AZRAS 設備 6,314,918  →  10,324,515
    RC 設備    8,727,318  →  10,324,515   ← AZRAS と完全一致
  直接工事費（単価行）は3件とも1円も変化しない。

────────────────────────────────────────
(2) 同一開口の重複行が両方 audit_only になり、窓・ドアが消える
────────────────────────────────────────
原因:
  _annotate_quantity_aggregation_ownership の PATCH_533 は、窓・ドア
  それぞれで所有者行を1つ選び、それ以外の行を audit_only に落とす。
  この「落とした印」（aggregation_role / downstream_quantity_eligible /
  downstream_use / quantity_adoption_class / superseded_physical_quantity）
  は保存され、以後二度と解除されなかった。一方で所有者は保存の
  たびに選び直される。
  ChatGPT最終図面再確認によって2行の優先度が同点になると、所有者が
  以前に落とされた側の行へ移ることがある。新しい所有者は古い
  audit_only の印を持ったまま、旧所有者は今回新たに落とされるため、
  両方 audit_only となり、その開口は金額の持ち主を失う。

  260918_RC_Rahmen_Sample で実際に発生:
    'Exterior window glazing'  audit_only（superseded）
    '外壁窓ガラス'              audit_only（superseded）
    'Exterior doors'           audit_only（superseded）
    '外部ドア'                  audit_only（superseded）
  → 窓 55.74 m2 が Module 5 から完全に欠落（約4.27M円）。
    ドア 6.33 m2 は Module 5 の工法プロファイル既定値で辛うじて残存。

  さらに、所有者が1件も選ばれない場合でも旧判定
  「_owners.get(k) is not r」は全行で真となり、全行を落としていた。

対応:
  ・選定の直前に、この仕組み自身が付けた印（supersession_reason が
    superseded_by_current_pdf_windows_owner / doors_owner）だけを解除し、
    記録してあれば落とす前の状態へ、記録が無い旧保存では書き込んだ
    4項目だけを元に戻す。他の理由による audit_only には触れない。
  ・落とす時に元の状態を _pre_opening_supersession_state へ記録する。
  ・所有者が実在する場合にのみ他行を落とす（_k in _owners）。
  ・独自の理由で audit_only の行（集計監査など）は所有者候補にしない。
  ・同点時は「前回落とされていない行」を優先し、保存のたびに所有者が
    入れ替わらないようにした。
  ・落とす時は quantity_adoption_class も同時に audit_only にし、
    Module 5 のコストゲートが読む全項目を1パス内で一致させる。

検証（実Project 3件、Module 1 の所有者判定を2パス実行）:
                 修正前                         修正後
    RC           窓・ドアとも所有者なし         窓・ドアとも所有者1件、2パスで不変
    AZRAS        外壁窓ガラス／外部ドアが所有   同左（変化なし）
    2×6          外壁窓ガラス／外部ドアが所有   同左（変化なし）
  RC を実エンジンで Module 5 再計算すると glass 55.74 m2 が1回だけ
  計上される（0でも2倍の111.48でもない）。

────────────────────────────────────────
RC の窓単価について
────────────────────────────────────────
  RC はこれまで窓の数量を持たなかったため、AI概算単価セッションにも
  glass が含まれていない。修正後に再計算すると glass は内蔵の地域
  単価で計上され、price_basis_fingerprint（PATCH_040）は
  mixed_ai_and_regional_database（AI 9行／全10行）と正しく報告する。
  AI基準に揃えるため、glass を加えた RC 用 AI概算単価JSONを別途提供
  する（260921_0455_...RC_Rahmen_Sample_claude.json。旧1011版の上位互換）。

横断監査:
  - 00 Installer: 変更なし。
  - 02 Evaluation: Module 5 保存結果のキー追加・値の変化のみで読取Contract
    変更なし。設備額が変わるため Module 6/7 は再計算が必要。
  - 03 Compare: 読取Contract変更なし。
  - 既存PATCHフォルダーは削除・整理・上書きしていない。

回帰確認:
  - dev_checks/既存18本: 全てPASS
    （azras_scope_leakage_regression のみ本サンドボックスに tkinter が
      無いためImportErrorで停止。修正前のソースでも同一の停止になる
      ことを確認済みで、パッチ起因ではない）
  - PATCH_041追加self-check: PASS（18項目）。修正前のコードでは失敗する
    ことを確認済み。
  - Python compile: PASS
  - pyflakes: 修正前後で警告が完全一致（差分0行）
