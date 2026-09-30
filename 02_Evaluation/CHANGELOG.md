# AZRAS Evaluation v2.2.0 — PATCH_014 (CSV language)

- Result CSVs follow the UI language at save time. English output unchanged; Japanese output has Japanese headers (`lang/csv_ja.json`) and Japanese action / component / scope / category / semantics values (same labels as the screens); numbers untouched.
- `core/csv_export.py` extended (same file as 01 Planning). Module 3 timeline, Module 4 annual/event, Module 6 cash flow, Module 7 event costs.
- Added `dev_checks/csv_language_self_check.py`. No calculation or Project JSON change.

# AZRAS Evaluation v2.2.0 — PATCH_013 (four-product audit: requirements.txt)

- Added `requirements.txt` (numpy, pandas, reportlab; pyflakes/jsonschema for dev_checks only). On a fresh Python `main.py` stopped with `ModuleNotFoundError: reportlab`; there was no requirements file. 00 Installer PATCH_004 reads it and shows the missing packages and the pip command.
- `build_AZRAS_Evaluation.bat` names the requirements file when build dependencies are missing.
- Added `dev_checks/language_combobox_liveness_self_check.py` (the four-product check; passes). No calculation change.

# AZRAS Evaluation v2.2.0 — PATCH_012 (export file names)

- Fixed: Module 6 「キャッシュフローCSV保存」 proposed `Module6_修繕更新解体積算_イベント別.csv` — the same name Module 7 uses, so the files overwrote each other.
- Module 6 cash flow → `Module6_投資評価_キャッシュフロー.csv`; Module 7 event costs → `Module7_改修更新解体費_イベント別.csv`.
- `MODULE_EXPORT_NAMES` 6/7 updated to the current screen names. New `dev_checks/export_filename_self_check.py`. No calculation or CSV-content change.

# AZRAS Evaluation v2.2.0 — PATCH_011 (Module 4 annual CSV export fix)

- Fixed: 「年別結果CSV保存」 (Module 4) crashed with `ValueError: dict contains fields not in fieldnames: 'climate_temperature_offset_C', 'operational_change_factor', 'climate_energy_factor'`.
- Cause: the CSV header came from the first row (year 0 = initial construction), which lacked the three climate columns present in every yearly row.
- The year-0 row now includes the three columns; the three columns are written to the annual CSV.
- New `core/csv_export.py`: result CSVs use the union of all row keys (old saved Project JSONs also export). Applied to Module 4 annual/event, Module 6 cashflow, Module 7 event costs.
- New `dev_checks/csv_export_fieldnames_self_check.py`. No calculated value changes.

# AZRAS Evaluation v2.2.0 — PATCH_010 (v2.2.0 baseline release)

- Version single source of truth (VERSION.json): NOTICE, FINAL_RELEASE_STATUS, ROOT_MANIFEST, README and the build guide state 2.2.0; patch is a JSON number.
- version_info_AZRAS_Evaluation.txt is generated from VERSION.json as a VSVersionInfo (the old one-line text stopped the PyInstaller build).
- Added dev_checks: version_consistency, duplicate_dict_key, pyflakes_undefined_names. Removed obsolete APPLY_LOCATION.txt / APPLY_PATCH_154.txt.
- PATCH_009 market-rent contract confirmed against 03 Compare PATCH_007. No calculation change.
- Entries below are the pre-v2.2.0 history.

# AZRAS Evaluation v1.0.209 — PATCH 209

- Persisted `cumulative_discounted_unlevered_cash_flow_ex_terminal` in Module 6.
- This makes the present-value holding-period recovery timeline an Evaluation-owned saved result.
- 03 Compare must read this saved series and must not recalculate Evaluation cash flow.

# AZRAS Evaluation v1.0.208 — PATCH 208

- Enforced `Planning → Evaluation → Compare` responsibility boundary.
- Evaluation now consumes only `module_outputs.module1.quantity_takeoff.rows` for Planning quantities.
- Removed fallback reconstruction from `ai_takeoff_import_payload.takeoff_items`.
- Removed raw AI/provider facade fallback from Evaluation calculation input.
- Removed retired `accepted_feasibility_adjustment` from active calculations and Project migration.
- Removed obsolete Feasibility A4 adjustment row from LCA crosswalk.
- Removed retired Module 8 and future Module 9 from active dependency/recalculation paths.
- Synchronized Evaluation scope metadata with the actual four-screen UI.
- Removed obsolete Feasibility/Disaster/Module8 runtime files from the clean release.
- Removed Python cache artifacts from the release.
- Re-ran current self-checks and regression checks.

