PATCH_007 — 260924 UTC — v2.2.0（v2.2.0 ベースライン完成版）
========================================

対象ファイル:
  - comparison/extractor.py
  - comparison/premise_book.py
  - dev_checks/patch_007_market_rent_yield_contract_self_check.py（新規）
  - dev_checks/version_consistency_self_check.py（新規）
  - dev_checks/duplicate_dict_key_self_check.py（新規・4製品共通）
  - dev_checks/pyflakes_undefined_names_self_check.py（新規・4製品共通）
  - README.txt / README_JA.txt / NOTICE.txt（版表記）
  - VERSION.json

要望内容（4製品横断監査の指摘）:
  1. 02 Evaluation PATCH_009 で市場家賃モードの保存形式が変わったが、
     03 Compare が追従しておらず、市場家賃の Project でも目標表面利回りを拾っていた。
  2. 版情報が VERSION.json（2.2.0）と README／NOTICE（1.1.17～1.1.19、v2.0.0）で不一致。

02_Evaluation_09 の実際の保存形式（Evaluation の計算関数を実行して確認）:
  市場家賃モードの module6 出力
    summary.target_gross_yield_percent        = null
    summary.stored_target_gross_yield_percent = 利用者の設定値（例 6.5）
    summary / settings.target_gross_yield_active = false
    settings.target_gross_yield_percent       = 利用者の設定値（画面復元用に保持）

原因と修正:
  1. extractor.py：
     m6.get('target_gross_yield_percent') or settings.get('target_gross_yield_percent')
     が、上位に無い値を settings の設定値（6.5 / 8.0）で補い、
     市場家賃なのに「目標利回りあり」と報告していた。
     → 判定順を「target_gross_yield_active フラグ（summary / settings）
       → 家賃設定方法（gross_yield のみ有効）→ 設定方法が保存されていない旧JSONは従来どおり」
       に変更。無効な利回りは target_gross_yield_percent に出さず、
       stored_target_gross_yield_percent（参考値）として別に出す。
       target_gross_yield_active も出力に追加。
     → 0.0 が「or」で読み飛ばされる潜在不具合も同時に解消。
     → 家賃設定方法が _input_snapshot.settings にだけある場合も読む。
  2. premise_book.py：
     無効な目標利回り（3項目）が Project 間の「前提差」として比較前提表に出ていた。
     比較前提表は全コピーを市場家賃に統一するため、これは前提ではない → 除外。
     比較コピーは Evaluation 自身と同じ形で保存：
       target_gross_yield_active = false、利用者の設定値はそのまま保持。
     （null にすると Module 6 が再読込時に 8.0 で埋めるため、6.5 等の設定値が失われる。）
     PATCH_007 より前に発行された前提表に利回りの決定値が残っていても、コピーへは書き戻さない。
  3. 版情報：README／NOTICE を 2.2.0 に統一、VERSION.json の patch を数値に統一。
     版情報の自己検査を追加。
  4. 4製品で自己検査の基準をそろえるため、辞書キー重複検査・pyflakes 未定義名検査を追加
     （いずれも現状でエラーなし）。

変更していないもの:
  - 数値CF・CO₂・コストの計算、比較キー、家賃設定方法そのものの差の検出。
  - gross_yield モードの Project は従来どおり有効な目標利回りを表示。
  - 元の Project JSON は一切変更しない（コピーのみ）。


追加（再発行時）: ライセンスを MIT License に統一
  AZRAS-System リポジトリのルート LICENSE（MIT License、著作権者 株式会社ACE総合コンサル）と、
  製品内 LICENSE.txt（独自の許諾文）が食い違っていた。
  → LICENSE.txt を MIT License 全文＋日本語の参考訳（英文が優先）に差し替え。
  → 新規 dev_checks/license_consistency_self_check.py：LICENSE.txt が MIT 全文であることを検査。

確認:
  - 新規 dev_check：02_Evaluation_09 の計算関数が実際に出力した市場家賃データで、
    修正前コードは NG（6.5 を目標利回りとして返す）、修正後は PASS。
  - dev_checks 11本すべて PASS、pyflakes 警告なし、GUI起動スモーク PASS。
