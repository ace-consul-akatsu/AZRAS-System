AZRAS Installer Version 5.0.4（パッチ番号は VERSION.json の "patch" を参照）

【現在の正式製品構成 — AZRAS v2.2.0】
00 AZRAS Installer
01 AZRAS Planning
02 AZRAS Evaluation
03 AZRAS Compare

正式データフロー：
01 Planning → 02 Evaluationで計算・保存 → 03 Compareは保存結果だけを比較

今回の検証済み組合せ：
- 01 AZRAS Planning v2.2.0
- 02 AZRAS Evaluation v2.2.0
- 03 AZRAS Compare v2.2.0

【ランチャー】
標準デスクトップ運用はAZRAS代表アイコン1個です。
LauncherにはPlanning / Evaluation / Compareの3製品だけを表示します。
04 Professional / 05 Disaster / 06 Twinはv2.2.0正式製品として表示しません。

公開製品名は「AZRAS Planning」です。
歴史的な内部フォルダー名 `01_AZRAS_Planning_Basic` および旧BAT名は、
既存ソース互換のためLauncherがaliasとして認識しますが、公開名称には使用しません。

【言語方針】
内部データ・保存メタデータ・識別子は英語Canonicalです。
日本語はUI表示翻訳です。

【起動条件】
Installer自体はPython無しでも配布EXEから起動できます。
ソース版を起動する場合はPython 3.13（64-bit）を使用します。
