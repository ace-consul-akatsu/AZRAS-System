AZRAS Planning Version 2.2.0（パッチ番号は VERSION.json の "patch" を参照）
正式製品番号: 01 AZRAS Planning
正式データフロー: 01 Planning → 02 Evaluation → 03 Compare
Planningは企画段階の正式Project JSONを作成・保存します。
図面解析、AI／人間確認後のcanonical quantity、地域・気候、8760時間結果、概算建設費はPlanningの責任です。
PDF/ZIP解析は選択済みBuilding System / Structure / Methodを勝手に変更しません。
Human Reviewはcurrent-state-only。AIはcanonical providerごとにcurrent snapshot 1件。
Building System変更時はcurrent AI imported stateを削除。AI積算データはProject/R1の4段階フォルダーだけを使用。
不明・未計算を0へ置換しません。
起動: run_AZRAS_Planning_without_build.bat
EXEビルド: build_AZRAS_Planning.bat
旧Planning_Basic識別子は互換aliasに限ります。

AI安全・監査（Planning_22）:
- AZRAS Planning自体はAIサービスへAPI接続しません。依頼TXT/ZIPを生成し、ユーザーがAIへ送るファイル交換方式です。
- AI回答JSONの参照URLは、AZRAS取込時にpublic HTTP/HTTPSだけを許可し、localhost・ループバック・RFC1918/private・link-local・認証情報埋込URL・単一ラベルのイントラネット名・非Webスキームをコードで拒否します。
- これはAZRAS側の技術的境界であり、AI事業者内部のネットワーク分離をAZRASが保証するものではありません。
- 生成依頼と取込/拒否したAI回答について、ハッシュ・AI名・時刻・明示された参照URL・契約/安全異常をProjectローカルのAI_Auditへ記録し、直近7日間の異常サマリーを更新します。
- AIの非公開Chain-of-Thought（内部推論ログ）は要求・保存しません。監査対象は、JSONに明示されたcalculation_basis/decision/evidence、参照URL、ファイルハッシュ等の観測可能な証拠です。
