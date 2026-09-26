PATCH_003 — 260924 UTC — AZRAS Installer 5.0.4（AZRAS v2.2.0 ベースライン完成版）
========================================

対象ファイル:
  - VERSION.json / azras_installer.py
  - README_JA.txt / README_EN.txt / NOTICE.txt
  - docs/AZRAS_Installation_Guide_JA.html / docs/AZRAS_Installation_Guide_EN.html（版表記のみ）
  - dev_checks/version_consistency_self_check.py（新規）
  - dev_checks/launcher_product_resolution_self_check.py（新規）
  - dev_checks/duplicate_dict_key_self_check.py（新規・4製品共通）
  - dev_checks/pyflakes_undefined_names_self_check.py（新規・4製品共通）

要望内容:
  4製品横断監査の指摘のうち 00 Installer 分（版管理の不整合）と、v2.2.0 ベースライン完成。

修正:
  1. 版情報が4種類あった
       画面 5.0.4-p032 / README 5.0.4-p033 / NOTICE 5.0.4-p032 /
       VERSION.json 5.0.4-p001 ＋ patch "2"
     → 製品版は 5.0.4（Installer 独自系列のまま）。パッチ番号は VERSION.json の
       "patch"（数値）だけに持たせ、版の文字列から -pNNN を外した。
     → azras_installer.py は VERSION.json から版を読む（直書きを廃止）。
     → README・NOTICE・インストール手順書（5.0.0 と記載）を 5.0.4 に統一。
     → NOTICE の「検証済み製品セット」（Planning 1.0.614 / Evaluation 1.0.215 /
       Compare 1.1.19、AZRAS v2.0.0）を v2.2.0 ベースラインの組み合わせに更新：
       Planning 2.2.0 PATCH_048 / Evaluation 2.2.0 PATCH_010 / Compare 2.2.0 PATCH_007
  2. フォルダ番号とパッチ番号のずれ
     PATCH_002 が 00_Installer_01 のまま納品されていた。今回は PATCH_003 として
     00_Installer_03 とし、他の3製品と同じく「フォルダ番号＝パッチ番号」に戻した
     （00_Installer_02 は欠番）。
  3. ランチャーの確認（変更なし）
     新しいフォルダ名（01_Planning_48 / 02_Evaluation_10 / 03_Compare_07）と
     旧フォルダが並んでいても、番号の大きい方を数値で比較して起動することを
     新規自己検査で確認（_10 が _09・_9 より優先される）。

変更していないもの:
  - インストール・ランチャー・ショートカット作成の動作。


追加（再発行時）: ライセンスを MIT License に統一
  AZRAS-System リポジトリのルート LICENSE（MIT License、著作権者 株式会社ACE総合コンサル）と、
  製品内 LICENSE.txt（独自の許諾文）が食い違っていた。
  → LICENSE.txt を MIT License 全文＋日本語の参考訳（英文が優先）に差し替え。
  → 新規 dev_checks/license_consistency_self_check.py：LICENSE.txt が MIT 全文であることを検査。

確認:
  - dev_checks 7本すべて PASS、pyflakes 警告ゼロ。
  - 版情報の自己検査は、旧表記（5.0.4-p032 直書き、手順書 5.0.0、NOTICE の旧製品版）で NG になることを確認。
  - GUI起動スモーク PASS（Installer「AZRAS Installer Version 5.0.4」、Launcher「AZRAS v2.2.0」）。
