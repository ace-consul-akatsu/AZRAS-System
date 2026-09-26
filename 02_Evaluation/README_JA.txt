AZRAS Evaluation Version 2.2.0（パッチ番号は VERSION.json の "patch" を参照）

【現在の製品責任】
Planningが正式なProject JSONを作成・保存します。
EvaluationはPlanningで保存された正式結果を読み、承認済みの長期評価を計算・保存します。
CompareはEvaluationで保存済みの結果だけを読みます。

正式データフロー：
01 AZRAS Planning → 02 AZRAS Evaluation → 03 AZRAS Compare

【Evaluationの責任境界】
- 図面解析、AI／人間確認後の数量確定、canonical quantity_takeoff、
  8760時間結果、建設費はPlanningの責任です。
- Evaluationはraw AI payloadから不足数量を再構築しません。
- 廃止済み04 Feasibilityの追加CO₂・追加費・追加工期を現在計算へ加算しません。
- 旧monolithic Module 8および将来拡張Disaster／Module 9は
  現在のEvaluation依存関係に含めません。
- Planningの正式結果が不足している場合は0・推定値で補完せず、
  Planning側で修正・保存します。

【Evaluation画面】
- 修繕・更新・解体シナリオ
- 200年環境
- 改修・更新・解体費
- 200年事業

金額は企画・比較用の概算値であり、契約金額・正式見積金額ではありません。
