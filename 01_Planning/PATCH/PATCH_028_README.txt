PATCH_028 — 260919 UTC — v2.2.0
========================================

対象ファイル:
  - VERSION.json（schema_version）
  - core/version.py（DEFAULT_SCHEMA_VERSION）
  - dev_checks/duplicate_function_definition_self_check.py（新規追加）

報告内容:
  00_Installer_01 / 01_Planning_26 / 02_Evaluation_01 / 03_Compare_01 の
  4製品を対象にした横断監査で、以下2件の不整合を検出した。

問題1: schema_versionの不一致
  01_PlanningのVERSION.jsonのschema_versionが "1.0.632"、
  core/version.pyのDEFAULT_SCHEMA_VERSIONが "1.0.620" になっており、
  02_Evaluation・03_Compareが共通で使用している
  Core Project JSON Schema "3.0" と食い違っていた。
  実際にはEvaluation側のmigrate_project()がロード時にschema_versionを
  強制上書きするため即クラッシュには至らないが、VERSION.jsonの記載が
  事実と異なっており、以前の横断監査で統一されたはずの値が
  01_Planningのv2.2.0再ベースライン時に誤って製品バージョン番号
  (1.0.6xx系)に置き換わってしまっていたと見られる。

対応1:
  VERSION.jsonのschema_versionを "3.0" に修正。
  core/version.pyのDEFAULT_SCHEMA_VERSIONを "3.0" に修正。
  DEFAULT_VERSION（製品バージョンのフォールバック、"1.0.620"）は
  schema_versionとは別概念のため変更していない。

問題2: duplicate_function_definition_self_checkが01_Planningに未導入
  00_Installer / 02_Evaluation / 03_Compareの3製品は、いずれも
  「01_Planning PATCH_017で見つかった、同名関数の重複による
  修正の無効化」を理由にdev_checks/duplicate_function_definition_
  self_check.pyを追加済みだったが、発生源である01_Planning自身の
  dev_checks/にはこのチェックが存在しなかった。

対応2:
  他3製品と同一内容のdev_checks/duplicate_function_definition_
  self_check.pyを01_Planningのdev_checks/にも追加した
  （製品固有の記述を含まない共通スクリプトのため、内容の変更なし）。
  追加後に実行し、01_Planning内に同名関数の重複が無いことを確認済み。

検証:
  dev_checks/配下の全15スクリプトを実行し、全てPASSすることを確認。
  （all_python_sources_compile / pyflakes_undefined_names を含む）

再発防止:
  今後、01_PlanningのVERSION.json再ベースライン時は、schema_version欄
  だけは製品バージョン番号と連動させず、02_Evaluation/03_Compareと
  同一の値（現在は"3.0"）に固定することを明記。
