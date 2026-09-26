PATCH_027 — 260918 UTC — v1.0.631
========================================

対象ファイル:
  - module1/app.py（_ensure_azras_mandatory_scope_coverage_rows のバグ修正）

報告内容:
  マルコ氏より、「AZRASではない2×6のProject」であるにもかかわらず、
  Module 1の「不明・図面矛盾への回答」画面に
  「AZRAS内部RC界壁コンクリート」「AZRAS内部間仕切2×6構造材」
  「AZRAS天井下地・構造材」「AZRAS 1階床下地・構造材」
  「AZRAS 2階床構造材」「AZRAS屋根構造材」
  という6行（いずれも現在値0.0、状態=回答済み）が表示される、との
  スクリーンショット付き報告があった。Module 1の建築システムは
  「一般建築」（AZRAS Platformではない）、構造＝木造枠組壁構造、
  工法詳細＝2×6が選択されている。

原因:
  module1/app.py の _ensure_azras_mandatory_scope_coverage_rows()
  （PATCH_576で追加、AZRAS Platform専用の構造スコープが図面・AIの
  双方から漏れた場合に「未回答項目」として必ず可視化するための機能）
  のガード条件が誤っていた。

    method = common.get("construction_method_id")（空なら""）
    if method and method != "azras":
        return takeoff   # ここで注入をスキップする「はず」だった

  この条件は「methodが非空文字列で、かつ"azras"でない」場合のみ
  スキップする、という書き方になっていた。ところが
  construction_method_id が未設定・空文字列のタイミングでこの関数が
  呼ばれると、`method` が空文字列（Falsy）となり、
  `if method and ...` の前半で条件全体がFalseになってしまうため、
  スキップされずにAZRAS専用の6項目がそのまま注入されていた。

  本来のコメント（"Do not inject AZRAS-specific construction scopes
  into 2x6/RC/S projects."）が意図していたのは「method が"azras"で
  ない限り注入しない」であり、"methodが空でない場合に限り"という
  前提は誤りだった。

対応:
  ガード条件を `if method != "azras": return takeoff` に修正し、
  空文字列・未設定のケースも含めて「"azras"であると確認できない限り
  注入しない」という本来の意図通りの動作にした。

  あわせて、この関数が過去に誤って注入した「AZRAS専用の6項目」が
  既にProject JSON内に残っているケース（今回のスクリーンショットの
  ように、既に0.0で回答済みとして残ってしまっている場合）についても、
  method が "azras" でないと判定された際に、この関数自身が付与する
  目印（coverage_gap_required:true かつ coverage_gap_key が
  "azras_"で始まる）を持つ行だけを対象に、安全に取り除くようにした。
  ユーザーが手入力した実データや、他の仕組みが追加した行には一切
  触れない。

検証:
  以下3パターンをコードで直接再現し、修正後の期待通りの動作を確認した。
    1. construction_method_id が空文字列（今回の再現ケース）
       → 新規注入なし、かつ既存の紛れ込んだAZRAS専用行（6項目）が
         除去され、本来のユーザーデータ（例：Foundation concrete）は
         そのまま残る。
    2. construction_method_id が一般の2×6系ID
       → 同上（新規注入なし、mandatory_scope_coverage_auditも
         追加されない）。
    3. construction_method_id が "azras"
       → 従来通りAZRAS専用の6項目が正しく注入される（回帰なし）。

再発防止:
  dev_checks/azras_scope_leakage_regression_self_check.py を追加し、
  上記3パターンを自動検証する。
