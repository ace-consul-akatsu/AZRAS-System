PATCH_004 — 260921 UTC — v2.2.0
========================================

対象ファイル:
  - comparison/extractor.py
  - main.py
  - dev_checks/patch_004_snapshot_staleness_and_currency_self_check.py（新規）

要望内容:
  保存値検証で、Compare が「現在の入力から計算されていない値」を
  最新値として表示していることが判明した。2件を修正する。

────────────────────────────────────────
(1) 古い8760スナップショット・古い評価結果を最新として表示
────────────────────────────────────────
原因:
  Compare はエネルギーを regional_analysis.module10_snapshot から、
  CO2 を Module 4、事業性を Module 6 から読む。いずれも別個に保存
  される成果物で、Module 2（エネルギー）や Module 5（建設費）を
  再計算しても自動では作り直されない。
  既存の _snapshot()（PATCH 044）はパッシブ設定の不一致だけを検査し、
  外皮の不一致は検査していなかった。

  260918_RC_Rahmen_Sample で実際に発生:
    Module 2（9/21 04:15）: light_wall U=0.130 × 82.88m2 = 10.8 W/K
                             年間 16,029.6 kWh
    スナップショット（9/20 08:54）: light_wall U=5.882 × 82.88m2 = 487.5 W/K
                             年間 23,206.9 kWh
    Module 3/4/6/7（9/20 09:05〜09:06）: 修正前の入力で計算
  → Compare は修正前の 23,206.9 kWh / 9.979 t / 1,545.2 t / −122.8M を
    最新値として表示し続けていた。

対応:
  ・snapshot_envelope_mismatches(): スナップショットの model_config と
    Module 2 の floor_thermal_breakdown を、RC外壁・軽量外壁ごとに
    熱貫流（U×A）で比較する。差が max(1 W/K, 2%) を超えたら不一致。
    面積0の部位のU値差（2×6の rc_wall U=5.88×0㎡ 等）は誤検知しない。
    どちらかにデータが無い旧ファイルは検査対象外（従来どおり採用）。
  ・_snapshot(): 不一致なら PATCH 044 と同じくスナップショットを不採用
    とし、Module 2 の年間値へフォールバックする。
  ・stale_downstream_results(): module_status の保存時刻を比較し、
    Module 2 より古い Module 3/4/6/7、Module 5 より古い Module 6/7 を
    列挙する。未計算モジュールは対象外。報告のみで値は変更しない。

────────────────────────────────────────
(2) 通貨を Module 0 の宣言から読んでいた
────────────────────────────────────────
原因:
  extractor が通貨を project_identity.currency から優先して読んでいた。
  260919_S-Structure_Sample は Module 0 の宣言が JPY のまま、
  Module 5/6 は USD で計算されており、$1,226,508 が
  ¥1,226,508 として表示されていた（工場1棟が約120万円に見える）。

対応:
  ・通貨は値を計算した Module 5 → Module 6 → project_identity → common
    の順で解決する。
  ・宣言と計算通貨が異なる場合は currency_conflict として報告する。

────────────────────────────────────────
警告表示
────────────────────────────────────────
  読込直後に「保存データの整合性確認」を1回表示する（該当時のみ）。
    ・スナップショット外皮の不一致（部位・U・面積・熱貫流を両方表示）
    ・入力より古い評価結果（例: Module 2→Module 3, Module 5→Module 6）
    ・通貨の不一致
  既存の「02 Evaluation 未計算確認」「税金取扱いの確認」
  「比較前提の確認」と同じ扱い。英訳あり。

実データ検証（4件のProject JSON、実コード）:
    2×6_Sample          警告なし（誤検知なし）
    AZRAS_Sample        警告なし（誤検知なし）
    RC_Rahmen_Sample    スナップショット不一致（487.5 vs 10.8 W/K）
                        → 年間エネルギー表示 23,206.9 → 16,029.6 kWh
                        古い評価結果6件（M2→M3/M4/M6/M7, M5→M6/M7）
    S-Structure_Sample  通貨 JPY → USD、通貨不一致を報告

横断監査:
  - 本製品は read_only_consumer。Project JSONへの書き込みなし。
  - extractor の返り値はキー追加のみ（currency の解決順のみ変更）。
  - 既存PATCHフォルダーは削除・整理・上書きしていない。

回帰確認:
  - dev_checks/既存3本: PASS
  - PATCH_004追加self-check: PASS（18項目）
  - Python compile: PASS
  - pyflakes: 修正前後で警告が完全一致（差分0行）
