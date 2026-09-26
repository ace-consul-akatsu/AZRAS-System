PATCH_025 — 260918 UTC — Planning_22
========================================

対象ファイル:
  - core/ai_security_audit.py（新規）
  - module1/app.py
  - module5/app.py
  - dev_checks/ai_request_efficiency_security_audit_self_check.py（新規）
  - README_JA.txt / README_EN.txt

目的:
  Planning_21で導入した依頼文圧縮・AI標準ルールをさらに実装側で強化し、
  (1) AI回答時間の短縮、(2) 「お願い」だけではない技術的安全境界、
  (3) 監視内容の明確化と再発防止を同時に行う。Metaからの指摘
  「ネットワーク/API境界を構造として示す」「何をログに残し、誰が見るかを
  明確にする」も取り込んだ。

1. AI依頼文の追加軽量化
  - Module 1 FINAL再確認を3層化:
      A confirmed/manual + AI一致 -> confirmed_matching_items（最小）
      B estimated + 全収集AI一致 -> estimated_matching_items（根拠ページ等だけ）
      C 不一致/未解決/AI未回答 -> items_requiring_review（従来どおり全文）
  - building_profileは、全AIが実質一致する場合、各AI全文を再送せず
    building_profile_matching_summary 1件へ圧縮。不一致時だけ
    building_profile_requiring_reviewに各AI全文を残す。
  - Module 5 FINAL再確認のincomplete_items/unresolved_itemsも
    keys_needing_reviewの項目だけにフィルタ。

2. 10分ルールの停止動作を修正
  - 10分到達時に「続けますか？」と中断する方式を廃止。
  - 追加探索の価値が低い場合は探索を打ち切り、未確定はunresolvedのまま
    必須JSONを完成させる。精度を落として数値を作ることは禁止。
  - 建設費依頼には evidence sufficiency / SEARCH STOP RULE を追加。

3. 技術的なAZRAS側ネットワーク境界
  - AI回答JSON取込時、参照URLをコード検証。public HTTP/HTTPSのみ許容。
  - localhost、loopback、RFC1918/private、link-local、認証情報埋込URL、
    単一ラベルのイントラネット名、file/ftp/ssh/smb等の非Webスキームを拒否。
  - Module 1数量AI、FINAL JSON、Module 5建設費AIのいずれにも適用。
  - 重要: これはAZRAS取込境界の技術的強制であり、AI事業者内部ネットワークを
    AZRASが物理的に分離していると誤って主張しない。AZRAS Planning自体は
    AI APIを呼ばず、TXT/ZIPをユーザーがAIへ送る方式。

4. 監視・監査ログの具体化
  - 既存4フォルダー構成を増やさず、各ワークフローの
    R1/04_Final determination/AI_Audit/ に保存。
  - AI_AUDIT_LOG.jsonl: 生成依頼/取込・拒否回答、SHA-256、AI名、時刻、
    明示された参照URL、contract/security anomaly、採用段階の概要を記録。
  - AI_WEEKLY_ANOMALY_SUMMARY.json: 直近7日rollingでイベント数・異常種別・
    reviewer・参照URL数を集計。AZRAS operator/designerがレビュー主体。
  - AZRASを閉じている間にバックグラウンド処理をするものではなく、
    依頼生成/AI回答取込時にrolling 7-day summaryを更新する。
  - 非公開Chain-of-Thought（AI内部推論ログ）は取得できないため要求・保存しない。
    calculation_basis / decision / evidence / source URL等、AIが明示して返した
    観測可能な証拠だけを監査対象とする。

5. 再発防止
  - dev_checks/ai_request_efficiency_security_audit_self_check.py を追加。
  - private/local URL拒否、public URL許容、audit log / 7-day summary生成、
    依頼文圧縮マーカー・Module5 incomplete filterの残存を自己チェック。

互換性:
  - AI JSON schema自体は変更しない。
  - R1トップレベル4フォルダー構成は変更しない。
  - 既存の公開Web参照はHTTP/HTTPSであれば継続利用可能。
