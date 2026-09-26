PATCH_042 — 260921 UTC — v2.2.0
========================================

対象ファイル:
  - services/construction_cost_engine_v9_4.py
  - module5/app.py
  - dev_checks/patch_042_japanese_address_profile_resolution_self_check.py（新規）

要望内容:
  260918_2_6_Sample / AZRAS_Sample / RC_Rahmen_Sample（いずれも
  愛知県春日井市）の Module 5 代表プロファイルが「Japan / Tokyo」に
  なっていた件を修正する。

原因:
  resolve_location_profile_from_project() には既に
  city_aliases = {"春日井":"nagoya", "名古屋":"nagoya", ...} が登録されて
  いたが、別名は city 欄の「全体」と完全一致した場合にしか引かれて
  いなかった。日本の案件では city 欄に番地まで入った住所
  （"愛知県春日井市松河戸町2-18-7"）が入るのが通常で、別名は一度も
  働いていなかった。その後段の住所フォールバックはローマ字
  ("tokyo","sapporo","nagoya") を日本語住所の中から探すため、これも
  必ず失敗する。結果として3件とも国の基準都市 Tokyo に落ちていた。

  Tokyo と Nagoya の差（本DB）:
                     material  labor  productivity
    Japan / Tokyo      112     118        95
    Japan / Nagoya     105     105       100
  AI概算単価の行は地域係数を通らない（PATCH_462/475）ため直接工事費
  への影響は限定的だが、DB単価で値付けされる行と工期（生産性）に
  影響していた。

対応:
  1. 非ラテン文字の別名を city／住所の「部分文字列」として照合する。
     長い別名から順に試すので、"愛知県名古屋市..." は "名古屋" に、
     "愛知県春日井市..." は "春日井" に一致する。
  2. 別名に無い市町村のために、日本の都道府県フォールバックを追加した。
     登録済みの代表都市があるものだけを列挙し、それ以外は推測しない。
       愛知県・岐阜県・三重県 → Japan / Nagoya
       北海道                 → Japan / Sapporo
       東京都・神奈川県・埼玉県・千葉県 → Japan / Tokyo
     大阪府など代表都市が未登録の府県は、従来どおり
     country_reference_fallback として正直に報告する。
  3. match_level に matched_prefecture を追加し、
     profile_is_regional_match / matched_alias / matched_prefecture を
     返すようにした（既存キーは不変）。
  4. 保存済みの Module 5 は「利用者の選択」として上書きしない
     （PATCH 056 の既存方針を維持）。代わりに、保存済みプロファイルが
     住所から解決されるプロファイルと異なる場合、Module 5 ヘッダーに
     「案件所在地に対応する代表プロファイルは Japan / Nagoya です
     （現在の選択: Japan / Tokyo）」と表示する。
     Project をファイルから開き直した場合は、PATCH 056 の既存処理により
     解決結果（Nagoya）が自動で選ばれる。

検証（実Project 4件）:
    260918_2_6_Sample       Tokyo（fallback） → Nagoya（matched_city, 別名 春日井）
    260918_AZRAS_Sample     Tokyo（fallback） → Nagoya（matched_city, 別名 春日井）
    260918_RC_Rahmen_Sample Tokyo（fallback） → Nagoya（matched_city, 別名 春日井）
    260919_S-Structure      New York（fallback） → 変化なし（PATCH_039どおり）

横断監査:
  - 00 Installer / 02 Evaluation / 03 Compare: 変更なし。
  - resolve_location_profile_from_project() はキー追加のみ。
  - 既存の regional_project_location_self_check は変更なしでPASS。
  - 既存PATCHフォルダーは削除・整理・上書きしていない。

回帰確認:
  - dev_checks/既存19本: 全てPASS
    （azras_scope_leakage_regression のみ本サンドボックスに tkinter が
      無いためImportErrorで停止。修正前のソースでも同一）
  - PATCH_042追加self-check: PASS（20項目）
  - Python compile: PASS
  - pyflakes: 修正前後で警告が完全一致（差分0行）
