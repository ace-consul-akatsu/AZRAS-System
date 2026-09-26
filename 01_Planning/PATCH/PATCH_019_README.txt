PATCH_019 — 260917 UTC — v1.0.624
========================================

対象追加ファイル:
  - resources/ai_takeoff_contract/AZRAS_AI_START_GEMINI_EMPHASIS_v1.txt（新規）

経緯:
  260916_1110の依頼ラウンドで、Geminiの回答（gemini-code-...json）が
  他の3社（Claude/ChatGPT/Meta）と比べて明らかに簡略化されており、
  スキーマも独自形式（PRE_TAKEOFF_NNN形式のlocal_id、item_name/spec/
  quantityのみのフラットな構造）で、必須のtakeoff_items網羅も
  calculation_ledger等の根拠情報も欠けていた。標準のAZRAS AI START
  テキストの指示を守り切れていない可能性が高いと判断し、マルコ氏より
  Gemini向けに指示をより明示的・強調した依頼文の作成を依頼された。

対応:
  標準のAZRAS AI STARTテキストをベースに、以下を強化した専用版を
  resources/ai_takeoff_contract/AZRAS_AI_START_GEMINI_EMPHASIS_v1.txt
  として追加した。
  - 冒頭に「これまでGeminiの回答で見られた3つの失敗パターン」を明示
    （簡略化された要約での回答、独自スキーマでの回答、正確な値の代わりに
    丸めた概算値を使うこと）
  - レスポンステンプレートの項目名をそのまま使うことの再強調
  - 送信前のセルフチェックリスト（8項目）を追加し、Gemini自身に送信前の
    形式検証を促す

注記（今回は未実装）:
  このファイルは現時点では静的なリソースとして追加しただけで、
  依頼パッケージ生成コード（module1/app.py内、AZRAS AI STARTテキストを
  組み立てる箇所）への自動連携（AI提供元ごとに異なるSTARTテキストを
  自動選択する機能）は実装していない。現状は、Gemini宛てに依頼する際、
  このファイルを標準のSTART.txtの代わりに手動で使う運用を想定している。
  提供元別の自動切替をソフト側に組み込む場合は、別途UI設計（依頼先AI選択
  ドロップダウン等）が必要になる。

検証:
  python3 -m py_compile および既存dev_checks全件が引き続き通ることを
  確認済み（このパッチはコードロジックを変更していないため、新規の
  自己検証スクリプトは追加していない）。
