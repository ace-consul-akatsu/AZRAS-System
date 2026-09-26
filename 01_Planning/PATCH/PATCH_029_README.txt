PATCH_029 — 260919 UTC — v2.2.0
========================================

対象ファイル:
  - module1/app.py

要望内容:
  マルコ氏より、「方位入力欄の値が、最後に解析を実行した時の値と異なる場合は
  再解析が必要」と警告を出してほしい、という依頼。

背景（実際にあった事象）:
  建築図の平面図に描かれた方位（コンパス記号）が自動検索できず、
  北方位入力欄に手動で33.6°を入力したが、保存したProject JSONを見ると
  module_outputs.module1.drawing_analysis.north_rotation_confirmed が
  falseのまま、profile.north_rotation_degも0.0のままだった。

原因（前回の回答で特定済み）:
  保存処理（27908行目付近）は入力欄の現在値を常にcommon.north_rotation_deg
  へ書き込むが、drawing_analysis.north_rotation_input_deg／confirmedや、
  方位依存の数量（壁面積・胴縁方位など）はrun()内でanalyze_pdf()を実行した
  「その瞬間」の入力欄の値でしか更新されない（13565〜13569行目付近）。
  つまり「解析を実行」より後に方位を書き換えても、保存はできるが数量には
  反映されない。

対応:
  1. __init__に self._north_last_analyzed_value（最後に解析した時の方位）
     と self._north_last_analyzed_known（一度でも解析済みか）を追加し、
     self.northへの書き込みを監視するtraceを登録。
  2. run()がanalyze_pdf()を実行した直後に、その回で使われた入力値を
     baselineとして記録するよう変更。
  3. restore_saved_state()で、保存済みProject JSONの
     drawing_analysis.north_rotation_input_degからbaselineを復元
     （未解析のProjectではknown=falseのままとし、警告を出さない）。
  4. 北方位入力欄の下に警告ラベル（self.north_stale_label）を追加。
     現在の入力欄の値がbaselineと異なる場合、
     「⚠ 方位（北方位入力欄）が最後に「解析を実行」した時の値と異なります。
     図面解析・数量計算へ反映するには、もう一度「解析を実行」してください。」
     という警告文を赤字で表示し、入力欄の背景色もオレンジ
     （#ffd8a8）に変える。値を戻す、または解析をやり直すと警告は消える。
  5. 一度も解析を実行していない新規Projectでは、比較対象となる
     baselineが存在しないため、値を入力しても警告は出さない
     （的外れな警告を防止）。

検証:
  dev_checks/配下の全15スクリプトを実行し、全てPASSを確認。
  Xvfb上でModule1Appを実際に起動し、以下のケースを確認:
    - 未解析の新規Projectでは、方位欄に値を入力しても警告が出ないこと
    - 「33.6°で解析済み」として保存されたProjectを開くと、
      欄の値がbaseline(33.6)と一致するため警告が出ないこと
    - その状態で欄を45に変更すると警告文と背景色オレンジが表示され、
      33.6に戻すと警告が消え、背景色も元に戻ること
    - 空欄・数値変換できない文字列（"abc"等）は、未解析時のbaseline
      （null）と同じ扱いになり誤警告を出さないこと
  修正前後でpyflakesの警告件数・内容が完全に一致することを確認し、
  今回の変更が新たな未使用変数等を持ち込んでいないことを確認。
