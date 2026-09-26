PATCH_048 — 260924 UTC — v2.2.0（v2.2.0 ベースライン完成版）
========================================

対象ファイル:
  - module1/app.py
  - dev_checks/pyflakes_undefined_names_self_check.py
  - dev_checks/duplicate_dict_key_self_check.py（新規）
  - dev_checks/version_consistency_self_check.py（新規）
  - build_tools/make_version_info.py（新規）、build_tools/__init__.py（新規）
  - core/version.py
  - version_info_AZRAS_Planning.txt（自動生成に変更）
  - AZRAS_Planning.spec / AZRAS_Planning_Basic.spec
  - build_AZRAS_Planning.bat / requirements.txt
  - README_JA.txt / README_EN.txt / NOTICE.txt（1行目の版表記のみ）
  - VERSION.json / CHANGELOG.md / PATCH_README.txt
  - 削除: VERSION（1.0.632・どこからも読まれていない）
  - 削除: version_info_AZRAS_Planning_Basic.txt（どの .spec からも参照されていない）
  - 削除: APPLY_LOCATION.txt（PATCH 573 / v1.0.573 時代の古い適用手順）
  - resources/ai_takeoff_contract/AZRAS_AI_Longitudinal_Observation_Protocol_v1.1_EN.md
  - dev_checks/ai_request_package_resources_self_check.py（新規）

要望内容:
  4製品横断監査（ChatGPT）の指摘のうち 01 Planning 分。

