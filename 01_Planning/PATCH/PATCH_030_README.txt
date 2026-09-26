PATCH_030 — 260919 UTC — v2.2.0
========================================

対象ファイル:
  - module1/app.py

要望内容:
  マルコ氏より、「電気設備図・機械設備図から実際に機器数量を拾えるように
  してほしい」という依頼。以前の横断監査（実プロジェクトのS-Structure_Sample
  で発見）で、document_wide_preflightは登録済みの設備図PDFの全ページを
  スキャンしていたが、quantity_takeoffには電気・機械設備の行が1件も
  生成されておらず、equipment_symbol_recognitionはnullのまま、
  mep_route_quantity_reconciliationのphysical_owner_countも0のまま
  だった。原因は「機器を数え上げて書き込む抽出処理自体が存在しない」
  ことだった（ルート長照合・Module5パッケージ価格紐付けの「枠組み」
  だけがあり、そこへ流し込むデータが無かった）。

対応:
  1. _extract_mep_equipment_facts(text) を新規追加。
     既存の_extract_joinery_facts（建具表抽出）と同じ方式の、
     決定論的なテキストスキャン（AI呼び出しではない）。
     「機　器　リ　ス　ト　（　○○設備　）」という見出し（各文字間に
     全角スペースが入る実際の表記に対応）をアンカーとしてセクションを
     区切り、区間内の各行を
     「<記号> <名称> 形式/型式 …… <台数> [設置場所] 参考型番」
     というパターンでマッチさせる。台数は「参考型番／location手前の、
     単独の整数トークンのうち最後のもの」として抽出するため、
     電源コード（例: 3-200）や消費電力（例: 1.37）が台数と誤認される
     ことはない。
  2. _collect_mep_equipment_source_text(self) を新規追加。
     登録済みPDFをextract_pdf_text()で直接読み直す。既存の
     _collect_registered_project_pdf_evidence()が組み立てるページ
     テキスト（埋め込み文字＋OCRのマージ）は、実際に確認したところ
     1行1トークンに近い形式になっており、本抽出処理の「表の1行を
     1行としてマッチさせる」正規表現とは相性が悪く、そのままでは
     0件しか拾えなかった（実データで検証して発覚し、抽出元をPDF
     直接読み込みに変更して解決）。
  3. _merge_mep_equipment_inventory(self, takeoff, project_evidence=None)
     を新規追加。上記で抽出した機器を、既存のadd()ヘルパーが生成する
     行と同じ形（category/item/quantity/confidence/evidence等）の
     quantity_takeoff行として追加する。台数が確定した機器は
     confidence 0.80・unit「台」・status系は既存の建具「シャッター」
     行と同じ扱い、台数列を確定できなかった機器（記号のみ検出）は
     既存の建具「存在確認・外部/内部未確定」行と同じ扱い（数量1・
     unit「箇所」・confidence 0.62）とする。
  4. run()内、project_evidence取得直後・_second_pass_cross_drawing_
     reconciliation実行前にこの統合処理を呼び出す。この位置は、
     行のmep_trade（hvac/plumbing/electrical/fire/other）を
     キーワード判定で自動付与する既存ロジック（_annotate_quantity_
     aggregation_ownership内、category/item/evidence文言から判定）
     より前になるため、新規追加した行に対して改めてタグ付けロジックを
     書く必要は無く、既存分類が自動的に機能する。
  5. 副次的に、_collect_registered_project_pdf_evidence()の戻り値に
     mep_text（joinery_text／structural_textと同じ考え方の、設備図に
     絞ったテキスト）を追加した。本抽出処理自体はこれを使わないが
     （上記2の理由）、将来の他機能のために用意した。

検証:
  実際にアップロードされた260919_S-Structure_工場事務所_機械設備図.pdf
  および290919_S-Structure_工場事務所_電気設備図.pdfを、Module1Appの
  実クラスメソッド経由（スタンドアロンスクリプトではなく）で最後まで
  通し、以下を確認:
    - 機械設備図から機器21件を、台数・設置場所とも実データと完全一致
      する形で抽出（空調設備7件=GHP各種、換気設備11件=EF・VF7台・
      HEX3台、衛生設備3件=DP-1・OTU-1・GW-1）
    - quantity_takeoff.rowsへ正しく統合されること
    - mep_cost_linkage.trade_row_counts が hvac=18／plumbing=3／
      electrical=0 と、既存のキーワード分類ロジックだけで正しく
      振り分けられること（コード変更なしで機能）
    - electrical=0は不具合ではなく、この電気設備図に機器リスト形式の
      表が実際に存在しない（特記仕様書のみ）ことを確認した正しい結果
      であること。将来、機器リスト形式の表を含む電気設備図が来れば
      同じ抽出処理がそのまま機能する
  dev_checks/配下の全15スクリプトを再実行し、全てPASSを確認。
  修正前後でpyflakesの警告が完全一致することを確認し、新規の不具合を
  持ち込んでいないことを確認。
