PATCH_010 — 260924 UTC — v2.2.0（v2.2.0 ベースライン完成版）
========================================

対象ファイル:
  - VERSION.json / core/version.py
  - NOTICE.txt / FINAL_RELEASE_STATUS.txt / ROOT_MANIFEST.txt / README.txt / README_JA.txt
  - docs/maintenance/CURRENT_BUILD_GUIDE.txt
  - version_info_AZRAS_Evaluation.txt（自動生成に変更）
  - build_AZRAS_Evaluation.bat
  - build_tools/make_version_info.py（新規・4製品共通）、build_tools/__init__.py（新規）
  - dev_checks/version_consistency_self_check.py（新規）
  - dev_checks/duplicate_dict_key_self_check.py（新規・Planning と共通）
  - dev_checks/pyflakes_undefined_names_self_check.py（新規・Planning と共通）
  - 削除: APPLY_LOCATION.txt（v1.0.215 の古い適用手順）
  - 削除: APPLY_PATCH_154.txt（PATCH 154 の古い適用手順）

要望内容:
  4製品横断監査の指摘のうち 02 Evaluation 分（版情報）と、v2.2.0 ベースライン完成。

修正:
  1. 版情報を VERSION.json に一元化
     NOTICE・FINAL_RELEASE_STATUS は 1.0.215、ROOT_MANIFEST・ビルド手順書は 1.0.212 と
     記載していた → すべて 2.2.0（パッチ番号は VERSION.json 参照）。
     README にも版を明記。core/version.py の予備値 1.0.215 → 2.2.0。
     VERSION.json の patch を文字列 "9" から数値 10 に（4製品で数値に統一）。
  2. EXE ビルドの版情報ファイル
     version_info_AZRAS_Evaluation.txt が 1行の文字列で、PyInstaller が eval できず
     EXE ビルドがそこで止まる状態だった → VERSION.json から VSVersionInfo 形式で生成。
     build_AZRAS_Evaluation.bat が PyInstaller の直前に毎回再生成。
     EXE のファイルバージョン = 2.2.0.10。
  3. 自己検査の追加（4製品で同じ基準にそろえる）
     版情報の一致、辞書キー重複、pyflakes 未定義名。いずれも現状でエラーなし。

市場家賃 Contract（PATCH_009）の突き合わせ:
  services/investment_engine_v9_5.calculate_investment を実行し、市場家賃時の保存形式を確認。
    summary.target_gross_yield_percent = null
    summary.stored_target_gross_yield_percent = 利用者の設定値
    summary / settings.target_gross_yield_active = false
    settings.target_gross_yield_percent = 利用者の設定値（画面復元用）
  この実データで 03 Compare PATCH_007 が正しく読むことを確認済み（Compare 側の自己検査に固定）。
  Evaluation 側の計算・保存形式は変更なし。

変更していないもの:
  - 計算・画面・保存形式。

今後のパッチ作業での注意:
  - VERSION.json の patch を上げたら python build_tools/make_version_info.py を実行
    （忘れると version_consistency_self_check が NG）。


追加（再発行時）: ライセンスを MIT License に統一
  AZRAS-System リポジトリのルート LICENSE（MIT License、著作権者 株式会社ACE総合コンサル）と、
  製品内 LICENSE.txt（独自の許諾文）が食い違っていた。
  → LICENSE.txt を MIT License 全文＋日本語の参考訳（英文が優先）に差し替え。
  → 新規 dev_checks/license_consistency_self_check.py：LICENSE.txt が MIT 全文であることを検査。
  → 画面の「ライセンス」表示（core/branding.py）も同じ MIT 文面に変更し、LICENSE.txt と完全一致することを検査。


追加（再発行時）: Project JSON スキーマを保存形式（3.0）に一致
  data/project_schema_v2_0.json は schema_version を "2.0" に固定しており、
  v2.2.0 が保存する schema_version "3.0" の Project JSON はすべて不合格になっていた
  （サンプル18件・新規Projectで確認。不一致はこの1項目のみ）。
  → data/project_schema_v3_0.json を追加（構造は同一、schema_version "3.0"）。
    v2_0 は旧形式ファイル用として残す。
  → 新規 dev_checks/project_schema_consistency_self_check.py：スキーマの版と
    core/project_store.SCHEMA_VERSION の一致、新規 Project の検証（jsonschema があれば完全検証）。
  → docs/maintenance/SCHEMA_VERSION_MAP.txt に残っていた旧版表記（PATCH 140 / 1.0.140）を削除し、
    スキーマ文書の場所を追記。版情報の自己検査の対象に追加。

確認:
  - dev_checks 17本（既存12本＋新規5本）と full_self_check.py すべて PASS。
  - 生成した version_info を PyInstaller 6.22 の読込関数で読み込み、バイナリ化まで成功。
  - GUI起動スモーク PASS（タイトル「AZRAS Evaluation Version 2.2.0」）。
  - pyflakes 警告数は修正前後で同数（26・未定義名ゼロ）。
  - Windows 上での実ビルドはこの環境では未実施。