## v1.0.206 / PATCH 206
- Fixed startup `ModuleNotFoundError: services.envelope_insulation_model_v1` present in v1.0.205.
- Restored the missing shared envelope-insulation runtime module required by `services/environment_engine_v9_1.py`.
- No Evaluation formulas or saved-result semantics changed.

## v1.0.204 / PATCH 204
- Restored the dedicated 「修繕・更新・解体シナリオ」 (Module 3) screen to the Evaluation top menu.
- Reconnected the existing Module 3 scenario engine and Project JSON save flow; no scenario calculation logic was rewritten.
- Evaluation top menu now exposes the full workflow: 200年環境 → 修繕・更新・解体シナリオ → 改修・更新・解体費 → 200年事業.
- Preserved PATCH 203 Module 7 restoration and existing 200-year Environment / Business logic unchanged.
- Added explicit top-screen guidance that Module 3 lifecycle events feed Module 7 cost calculation, and saved Module 7 results feed 200-year Business.

## v1.0.203 / PATCH 203
- Restored the dedicated 「改修・更新・解体費」 screen to the Evaluation top menu.
- Reconnected the existing Module 7 UI to its existing repair/renewal/demolition calculation engine and Project JSON save flow.
- Existing 200-year Environment and 200-year Business functions are unchanged.
- Fixed the restored Module 7 window numbering from 6 to 7.
- Removed the incorrect top-screen notice stating that renewal costs had no independent screen.

## v1.0.202 / PATCH 202
- Evaluation now accepts Planning 535 method-specific timber totals and RC internal-partition LGS steel.
- RC method cost allow-list permits the explicit permanent LGS steel total.
- Long-term environment fallback recognizes the new timber/LGS labels.
- Audit-only component breakdowns remain excluded from downstream ownership.

## v1.0.201 — 2026-09-06
- Aligned Evaluation Module 4/5 quantity bridge with Planning PATCH 534.
- Audit/superseded ownership now has absolute precedence over legacy provisional compatibility, preventing historical rows from re-entering CO2/cost calculations.
- Added direct mapping for yellow 2x6/AZRAS structural-timber planning quantities and corrected English opening rows.
- Rational provisional quantities remain eligible even when human confirmation is still recommended.
- Regression against normalized 260906 samples: 2x6 = 0.9804 t rebar / 14.706 m3 timber / 55.74 m2 glass / 6.33 m2 doors; AZRAS = 8.4159 t / 14.706 m3 / 55.74 m2 / 6.33 m2; RC = 15.530288 t / 55.74 m2 / 6.33 m2.


## v1.0.200 / PATCH 200
- Aligned Evaluation quantity eligibility with Planning Basic PATCH 532.
- Clearly labelled rational provisional/general-specification numeric quantities remain usable as yellow planning inputs even in legacy Project JSONs with stale red/block flags.
- Genuine red/unknown/conflict/spec/audit rows remain excluded.
# CHANGELOG

## v1.0.161 PATCH 161 — 2026-08-16
- 04 Feasibility adjustment receiverを追加。
- CO₂ / cost / scheduleを個別に明示採用可能。
- accepted_feasibility_adjustmentをProject JSON commonへ保存。
- Module 4へ追加CO₂、Module 5へ追加費・追加工期を反映。
- LCA crosswalkにA4/site logistics adjustmentを追加。
- 読込のみでは反映しない。工法ID不一致は拒否。

## v1.0.160 PATCH 160 — 2026-08-16
- Module 4へ既存LCA結果のA1-A5 / B / C / D説明用クロスウォークを追加。
- 初期建設=A1-A5集約、更新=B4-B5 proxy、運用=B6、解体・廃棄=C1-C4集約、再使用/リサイクルCO₂クレジット=Dとして表示。
- A1/A2/A3/A4/A5等の未算定内訳を作らず、集約値であることを明記。
- Module 4既存計算式・原単位・200年結果は変更していない。

## v1.0.159 PATCH 159 — 2026-08-16
- Module 6へ割引率2/3/4/5/6%＋現在入力率の自動感度分析を追加。
- 50/100/150/200年NPVと各期間末terminal valueを再計算。
- 割引率以外の条件は固定。
- 従来の主計算NPV・IRR・CFは変更していない。

