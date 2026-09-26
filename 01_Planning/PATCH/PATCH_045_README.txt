PATCH_045 — 260923 UTC — v2.2.0
========================================

対象ファイル:
  - module5/app.py
  - dev_checks/patch_045_ai_cost_reviewer_import_self_check.py（新規）

不具合:
  Module 5 建設費の AI 概算単価フローで、③「他AI再調査依頼書」後の④「各AI JSONを順次取込」において、
  1) Meta AI の AZRAS_AI_APPROX_COST reviewer JSON が currency フィールドを省略すると、Project が JPY であっても
     「AI cost currency mismatch: expected JPY, got (missing)」で拒否される。
  2) 数量積算用 AZRAS_AI_TAKEOFF_FINAL_REVIEW JSON を誤って選択した場合、一般的な Unsupported schema 表示だけで、
     建設費用JSONとの取り違えが分かりにくい。
  3) ③の他AI再調査依頼書が「同じ構造」とだけ指示しており、他AIが location.currency、research_execution、
     equipment_packages 等の必須欄を省略する余地があった。

修正:
  1. reviewer JSON に限り、canonical currency 宣言が欠けていても、JSON自身の machine-readable evidence
     （例: source_unit="JPY/m2"、price_JPY 等）が Project currency と一意に一致する場合だけ受理する。
     国名・住所だけから通貨を推測しない。複数通貨が検出された場合は従来どおり拒否する。
  2. ChatGPT primary_guide / primary_recheck は従来どおり currency の明示を必須とし、契約を緩めない。
  3. reviewer の evolution_observation.response_timestamp も completed_at の互換候補として利用する。
  4. reviewer location.authoritative_location を Project住所照合の互換候補へ追加する。
  5. AZRAS_AI_TAKEOFF / AZRAS_AI_TAKEOFF_FINAL_REVIEW を Module 5 へ選択した場合は、
     「数量積算用JSONであり建設費JSONではない」と明示し、③の依頼から返された AZRAS_AI_APPROX_COST を④で選ぶよう案内する。
     数量JSONを建設費として無理に受理することはしない。
  6. ③「他AI再調査依頼書」の出力契約を強化し、schema、research_role、location.project_address、location.currency、
     research_execution、unit_costs、equipment_packages、review_findings、ファイル名を明示した。

実ファイル確認:
  - 260923_0901_AZRAS_AI_APPROX_COST_..._chatgpt.json: 従来どおり読込 PASS
  - 260923_0922_AZRAS_AI_APPROX_COST_REVIEW_..._meta.json: PATCH_045後 読込 PASS
    currency_validation=reviewer_payload_inference(JPY)、10/10 cost items parsed
  - 260923_0913_AZRAS_AI_TAKEOFF_FINAL_..._claude.json: 建設費JSONではないため意図的に拒否。
    ただしエラーを用途取り違えが分かる表示へ変更。

重要:
  Claudeファイルは修正対象の「読込互換性」ではなく、ファイル自体が数量積算FINAL_REVIEWであり建設費調査結果を含まない。
  そのため④で使用してはいけない。③「他AI再調査依頼書」をClaudeへ送り直し、
  AZRAS_AI_APPROX_COST schema_version 1.4 の reviewer JSONを取得する必要がある。

回帰確認:
  - Python全ソースcompile
  - PATCH_045 self-check
  - 既存 dev_checks 全体
