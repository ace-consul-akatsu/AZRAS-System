PATCH_021 — 260917 UTC — v1.0.626
========================================

対象ファイル:
  - module2/app.py
  - module1/app.py（辞書追加のみ）
  - dev_checks/comparison_floor_position_self_check.py（新規）

--------------------------------------------------------------------
1) 8760時間比較の「床・土間」行が、ベタ基礎底断熱の設定を無視していた
--------------------------------------------------------------------
症状:
  「1階床・基礎・RC蓄熱詳細」で「ベタ基礎底断熱あり」を確定済み・
  「土間下断熱あり」は未チェックにしているにもかかわらず、断熱・蓄熱
  8760時間比較（PATCH_402画面）の「床・土間」行では「現状断熱位置」が
  「未確認」のまま表示される。

原因:
  module2/app.pyの比較テーブル行構築コードが、
    if part == "slab" and floor_saved.get("slab_under_insulation"):
  という条件でしか「床の断熱設定は確定済みの根拠がある」と判定しておらず、
  foundation_bottom_insulationを見る分岐が存在しなかった。これは
  PATCH_016でenvironment_engine_v9_1.py（実際の計算エンジン）側に見つけて
  直したのと全く同じ抜け漏れが、別ファイル（比較テーブルの表示側）に
  独立して存在していたことを意味する。

修正:
  該当2箇所の条件を
    floor_saved.get("slab_under_insulation") or floor_saved.get("foundation_bottom_insulation")
  に変更。

再発防止:
  dev_checks/comparison_floor_position_self_check.py を新設。
  module2/app.py内に上記の統合条件が（2箇所とも）存在するかをソース
  レベルで確認する。

--------------------------------------------------------------------
2) 英日混在表示の追加語彙ギャップ
--------------------------------------------------------------------
「不明・図面矛盾への回答」画面で新たに確認された未対応語（Branch、
Cold-water、Hot-water、condensate drain、drain、structural sheathing、
decking、exhaust routes）を辞書に追加した。garbled_mixed_language_
label_self_check.pyのテストケースにも追加。

限界（正直な注記、継続）:
  この語彙追加方式は引き続き「有限の辞書で無限のAI表現を追いかける」
  構造的な限界を持つ。今回も新しい図面・新しい取り込みのたびに未対応語が
  出てくる可能性がある。