## v1.0.158 PATCH 158 — 2026-08-16
- Module 4に電力CO₂低減率の低位・標準・高位・任意シナリオを追加。
- 低位=-0.25%/年、標準=-0.50%/年、高位=-1.00%/年。
- 標準は従来の-0.5%/年と互換。
- scenario_keyと実使用年率をProject JSONへ保存。
- 将来気候8760時間感度と電力グリッド脱炭素を独立変数として維持。
- PATCH 157/014の将来気候入力snapshot保存も横断確認して補完。
- 資材LCA・更新解体イベント・事業性計算は変更していない。

## v1.0.157 PATCH 157 — 2026-08-16
- Module 4へ将来気候8760時間温度感度を追加。
- Module 2で使用した同一EPW/CSVを、指定温度差でマイルストーン年ごとに8760時間再計算。
- 100年後・200年後の温度差、再計算間隔をProject JSONへ保存。
- 中間年は8760再計算済み年間エネルギー係数を補間し、200年CO₂・エネルギー系列へ反映。
- 従来の現在気候計算は既定値として維持し、既存結果を変更しない。
- grid CO₂低減、operational_change、更新・解体LCAロジックは維持。

## 1.0.156 / PATCH 156
- `version_info_AZRAS_Evaluation.txt` のWindows EXE版数を 1.0.156 へ更新。
- `core/version.py` の `DEFAULT_VERSION` を 1.0.156 へ更新。
- `ROOT_MANIFEST.txt` / `FINAL_RELEASE_STATUS.txt` を現行PATCHへ更新。
- 過去の「PATCH 153がfinal」という固定宣言を撤回し、現行監査状態を記録する文書へ変更。
- `module1/` は compatibility hold として維持。
- Core Project JSON Schema 3.0、計算式、Module 3〜7接続は変更していない。

## 1.0.155 / PATCH 155
- PATCH 154適用後の配布メタデータを整理。
- VERSION.json / README_JA.txt / APPLY_LOCATION.txt の現在Version・PATCH番号を統一。
- NOTICE.txt の旧 v3.4.0 表記を現行 v1.0.155 へ修正。
- PATCH 154のModule 6/7接続修正、計算式、Project JSON構造は変更なし。

## 1.0.154 / PATCH 154
- Removed retired internal `module8` from current Evaluation dependency propagation.
- Prevented false `module_status.module8 = recalculation_pending` after Module 6/7 saves.
- Final operation check no longer treats legacy internal Module 8 as an active Evaluation module.
- Existing real legacy Module 8 output is preserved for backward compatibility.

# CHANGELOG
## v1.0.153 PATCH 153 — 2026-08-14
- 個別SELF CHECK 5系統を full_self_check.py に完全統合。
- ルートの自己診断ファイルを FULL_SELF_CHECK.bat / full_self_check.py の2つに集約。
- GUI_FINAL_CHECKLIST.txt と FINAL_BASELINE.txt を開発完了後の不要資料として削除対象化。
- ROOT_MANIFEST.txt を最終クリーン構成へ更新。
- Version情報を 1.0.153 に統一。
- 計算式、Project JSON構造、Module接続仕様は変更なし。

## v1.0.152 PATCH 152 — 2026-08-14
- 03_AZRAS_Evaluation 本体整理・安定化作業を完了。
- PATCH 151までのFULL_SELF_CHECK PASSEDを最終基準として継承。
- Windows実機GUI確認で特に問題なしとの確認結果を最終状態として記録。
- FINAL_RELEASE_STATUS.txt を追加。
- Version情報を 1.0.152 に統一。
- 計算式、Project JSON構造、Module接続仕様は変更なし。
- 今後は確認済み不具合または新機能要求がある場合のみ新PATCHを作成する。

## v1.0.151 PATCH 151 — 2026-08-14
- Module 3〜7が起動時に参照する必須dataファイルの存在確認を追加。
- MODULE_RESOURCE_SELF_CHECKを追加。
- FULL_SELF_CHECKを5段階へ拡張。
- Version情報を 1.0.151 に統一。
- GUI実装、計算式、Project JSON、Module接続仕様は変更なし。

## v1.0.150 PATCH 150 — 2026-08-14
- main.pyのModule起動引数とModule 3〜7の__init__インターフェース一致を自動確認。
- Tkinterの第1引数名 master / parent の双方を正常なUI親引数として扱う。
- MODULE_CONSTRUCTOR_SELF_CHECKを追加。
- FULL_SELF_CHECKを4段階へ拡張。
- Version情報を 1.0.150 に統一。
- GUI実装、計算式、Project JSON、Module接続仕様は変更なし。

