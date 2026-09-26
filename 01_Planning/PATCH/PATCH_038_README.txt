PATCH_038 — 260920 UTC — v2.2.0
========================================

対象ファイル:
  - module5/app.py
  - services/construction_cost_engine_v9_4.py
  - core/project_coordinator.py
  - dev_checks/module5_ai_cost_overlay_recalc_self_check.py

要望内容:
  AI概算単価の最終再確認JSONまで正常に取り込めているにもかかわらず、
  Module 5の工種・材料別内訳と建設費計算結果が「未単価／0 USD」のまま
  更新されない不具合を修正する。

原因:
  1) AI概算JSON取込は、採用単価を _session_ai_unit_cost_overlay に保存する
     ところまでで終了しており、既に画面に表示されているModule 5計算結果を
     自動で再計算していなかった。このため、AI取込前に計算した「全未単価」
     の古い結果がそのまま表示され続けた。
  2) AI採用単価は完全なsession-onlyデータで、Module 5を保存して再起動した
     場合や、Module 1変更後の自動再計算では入力スナップショットから復元
     されなかった。その結果、再計算時に海外単価が再び未単価へ戻る経路が
     あった。
  3) AI最終再確認後の pricing_status
     ai_post_review_rechecked_provisional / ai_primary_basis_provisional 等が、
     UIの「想定・暫定単価」判定集合に含まれておらず、価格が入った場合に
     「確定・根拠単価」と誤表示される可能性があった。
  4) 地域プロファイルの辞書へ直接session overlayを置く設計のため、同じ地域
     プロファイルを使う別Projectへ価格が漏れる余地があった。

修正:
  - AI概算JSONを取り込んだ直後に Module 5を自動再計算し、工種別金額と
    右側の建設費集計を即時更新する。Projectへの正式保存は従来通りユーザーの
    「保存」操作で行う。
  - Module 5保存時の _input_snapshot に ai_cost_provider_overlay を保存し、
    再起動時に復元する。
  - Module 1更新に伴うModule 5自動再計算でも、保存済みAI overlayを先に
    再装着してから建設費を計算する。
  - AI overlayへproject_id/project_nameのbindingを付け、別Project IDでは
    overlayを使用しない。
  - 最終再確認済みでも provisional なAI価格は黄色の「想定・暫定単価」として
    表示する。

実物Project/R1による検証:
  260919_S-Structure_Sample と R1内4回答を同じ reconciliation ロジックで再現。
  最終ChatGPT再確認後、13工種中10工種の採用単価が有効になり、以下を含む
  金額が計算されることを確認した。
    PHC杭          57,742.08 USD
    構造用鉄骨    262,504.22 USD
    OAフロア       11,253.36 USD
    屋根GW          11,071.97 USD
    鉄筋             8,092.05 USD
    外装            42,079.19 USD
    屋根            74,229.58 USD
    建具            16,887.86 USD
    内装            60,008.26 USD
    型枠            32,626.17 USD
  設備パッケージもHVAC/Electrical/Plumbingの採用価格が計算へ入ることを確認。
  concrete / louver / phenolic_foam は最終AI根拠上まだ完全な採用価格がなく、
  0価格と仮定せず「未単価」のまま保持する（意図した挙動）。

横断監査:
  - 00 Installer: Contract変更なし。修正不要。
  - 02 Evaluation: Module 5保存結果の読取Contract変更なし。修正不要。
  - 03 Compare: Module 5保存結果の読取Contract変更なし。修正不要。
  - 各製品の既存PATCHフォルダーは削除・整理・上書きを行わない。
    01 Planningでは既存PATCHを全て保持したままPATCH_038だけ追加。

回帰確認:
  - dev_checks/既存15本: 全てPASS/SKIP(依存未導入のみ)
  - PATCH_038追加self-check: PASS
  - Python compile: PASS
