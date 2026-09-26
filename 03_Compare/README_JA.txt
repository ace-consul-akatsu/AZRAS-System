AZRAS Compare Version 2.2.0（パッチ番号は VERSION.json の "patch" を参照）
正式製品番号: 03_AZRAS_Compare

【正式データフロー】
01 AZRAS Planning → 02 AZRAS Evaluation → 03 AZRAS Compare

Compareは保存済みProject JSONを読み取り専用で比較します。

【Compareで禁止する処理】
- Evaluation未計算値を0へ置換しない
- Evaluation不足値を推定しない
- AI生回答から数量を再構築しない
- 200年環境結果をCompare側で再計算しない
- 200年事業／現在価値結果をCompare側で再計算しない
- 廃止済み04 Feasibility調整を参照・適用しない

【02 Evaluation状態】
- 200年環境・200年事業とも保存済み：完了
- 片方のみ保存済み：一部未計算
- 両方なし：未計算

【現在のAZRAS v2.2.0正式製品】
00 Installer / 01 Planning / 02 Evaluation / 03 Compare

【現在価値回収グラフ】
Evaluation v2.2.0（旧 Evaluation 1.0.209 以降）で保存された現在価値累積CFを読みます。旧Evaluation JSONでこの保存値が無い場合、Compare側で再計算せず「未計算」とします。

【言語表示修正（旧 Compare 1.1.19、v2.2.0 に継承）】
- 日本語／英語UIの表示経路を分離しました。
- 動的グラフ名、警告、状態表示、表見出し、CSV表示見出しを選択言語に連動させます。
- Project名・所在地・通貨・単位・保存済みProject JSONデータそのものは原文値として保持し、勝手に翻訳・書換えしません。
- CompareにEvaluation所管の再計算処理は追加していません。