## v1.0.149 PATCH 149 — 2026-08-14
- 自動SELF CHECKでは確認できないGUI動作の最終確認手順を追加。
- GUI_FINAL_CHECKLIST.txt にメイン画面、Project選択、Module 3/4/5/7/6起動、About/License確認を固定。
- Version情報を 1.0.149 に統一。
- GUI実装、計算式、Project JSON、Module接続仕様は変更なし。

## v1.0.148 PATCH 148 — 2026-08-14
- main.py のModule 3〜7画面入口を静的検証するGUI_WIRING_SELF_CHECKを追加。
- Project JSON選択、未選択時保護、load_project、open_module接続を確認。
- FULL_SELF_CHECKを3段階確認へ拡張。
- Version情報を 1.0.148 に統一。
- GUI実装、計算式、Project JSON、Module接続仕様そのものは変更なし。

## v1.0.147 PATCH 147 — 2026-08-14
- SELF_CHECK と PROJECT_JSON_SELF_CHECK を一括実行する FULL_SELF_CHECK を追加。
- 起動依存・Version/schema・必須resource・Project JSON round-tripを1回で確認可能にした。
- FULL_SELF_CHECK.bat / full_self_check.py を追加。
- Version情報を 1.0.147 に統一。
- 計算式、実Project JSON、Module接続仕様は変更なし。

## v1.0.146 PATCH 146 — 2026-08-14
- Project JSONの非破壊round-trip自己診断を追加。
- new_project → 一時保存 → load_project → module1〜9キー/schema 3.0/JSON妥当性を確認。
- PROJECT_JSON_SELF_CHECK.bat / project_json_self_check.py を追加。
- Version情報を 1.0.146 に統一。
- 実Project JSON、計算式、Module接続仕様は変更なし。

## v1.0.145 PATCH 145 — 2026-08-14
- PATCH 144整理後の最終ルート構成を監査し、必須欠落0件・旧PATCH残存0件・構文エラー0件を確認。
- SELF_CHECKのVersion比較前に core.version をreloadし、連続検証時の古いメモリ値による誤判定を防止。
- FINAL_BASELINE.txt を追加し、ファイル整理・Version整理・静的起動確認フェーズの完了基準を記録。
- Version情報を 1.0.145 に統一。
- 計算式、Project JSON、Module接続仕様は変更なし。

## v1.0.144 PATCH 144 — 2026-08-14
- PATCH ZIP内ファイルの更新日時をJSTで記録する作成方式へ変更。
- PATCH_143_APPLYで残った旧APPLY BAT対策として、明示的なdel /F /Q方式へ変更。
- PATCH 115/125/126/141/143 の旧適用BATを確実に削除。
- 監査・整理資料は docs/maintenance、旧PATCH資料は docs/history へ整理。
- Version情報を 1.0.144 に統一。
- 本体コード、計算式、Project JSON、Module接続仕様は変更なし。

## v1.0.143 PATCH 143 — 2026-08-14
- ルート直下に残っていた旧PATCH用BAT・監査資料・整理資料を一括整理。
- 監査/保守資料は docs/maintenance、旧PATCH資料は docs/history へ移動。
- PATCH 115/125/126/141 の一時適用BATを削除。
- Pythonキャッシュと誤階層PATCH_119/PATCH_121が残っていれば削除。
- ROOT_MANIFEST.txt を追加し、今後ルートに残すファイルを明確化。
- Version情報を 1.0.143 に統一。
- 本体コード、計算式、Project JSON、Module接続仕様は変更なし。

## v1.0.142 PATCH 142 — 2026-08-14
- PATCH 141適用後の配布ルート構成をシミュレーション確認。
- 必須ファイル・フォルダ欠落0件、Python構文エラー0件、SELF CHECK PASSEDを確認。
- DISTRIBUTION_LAYOUT_AUDIT.txt を追加。
- module1は現行Evaluation起動系外だが、01/02との所有境界確定までは保持。
- Version情報を 1.0.142 に統一。
- 計算式、Project JSON、Module接続仕様は変更なし。

## v1.0.141 PATCH 141 — 2026-08-14
- ルート直下の保守資料を docs/maintenance へ整理する適用BATを追加。
- PATCH_108_README.txt は削除せず docs/history へ移動。
- ROOT_LAYOUT_AFTER_PATCH141.txt を追加し、現行ルート構成を明示。
- Version情報を 1.0.141 に統一。
- Pythonコード、計算式、Project JSON、Module接続仕様は変更なし。