修正:
  1. 辞書キーの重複2件（module1/app.py 英語→日本語 表示表）
     "AZRAS actual sloped roof area" と "Exterior doors" が2回ずつ。
     前後とも同じ日本語値のため表示は不変。後ろ側を削除。
     PATCH_047 で見逃した理由：pyflakes は値が「異なる」重複しか警告しない。
     → 新規 duplicate_dict_key_self_check.py：値が同じでも重複キーを NG にする。
       全 .py の辞書リテラルと全 .json を検査。

  2. pyflakes 自己検査の抜け穴
     pyflakes が無いと [SKIP] を表示して終了コード0（＝PASS扱い）だった。
     → 未導入なら NG（終了コード1）。
     追加で見つけた抜け穴：pyflakes が構文解析できないファイルは
     エラー出力側にだけ出て無視され、「未定義名なし」になっていた → これも NG に。
     requirements.txt に pyflakes を追加（dev_checks 用）。

  3. 版情報の一元化（VERSION.json を唯一の正本に）
     - README_JA/EN・NOTICE の 1.0.614 → 2.2.0（パッチ番号は VERSION.json 参照と明記）。
     - 使われていない VERSION（1.0.632）と version_info_AZRAS_Planning_Basic.txt を削除。
     - requirements.txt・build bat の版表記（1.0.603）を削除。
     - core/version.py の予備値 1.0.620 → 2.2.0。

  4. EXE ビルドの版情報ファイル
     version_info_AZRAS_Planning.txt が 1行の文字列だったため、PyInstaller が
     eval できず、build_AZRAS_Planning.bat は EXE を作れない状態だった（再現確認済み）。
     → build_tools/make_version_info.py が VERSION.json から VSVersionInfo 形式で生成。
       ビルド bat が PyInstaller の直前に毎回再生成する。
       EXE のファイルバージョン = 2.2.0.48（版＋パッチ番号）。

  5. 監査の過程で見つけた EXE 版の不具合（同じビルド関連ファイルのため同梱）
     a. EXE が画面に誤った版を表示：core/version.py は EXE の隣の VERSION.json を
        探していたが、PyInstaller 6 は _internal フォルダに入れる。
        → _internal（sys._MEIPASS）も探す。
     b. .spec が resources/ と module1/*.json・*.md を同梱していなかった。
        EXE 版の AI 依頼ZIPから プロトコル・スキーマ・テンプレートが
        黙って抜けていた（存在確認で飛ばしていたためエラーにならない）。→ 同梱に追加。

変更していないもの:
  - 計算・数量・画面動作・保存形式。

今後のパッチ作業での注意:
  - パッチごとに VERSION.json の patch を上げたら
    python build_tools/make_version_info.py を実行する
    （忘れると version_consistency_self_check が NG で知らせる）。

  6. 日本語の定点観測プロトコルが AI に一度も送られていなかった
     AI依頼ZIP作成で「AZRAS_AI定点観測プロトコル_v1.1_JP.md」という存在しない名前で
     探していた（実ファイルは AZRAS_AI_Longitudinal_Observation_Protocol_v1.1_JP.md）。
     存在確認で黙って飛ばしていたため、エラーも出なかった。→ 名前を修正し、日英両方を送付。
     また日本語版にだけ「R1フォルダーの送付ルール」「回答形式のハードゲート」の2節があり、
     実際に送られていた英語版には無かった。→ 英語版に同じ2節を追加し、内容を一致させた。
     新規 ai_request_package_resources_self_check：ZIPに入れる予定の全ファイルが実在し、
     日英プロトコルの節構成が一致することを検査（修正前のコードでは NG を確認）。
     ※ 依頼ZIPの内容が変わるため、今後の依頼ZIPのハッシュは PATCH_047 以前と異なる。

  7. 古い APPLY_LOCATION.txt（PATCH 573 の手順書）を削除。


追加（再発行時）: ライセンスを MIT License に統一
  AZRAS-System リポジトリのルート LICENSE（MIT License、著作権者 株式会社ACE総合コンサル）と、
  製品内 LICENSE.txt（独自の許諾文）が食い違っていた。
  → LICENSE.txt を MIT License 全文＋日本語の参考訳（英文が優先）に差し替え。
  → 新規 dev_checks/license_consistency_self_check.py：LICENSE.txt が MIT 全文であることを検査。
  → 画面の「ライセンス」表示（core/branding.py）も同じ MIT 文面に変更し、LICENSE.txt と完全一致することを検査。


追加（再発行時）: 実案件の発注者名・案件名を公開前に除去
  ソース公開（GitHub／Zenodo は削除不可）に備え、実案件3件の名前を「実案件A・B・C」に置換。
  - services/legend_equipment_recognition_v9_2_4.py：コメント内の案件名 → real project A / B
  - PATCH/archive_pre_v2.2.0/PATCH_623_README.txt：案件名 → real projects A, B and C
  - module1/app.py：衛生器具リスト（P-02）の機器欄の区切りに、1社の社名が直書きされていた
    → 表題欄の「… ENGINEERING」という大文字の社名行なら社名を問わず区切る一般規則に変更
      （_TITLE_BLOCK_ENGINEERING_COMPANY_RE）。旧規則と区切り位置が同一になることを確認。
  - 新規 dev_checks/title_block_company_rule_self_check.py（架空の社名だけで検査。
    修正前のコードでは NG を確認）。
  図面・数量データそのものはリポジトリに含まれていない。


追加（再発行時）: Project JSON スキーマを保存形式（3.0）に一致
  data/project_schema_v2_0.json は schema_version を "2.0" に固定しており、
  v2.2.0 が保存する schema_version "3.0" の Project JSON はすべて不合格になっていた
  （サンプル18件・新規Projectで確認。不一致はこの1項目のみ）。
  → data/project_schema_v3_0.json を追加（構造は同一、schema_version "3.0"）。
    v2_0 は旧形式ファイル用として残す。
  → 新規 dev_checks/project_schema_consistency_self_check.py：スキーマの版と
    core/project_store.SCHEMA_VERSION の一致、新規 Project の検証（jsonschema があれば完全検証）。

確認:
  - 新規6本・既存24本、計30本の dev_checks すべて PASS。
  - 新しい重複キー検査は修正前の app.py で NG（2件）、修正後 PASS。
  - pyflakes 検査は「未導入」「構文エラーのファイルあり」の両方で NG になることを確認。
  - 生成した version_info を PyInstaller 6.22 の読込関数で読み込み、
    リソースのバイナリ化まで成功。旧ファイルは同じ関数で失敗することを確認。
  - GUI起動スモーク PASS（タイトル「AZRAS Planning Version 2.2.0」）。
  - pyflakes 警告数は修正前後で同数（未定義名ゼロ）。
  - Windows 上での実ビルドはこの環境では未実施。
