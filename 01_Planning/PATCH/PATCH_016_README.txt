PATCH_016 — 260916 UTC — v1.0.621
========================================

対象ファイル:
  - services/environment_engine_v9_1.py
  - module2/app.py

--------------------------------------------------------------------
1) ベタ基礎底断熱／土間下断熱の位置取り違えバグ
--------------------------------------------------------------------
症状:
  「1階床・基礎・RC蓄熱詳細」画面で「ベタ基礎底断熱あり」だけをチェックし
  「土間下断熱あり」は未チェックのまま厚さ・λを入力しても、Project JSON
  の floor_thermal_breakdown 側では slab_under_insulation が true になって
  出力される（floor_thermal_settings 側は正しく false のまま）。

原因:
  environment_engine_v9_1.py の地盤U値計算 if/elif連鎖に、floor_cfg 自身の
  foundation_bottom_insulation フラグを読む分岐が存在しなかった。
  slab_sc.enabled → foundation_sc.enabled（どちらも比較シナリオ経由の
  上書き専用） → slab_under_insulation の3分岐しかなく、ユーザーが
  foundation_bottom_insulation だけをONにした場合は最後のフォールバック
  （Module1図面プロファイル）に落ち、入力値が無視されたうえ結果が
  slab_under_insulation=True と誤記録されていた。

修正:
  foundation_bottom_insulation 専用のelif分岐を追加し、ユーザー入力の
  slab_insulation_thickness_mm / slab_insulation_conductivity_W_mK を
  正しく反映。ground_insulation_source も
  "floor_thermal_foundation_bottom" として区別。

あわせて module2/app.py:
  - 「ベタ基礎底断熱あり」「土間下断熱あり」を排他選択に変更。
  - 共通の厚さ入力欄ラベルを固定の「土間下断熱厚」から、どちらの位置にも
    使う共通欄であることを示すラベルに変更。

--------------------------------------------------------------------
2) 8760時間比較で断熱を薄くしたのに冷房負荷が下がる現象
--------------------------------------------------------------------
症状:
  断熱・蓄熱8760時間比較（PATCH_402画面）で、屋根・外壁・RC壁を現状仕様
  より薄い仕様に変更した比較案のほうが、現状仕様より年間冷房負荷が小さく
  表示される。

原因:
  比較行の「比較断熱位置」は、Module1が insulation_position を確定できて
  いない場合デフォルトで「その他」（mass_coupling係数0.50）になっていた。
  一方、基準値（現状仕様）側は比較シナリオが無効なため常に係数1.00
  （＝外断熱相当のフル蓄熱容量）で計算される。そのため、厚さを変える
  つもりで比較行のチェックを入れただけで、RC壁・床のアクティブな蓄熱
  容量が無条件に半分に減らされ、これが厚さ変更とは無関係に冷房負荷を
  押し下げていた。

修正:
  insulation_position が未確定の場合のデフォルトを「その他」→「外断熱」
  （係数1.00）に変更し、基準値側の暗黙の前提と揃えた。

注記（今回は未対応）:
  「現状断熱位置」列が「未確認」表示になるのは、Module1のAI積算取得時に
  insulation_position 自体を抽出していないため。図面注記に位置が明記
  されているケースでは、Module1側のAIプロンプト／スキーマに
  insulation_position 抽出を追加すれば「現状断熱位置」列も正しく表示
  できるようになる見込み。別途対応可能。

--------------------------------------------------------------------
検証:
  python3 -m py_compile services/environment_engine_v9_1.py module2/app.py
  で構文エラーなしを確認。実際の8760時間ソルバー実行による数値再検証は
  未実施（気象データ・実行環境が本チャットセッションにないため）。