## v1.0.140 PATCH 140 — 2026-08-13
- SELF_CHECKにVersion整合チェックを追加。
- VERSION.json / core.version / core.project_store のschema一致を自動確認。
- SCHEMA_VERSION_MAP.txt の現行Version表記を更新。
- Version情報を 1.0.140 に統一。
- 計算式、Project JSONデータ構造、Module接続仕様は変更なし。

## v1.0.139 PATCH 139 — 2026-08-13
- GUIを起動せず main / Module 3〜7 / Project Core をimport確認する self_check.py を追加。
- Windows用 SELF_CHECK.bat と実行ガイドを追加。
- 必須lang/data/VERSIONファイルの存在確認を追加。
- Version情報を 1.0.139 に統一。
- 計算式、Project JSON、Module接続仕様は変更なし。

## v1.0.138 PATCH 138 — 2026-08-13
- main.pyから到達するModule 3〜7の外部Python依存を監査。
- 必須依存を PyInstaller / numpy / pandas / reportlab と確定。
- build_AZRAS_Evaluation.bat に依存ライブラリ事前確認を追加。
- BUILD_REQUIREMENTS.txt を追加。
- Version情報を 1.0.138 に統一。
- 計算式、Project JSON、Module接続仕様は変更なし。

## v1.0.137 PATCH 137 — 2026-08-13
- PyInstaller hidden importを監査。
- ソース内にPIL依存が存在しないため AZRAS_Evaluation.spec の hiddenimports=['PIL'] を削除。
- 不要なPillow依存によるEXEビルド失敗リスクを除去。
- Version情報を 1.0.137 に統一。
- 計算式、Project JSON、Module接続仕様は変更なし。

## v1.0.136 PATCH 136 — 2026-08-13
- PyInstaller EXE時のVERSION.json参照先を監査。
- core/version.py のfrozen時rootを sys.executable.parent から sys._MEIPASS 優先へ修正。
- EXE_RESOURCE_AUDIT.txt を追加。
- Version情報を 1.0.136 に統一。
- 計算式、Project JSON、Module 3〜7、03_AZRAS_Evaluation_2 接続仕様は変更なし。

## v1.0.135 PATCH 135 — 2026-08-13
- Module 3〜7 のProject JSON読込・保存・自動伝播経路を監査。
- PROJECT_JSON_FLOW_AUDIT.txt を追加。
- module_outputsの保存キーと依存グラフに接続切れがないことを確認。
- 推奨手動順序 Module 3→4→5→7→6 が現行依存グラフと両立することを確認。
- Version情報を 1.0.135 に統一。
- 計算式、Project JSONデータ構造、Module接続仕様は変更なし。

## v1.0.134 PATCH 134 — 2026-08-13
- main.py / Module 3〜7 からのservice依存グラフを監査。
- SERVICE_DEPENDENCY_MAP.txt を追加し、runtime必須service 11件を明示。
- 現行起動グラフ外のservice 8件は01/02・Evaluation_2等との境界確認前には削除しない方針を固定。
- Version情報を 1.0.134 に統一。
- 計算式、Project JSON、Module接続仕様は変更なし。

## v1.0.133 PATCH 133 — 2026-08-13
- shared UI依存関係を監査し、UI_DEPENDENCY_AUDIT.txt を追加。
- ui/__init__.py の副作用により ui/global_treeview.py が間接runtime依存であることを正式に記録。
- ui/__init__.py の旧「AZRAS Platform」表記を「AZRAS Evaluation」へ修正（動作変更なし）。
- Version情報を 1.0.133 に統一。
- 計算式、Project JSON、Module 3〜7、03_AZRAS_Evaluation_2 接続仕様は変更なし。

## v1.0.132 PATCH 132 — 2026-08-13
- Module 3〜7 の例外処理を監査し、EXCEPTION_HANDLING_AUDIT.txt を追加。
- 保存結果の再描画などに broad exception suppression があることを明示。
- GUI回帰確認なしで機械的に削除すると読込動作を変えるため、今回は挙動を変更せず保護対象化。
- Version情報を 1.0.132 に統一。
- 計算式、Project JSON、Module接続仕様は変更なし。

