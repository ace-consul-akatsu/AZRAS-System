PATCH_047 — 260923 UTC — v2.2.0
========================================

対象ファイル:
  - module1/app.py
  - VERSION / VERSION.json / CHANGELOG.md

要望内容:
  3製品（01_Planning_46 / 02_Evaluation_09 / 03_Compare_05）の横断監査で見つかった不具合の修正。

修正:
  module1/app.py の辞書でキーが重複していた（後の値が黙って優先される）。
  1. _CANONICAL_EN_REPLACEMENTS の "図面" が2回（"drawing" と "drawings"）。
     実際に効いていた後者を残し、前者を削除（動作は不変）。
  2. 英語→日本語 表示表の "Exterior window glazing" が2回
     （"外壁窓ガラス" と "外部窓ガラス"）。後者が効いていたため、
     外壁窓ガラス → Exterior window glazing → 外部窓ガラス と往復で表記が変わっていた。
     Module 1 内の照合処理（外壁窓ガラス で判定）と一致させるため後者を削除。

確認:
  - dev_checks 24本すべて PASS、pyflakes の「dictionary key repeated」警告ゼロ。
