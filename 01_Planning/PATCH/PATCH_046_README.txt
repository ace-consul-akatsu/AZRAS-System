PATCH_046 — 260924 UTC — v2.2.0
========================================

対象ファイル:
  - module5/app.py
  - dev_checks/patch_046_ai_cost_final_filename_self_check.py（新規）
  - VERSION / VERSION.json / CHANGELOG.md / PATCH_README.txt

要望内容:
  Module 5 建設費の⑤「ChatGPT再確認依頼書」と、その最終回答JSONが、
  一次調査JSON・他AIレビューJSONとファイル名だけで明確に区別できるよう、
  最終段階の2ファイル名へ必ず "FINAL" を入れる。

修正:
  1. ⑤で保存する最終再確認依頼TXTを
       YYMMDD_HHMM_AZRAS_AI_APPROX_COST_CHATGPT_FINAL_RECHECK_REQUEST.txt
     に変更。
  2. ⑤の依頼本文 [RETURN] に、ChatGPT最終回答JSONの必須ファイル名を明記:
       YYMMDD_HHMM_AZRAS_AI_APPROX_COST_FINAL_<project_name>_chatgpt.json
     日時は従来どおり実回答完了時のUTC分単位。
  3. 画面ボタン名も
       ⑤ ChatGPT最終再確認依頼書
       ⑥ ChatGPT最終再確認JSON取込 → 終了
     とし、最終段階であることを明示。
  4. 既存の primary_recheck schema / recheck_findings / 価格採用ロジックは変更しない。
     旧JSONの読込互換性も壊さない（ファイル名による硬い拒否は追加しない）。

回帰確認:
  - Python全ソースcompile
  - PATCH_046 self-check
  - 既存 dev_checks 全体