## v1.0.131 PATCH 131 — 2026-08-13
- アプリVersion、Project JSON schema、旧JSON互換default、各Module sub-schemaの役割を整理。
- SCHEMA_VERSION_MAP.txt を追加し、Version番号の機械的置換によるJSON互換破壊を防止。
- core/project_coordinator.py の schema 2.0 / platform 9.4.0 は旧JSON互換用setdefaultのため変更せず保持。
- Version情報を 1.0.131 に統一。
- 計算式、Project JSONデータ構造、Module 3〜7、03_AZRAS_Evaluation_2 接続仕様は変更なし。

## v1.0.130 PATCH 130 — 2026-08-13
- VERSION.json に product_name / schema_version / executable_name / release_channel を明示。
- 既存 product キーも互換性維持のため保持。
- core/version.py の schemaフォールバックを、実際のProject JSON保存仕様 core/project_store.py の 3.0 に統一。
- Version情報を 1.0.130 に統一。
- 計算式、Module 3〜7の計算処理、03_AZRAS_Evaluation_2 接続仕様は変更なし。

## v1.0.129 PATCH 129 — 2026-08-13
- core/version.py に残っていた旧フォールバックVersion 4.0.0を現行Versionへ修正。
- EXE名フォールバック「AZRAS_Platform_Core」を「AZRAS_Evaluation」へ修正。
- schema_version 4.0 はProject JSON互換性保護のため変更せず保持。
- Version情報を 1.0.129 に統一。
- 計算式、Project JSON、Module 3〜7、03_AZRAS_Evaluation_2 接続仕様は変更なし。

## v1.0.128 PATCH 128 — 2026-08-13
- PATCH_108_README.txt を履歴資料として明示し、現行手順との混同を防止。
- CURRENT_BUILD_GUIDE.txt を追加し、現行の起動・EXEビルド・Version管理ファイルを明示。
- Version情報を 1.0.128 に統一。
- 計算式、Project JSON、Module 3〜7、03_AZRAS_Evaluation_2 接続仕様は変更なし。

## v1.0.127 PATCH 127 — 2026-08-13
- LICENSE.txt / NOTICE.txt に残っていた旧製品名「AZRAS Platform Core」を「AZRAS Evaluation」へ統一。
- core/version.py と日本語・英語言語ファイルの旧製品名も同時に統一。
- Version情報を 1.0.127 に統一。
- 法務条件、計算式、Project JSON、Module 3〜7、03_AZRAS_Evaluation_2 接続仕様は変更なし。

## v1.0.34 PATCH 034 — 2026-08-08
- AZRASだけの実績総額置換を廃止。
- AZRAS・2×6・RCラーメンの全工法に同一の2004年価格基準を適用。
- 2004→評価年上昇係数（初期値1.60）と共通市場校正係数（初期値0.5630355）を全工法へ同一適用。
- 高島2号34,500,000円（税別）は共通市場水準の校正基準として使用。
- 工法差は数量・施工歩掛り・工種構成で表現。
- JSONに common_price_basis を保存。
## v1.0.197 — 2026-09-06
- Corrected Module 4 material-quantity ownership. Official Evaluation order is Module 3 -> Module 4 -> Module 5, so an old saved Module 5 breakdown can no longer override current Module 1 quantities.
- Module 4 now rebuilds method-screened LCA quantities from current Module 1 through the canonical physical-quantity bridge and records saved Module 5 only as a mismatch audit.
- Added concrete physical-component de-duplication and reinforcement planning-row preservation to Evaluation's quantity bridge.
- Regression using the three 260906 sample Projects: 2x6 = 12.255 m3 concrete / 1.2255 t rebar; AZRAS = 93.510 m3 / 8.4159 t; RC frame = 129.419064 m3 / 15.53028768 t.
- Recomputed 200-year net lifecycle CO2 with the existing saved Evaluation settings: 2x6 1,226,574.95 kg; AZRAS 1,172,301.38 kg; RC frame 1,255,447.31 kg.
## v1.0.199 — 2026-09-06
- Unified Evaluation quantity adoption with Module 1 display certainty: confirmed and yellow provisional/assumed numeric quantities are included; red/unknown/spec/audit rows are excluded.
- Added stale-Project compatibility so an explicitly yellow quantity is not lost solely because an older saved downstream flag says blocked.
- Added prominent warnings to Module 4 CO2/LCA, Module 5 construction cost, and Module 6 business-plan result areas. The warning states that yellow quantities are included, red/unquantified items are omitted, and human additions require recalculation before final judgment.
- Corrected Module 4 result-grid placement so the new warning does not overlap the summary table.

