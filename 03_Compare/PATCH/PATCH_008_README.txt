PATCH_008 — 260930 UTC — v2.2.0（v2.3.0 横断監査前の手直し）
========================================

対象ファイル:
  - comparison/price_basis.py（新規・tkinter 非依存）
  - main.py（読込時の「比較前提の確認」：単価根拠の判定と表示）
  - comparison/premise_book_ui.py（7タブ B/D リストの建物列）
  - dev_checks/patch_008_price_basis_premise_book_self_check.py（新規）
  - dev_checks/patch_003_legend_layout_and_comparison_premise_self_check.py（判定の移設に追従）
  - VERSION.json

要望内容:
  2×6・AZRAS・RCラーメンの3棟を比較したところ「単価根拠が揃っていません」の警告が出た。
  2×6 は全行AI概算単価、AZRAS はコンクリート・鉄筋だけ内蔵地域単価（残りはAI）。
  同じ XPS（12.255 m3）で 2×6 約41,500円/m3、AZRAS 約74,000円/m3 など、
  共通工種でも Project ごとに AI 単価が異なっていた。単価をそろえる仕組みが必要。

調査結果:
  そろえる仕組み自体は PATCH_005（7. 比較前提表）＋ 01 Planning PATCH_043 で実装済み。
  共通工種の単価差を一覧 → 人が採用単価を決定 → 各Projectの比較用コピーへ書込
  → 01 Planning Module 5・02 Evaluation Module 6/7 で再計算 → コピーを比較。
  ただし次の2点で、手順どおりに進めても目的を果たせなかった。

原因と修正:
  1. 手順どおり作ったコピーでも、同じ警告が再び出ていた。
     比較前提表は工法固有の工種と「工法で仕事が違う工種」（型枠・コンクリート・鉄筋・
     フェノールフォーム）を統一対象から外し、各Projectの単価のまま残す（設計どおり）。
     01 Planning は、この残した工種に内蔵地域単価が1行でもあるコピーを
     mixed_comparison_group_and_regional_database、無いコピーを
     comparison_group_premise_book と記録する。PATCH_003 の警告はこの記号の一致だけを
     見ていたため、コピー同士でも必ず「揃っていない」と判定していた。
     → 修正前コードで再現確認済み（コピー2件で警告が出る）。
     → comparison/price_basis.py が3状態を判定：
         uniform：記号が1つ → 表示なし
         premise_book_aligned：全件が同じ版の比較前提表のコピーで、記号が上記2種のみ
           → 警告ではなく「情報」ダイアログ。各Projectが自前単価のまま持つ工種と
             その出所（地域単価／AI単価）を列挙し、統一したい場合の操作（A 除外工種
             リストで区分を「共通」に変えて作り直す）を示す。
         misaligned：それ以外 → 従来どおり警告
     → 元Project同士、版の異なるコピー、コピーと元Projectの混在、
       Module 5 未再計算のコピーは引き続き警告（検査済み）。
     → 行の出所の判定は 01 Planning _price_basis_fingerprint と同じ規則。
       保存済みでない module5 は extractor と同じく読まない。
  2. 警告に「どうそろえるか」が書かれていなかった。
     → 内蔵地域単価で値付けされた工種を Project ごとに表示。
     → 7タブでの5段階の手順（一覧を作成 → B単価・D家賃を決定 → 比較用コピーを作成
       → 01 Planning Module 5 → 02 Evaluation Module 6/7 → コピーを読込）を追記。
       引用したボタン名が7タブに実在することを自己検査で確認。
  3. 7タブの B 単価差リスト・D 事業前提が建物1〜3の列しか表示していなかった
     （Compare は2〜7件を読込可能。4件目以降の単価が画面に出ない）。
     → 建物1〜7の列を表示し、横スクロールバーを追加。

変更していないもの:
  - 単価・数量・合計・CF・CO₂の値。グラフ・集計は従来どおりそのまま表示。
  - 比較前提表の決定内容・コピーの書き出し形式・工種区分表。
  - 01 Planning（変更なし。01_Planning_48 のまま）。

確認:
  - 新規 dev_check：Planning の記号規則どおりのコピー3件（2×6・AZRAS・RC）で
    警告が消え情報表示になること、実際の App で元Projectは警告（手順・地域単価工種付き）、
    コピーは情報ダイアログ（日英）になること、7タブが建物7列を持つことを確認。
  - 7タブに5件読込で5件分の単価が表示されることを確認。
  - dev_checks 12本すべて PASS、pyflakes 警告なし。
  - 01_Planning_48 の dev_checks 30本も PASS（変更なしの確認）。
