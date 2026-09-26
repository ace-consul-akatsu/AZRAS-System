PATCH_020 — 260917 UTC — v1.0.625
========================================

対象ファイル:
  - module1/app.py（依頼パッケージ生成部の start_text を差し替え）
  - dev_checks/azras_ai_start_template_self_check.py（新規）

経緯:
  PATCH_019でGemini専用の強調版START文面を静的リソースとして追加したが、
  マルコ氏より「他のAIに同じものを送ったらどうなるか、既存の依頼文に
  追加して流す方法」を問われた。

検討結果:
  PATCH_019で書いたGemini向け文面は、末尾のAI IDENTITY部分に
  "you are Gemini" 的な決め打ちの一人称指定を含んでいたため、そのまま
  他社AI宛てに使うと誤った自己申告（analysis.ai_reviewerに間違った値を
  書かせる）を誘発する危険があった。一方、失敗パターンの警告文・
  セルフチェックリスト自体は特定AIに依存しない内容であり、既存の
  start_text生成（module1/app.py内、依頼パッケージ生成時に全AI共通で
  1つのSTART.txtとして出力される箇所）は元々「Identify YOURSELF from
  your own runtime/service identity」という自己申告方式で、特定AIを
  決め打ちしていなかった。

対応:
  Gemini限定の別ファイルとして温存するのではなく、失敗パターン警告
  ・セルフチェックリストを一般化（特定AI名を出さない書き方に修正）した
  うえで、module1/app.pyの共通start_text生成そのものに統合した。これに
  より、今後どのAIへ依頼パッケージを送っても、自動的にこの強化版の
  指示文が使われる。

追加された内容:
  - 冒頭に、AZRAS AI Takeoffで実際に見られた3つの失敗パターン（簡略化
    された要約での回答、独自スキーマでの回答、丸めた概算値の使用）を
    AI名を出さずに警告
  - ハード出力契約の再強調（各項目の理由・根拠フィールドを含めることの
    明示など）
  - 送信前のセルフチェックリスト（7項目）

再発防止:
  dev_checks/azras_ai_start_template_self_check.py を新設。
  1) 強化版に追加した主要セクション（STOP AND READ FIRST、
     BEFORE YOU RESPOND等）が引き続き含まれているかを確認。
  2) start_text組み立て箇所のソースに、特定AIの一人称指定
     （"you are gemini"等）が紛れ込んでいないかを確認（全AI共通の
     テンプレートに1社の識別を決め打ちする退行を防止）。
  3) わざと"STOP AND READ FIRST"の文言を書き換えたコードに対して、
     このチェックが実際に失敗する（＝検知できる）ことを確認済み。

注記:
  PATCH_019で追加したresources/ai_takeoff_contract/AZRAS_AI_START_
  GEMINI_EMPHASIS_v1.txt（Gemini限定の静的ファイル、一人称指定あり）は
  そのまま残している。本パッチの統合後は、通常は共通のSTART.txt生成
  だけで十分なはずだが、Gemini向けにさらに個別の念押しをしたい場合の
  補助資料として使える。
