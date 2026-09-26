PATCH_003 — 260919 UTC — v2.2.0
========================================

対象ファイル:
  - core/line_chart.py（新規追加）
  - module4/app.py（200年環境：累積CO₂グラフを追加）
  - module6/app.py（200年事業：単純投資回収／現在価値ベース回収グラフを追加）

要望内容:
  マルコ氏より、02_Evaluationでは表（数値テーブル）は出るが、
  03_Compareのようなグラフ表示ができない。単独の建物仕様でも、
  環境（CO₂）と事業（投資回収）それぞれで03_Compareと同じグラフを
  出したい。03_Compareは2件以上のProject JSONを読み込まないと
  単独では起動できないため、という依頼があった。

対応:
  03_Compareのmain.py内にある自己完結型のLineChart（tk.Canvas
  ベース、matplotlib等の外部依存なし）クラスを、内容を変更せずに
  core/line_chart.pyへ移植した。

  Module 4（200年環境）:
    既存のresults／timeline（表）2ペインのPanedwindowに、3つ目の
    ペインとして累積CO₂排出量グラフを追加。データはModule 4自身が
    既に計算済みのself.result["annual_timeline"]の
    cumulative_co2_kgをそのまま使用しており、新たな計算は行って
    いない。表示文言・免責事項は03_Compareの「③ 200年間CO₂累積」
    パネルと同一の内容。show_result()の末尾で更新するため、計算後・
    言語切替時・保存済みJSON再読込時のいずれでも表と同じタイミングで
    グラフが更新される。

  Module 6（200年事業）:
    summary／timeline（表）2ペインの下に、新しいセクションとして
    ①単純投資回収（名目累積CF・初回回収点を拡大表示）、②現在価値
    ベース回収（割引累積CF）の2つのグラフを左右に追加。データは
    Module 6自身が既に計算済みのself.result["cashflow"]の
    cumulative_unlevered_cash_flow_ex_terminal／
    cumulative_discounted_unlevered_cash_flow_ex_terminalと、
    self.result["summary"]["initial_total_investment"]をそのまま
    使用しており、新たな計算は行っていない。これらは03_Compareの
    comparison/extractor.pyが同じProject JSONから読みに行くのと
    全く同じフィールドであるため、画面に出る回収年は03_Compareで
    同じ建物を表示した場合と一致する。回収年判定ロジック
    （0円ラインを下から上へ超える最初の年）も03_Compareの
    _discounted_payback_yearと同一のアルゴリズムを使用。
    表示文言・免責事項も03_Compareの「④単純投資回収」「⑤現在価値
    ベース回収」パネルと同一の内容。

検証:
  dev_checks/配下の全7スクリプトおよびfull_self_check.pyを実行し、
  全てPASSを確認。
  加えて、Xvfb（仮想ディスプレイ）上でModule4App／Module6Appを
  実際に起動し、合成テストプロジェクトで以下を確認:
    - calculate()直後にグラフへ実データが描画されること
      （Module6: 単純投資回収18年／現在価値ベース回収29年、
       Module4: 200年時点の累積CO₂ 414 t-CO₂、いずれも入力値に
       対して妥当な計算結果）
    - change_language("en")後も表題・ラベルが正しく英語に切り替わり
      グラフが再描画されること
    - save_output()で保存したProject JSONを新しいModuleインスタンスで
      開いた場合（restore_saved_state経路）も、計算し直すことなく
      保存済みの結果からグラフが正しく描画されること
