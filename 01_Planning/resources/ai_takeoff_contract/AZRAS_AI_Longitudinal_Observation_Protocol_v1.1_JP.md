# AZRAS AI定点観測プロトコル v1.1

このファイルは、AZRASの通常AI積算依頼と同じ図面・同じ依頼文を、複数AI・異なる時期に同条件で再送し、
AIの図面読解・数量化能力の変化を観測するための補助プロトコルです。

## AIへの必須条件
- この依頼で受け取った図面と依頼文だけを根拠に独立回答すること。
- 過去回の回答、他AIの回答、AZRAS側の縦断比較結果を推測・参照しないこと。
- 図面に明記された事実 > 複数図面の相互参照 > 図面からの計算 > 推定、の順で根拠を示すこと。
- 判断不能なら null / unresolved とし、無理に数値を作らないこと。
- analysis.ai_reviewer には実際のAI名を記録すること。
- 可能なら analysis.evolution_observation.ai_model_version に正確なモデル名/バージョンを記録すること。不明なら null。
- 可能なら analysis.evolution_observation.response_timestamp に回答時刻をISO8601で記録すること。不明なら null。
- 通常のAZRAS_AI_TAKEOFF JSONを1ファイルだけ返すこと。別の比較JSONは作らないこと。

## AZRAS側でのみ記録する情報
previous_record_id / changed_from_previous / change_summary / cross_ai_variance_note /
human_review / final_adopted_value はAIへ判断させません。
これらはAI回答を収集した後、AZRASが履歴として別管理します。

## 再現性
同じ観測条件を再現するときは、依頼ZIPを変更せず再送し、PDF/ZIP図面一式は別添してください。
AZRASは依頼本文と各図面ファイルのSHA-256をManifestへ保存するため、後日も同一図面だったことを検証できます。

## R1フォルダーの送付ルール
AZRASの現在の正式保存領域はProject直下の `R1` だけです。
最初の各AIへの送付物は `R1/01_Request for Estimate` にまとめます。
各AIの独立回答JSONは `R1/02_AI response` に保存します。
再確認依頼は `R1/03_Request for Recheck`、正式採用する最終JSONは `R1/04_Final determination` に保存します。
他AIの回答を最初の独立回答時に送らないでください。独立比較条件が崩れます。
R2は将来用であり、この段階では作成しません。

## 回答形式のハードゲート
AIは図面要約、説明文、確認質問、次の作業提案を返してはいけません。
回答は `AZRAS_AI_TAKEOFF` JSONファイル1件だけとします。
不明点が残っても質問で止まらず、`quantity:null`、`evidence_status:"unresolved"`、`missing_inputs`、`checked_sources` をJSON内に記録して返します。
送付ZIP内の `AZRAS_AI_TAKEOFF_RESPONSE_TEMPLATE_v1.0.json` を回答形の雛形として使用します。


## PATCH 573 identity / filename rule
- `analysis.ai_reviewer` must identify the actual responding AI, determined from its own service/runtime identity.
- Root `required_filename` is mandatory and must use the same actual AI token and UTC completion minute.
- Canonical Meta AI token is `meta`; do not copy `chatgpt`, `claude`, or another provider token from examples.
- If the service/browser cannot control the downloaded filename, the generic transport filename is allowed only when `required_filename` is valid and internally consistent.
