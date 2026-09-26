PATCH_023 — 260918 UTC — v1.0.628
========================================

対象ファイル:
  - module1/app.py（_ai_takeoff_recheck_request_text, 新規 _final_recheck_qty_close /
    _final_recheck_split_by_agreement）
  - module5/app.py（_ai_cost_recheck_context, 新規 _ai_cost_recheck_needs_full_evidence）

経緯:
  マルコ氏より「AIへの依頼文が以前より長く・重くなり、回答時間が延びた」
  という指摘があり、原因分析の結果、最終再確認依頼（図面解析）・建設費
  再確認依頼のいずれも、全AIが既に一致・確認済みの項目まで毎回全文の
  evidenceを再送していることが主要因と判明した。改善案として「一致済み
  項目は要約リストのみ、差異がある項目だけ詳細evidenceを添付する」方式
  が提示され、実装を依頼された。

対応 (1) 図面解析・最終再確認依頼 (module1/app.py):
  _ai_takeoff_recheck_request_text() が送信していた
  independent_ai_responses（全AIのtakeoff_items全文）を廃止し、
  以下の構造に置き換えた。
    - confirmed_matching_items: Planning側で既にconfirmed/manual確定済み
      で、かつ収集した全AIの回答（報告がある場合）が数量・単位ともに
      一致し、unresolved/conflictingでもない項目。local_id・category・
      item・quantity・unitのみの要約行。
    - items_requiring_review: 上記に該当しない項目（Planning側が未確定、
      またはいずれかのAIが異なる数量/unresolved/conflictingを報告）。
      Planningの基準行に加え、各AIのreviewed_ai_values（quantity/unit/
      evidence_status/calculation_basis/source等）を全文添付。
    - new_items_proposed_by_ai: どのlocal_idにも一致しないAI提案項目
      （reviewer別）。
    - building_profile_by_reviewer: 真北・外壁面情報は従来通りAI別に
      全文添付（別途の一致判定は本パッチでは未実装）。
  数量の一致判定は相対誤差0.1%以内（_final_recheck_qty_close）。
  依頼文の[MANDATORY FINAL RULES]に項目12・13を追加し、
  「confirmed_matching_itemsは時短のための要約であり確定結果ではない。
  再確認中に矛盾する図面根拠を発見した場合はconfirmed_matching_items
  であっても再判定して報告すること」を明記した。

対応 (2) 建設費再確認依頼 (module5/app.py):
  _ai_cost_recheck_context() を変更し、reviewer（他AI）のreview_findings
  がsupports_primary_basis以外（challenges_primary_basis /
  fills_primary_gap / clarifies_primary_ambiguity / still_unresolved /
  未記録）のcost_item_key/package_keyのみをkeys_needing_reviewとして
  抽出。
    - confirmed_supported_items: 全reviewerがsupports_primary_basisと
      判定した項目の一行要約（cost_item_key/unit/price/どのreviewerが
      支持したか）のみ。
    - researched_items_needing_review / independent_reviews:
      keys_needing_reviewに該当する項目のみ、従来通りevidence全文を
      添付。該当項目がゼロになったreviewerはパケットから除外。
  依頼文に項目11・12を追加し、confirmed_supported_itemsも再確認中に
  問題が見つかれば再判定対象であることを明記。

効果:
  全項目が一致している場合、依頼文の大部分を占めていた「各AIのevidence
  全文」の再送が、差異のある項目・未解決項目のみに縮小される。精度・
  監査要件（多数決禁止、根拠不明の場合はunresolved維持等）は変更して
  いない。

再発防止:
  未実装（dev_checksへの回帰テスト追加は次パッチで対応予定）。

注記:
  building_profile（真北・外壁面）の一致判定圧縮は本パッチでは対象外。
  対象化する場合は別途PATCHで対応する。
