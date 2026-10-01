PATCH_053 — 261001 UTC — v2.2.0（Module 5 代表地域プロファイル：手動選択の保持／最寄り都市の自動選択／プロファイル追加）
========================================

対象ファイル:
  - services/regional_profile_catalog.py（新規・tkinter 非依存）
  - services/construction_cost_engine_v9_4.py（resolve_location_profile_from_project に最寄り都市判定を追加）
  - module5/app.py（手動選択の保持、「自動選択に戻す」「地域プロファイル追加」ボタン、警告文）
  - core/project_coordinator.py / module2/app.py（同じプロファイル一覧を読む）
  - data/construction_cost_database_v9_4.json（標準16都市に緯度経度を追加。指数・単価は変更なし）
  - data/regional_profiles/README.txt（新規フォルダー）
  - dev_checks/patch_053_regional_profile_selection_self_check.py（新規）
  - VERSION.json / version_info_AZRAS_Planning.txt（自動生成）/ CHANGELOG.md

要望内容（案件所在地：2-18-7 Matsukawadomachi, Kasugai-shi, Aichi-ken）:
  1. 代表地域プロファイルで名古屋を手動選択しても、その場で東京に戻り「地域条件を適用」に進めない。
  2. 自動選択は、プロファイル都市の緯度経度を使って同じ国の中で最も近い都市を選ぶ。
  3. プルダウンにある都市以外も、データがあれば利用できるようにする。

原因:
  1. Module 5 のウィンドウ全体に <FocusIn> → refresh_project_from_context が結び付いており、
     Module 5 が未保存の間は、フォーカスが戻るたびに _apply_project_location_initial_profile が
     自動選択（東京）と東京の指数を毎回上書きしていた。プルダウンを閉じた瞬間・ボタンを押した瞬間にも
     発生するため、名古屋を選んでも東京に戻った。手入力した資材・労務・生産性指数も同じ理由で戻っていた。
  2. 自動選択は都市名の一致と日本語の県名（愛知県など）しか見ておらず、ローマ字住所
     「Kasugai-shi, Aichi-ken」はどれにも一致しないため、国の基準都市（東京）になっていた。
  3. 一覧は内蔵データベースの固定リストだった。

対応:
  1. 手動選択の保持
     ・プルダウンで選んだプロファイルは「手動」として保持し、FocusIn・再計算・保存のどれでも上書きしない。
     ・Module 5 保存時に location_selection_mode（auto / manual）を記録。
     ・新ボタン「自動選択に戻す」で自動選択に戻せる。
     ・自動のときも、プロジェクトまたは所在地（国・住所・緯度経度）が変わったときだけ再適用する
       （手入力した指数がフォーカス移動で戻らない）。
  2. 最寄り都市の自動選択
     ・Module 0 の緯度経度（common.latitude / longitude）から各プロファイル都市までの距離を計算し、
       同じ国の中で最も近い都市を選ぶ。春日井 → Japan / Nagoya（約12km）。
     ・100km以内は「近隣プロファイル Japan / Nagoya を自動選択（所在地から約12km）」と表示し、
       地域単価表への登録も確認なしで進める。
     ・100kmを超える場合、または案件国のプロファイルが無く国外の最寄り都市を選んだ場合は、
       距離と注意文を表示する（「地域プロファイル追加」を案内）。
     ・都市名が一致した場合は従来どおり都市一致を優先。緯度経度が無い場合は従来の判定に加え、
       ローマ字の県名（Aichi など、単語単位で判定）でも名古屋等に対応。
  3. プロファイル一覧の動的生成と追加
     ・一覧 = 内蔵プロファイル + data/regional_profiles/*.json（利用者追加）
       + data/regional_cost/*.json のうち region_key が新しい都市で、通貨と regional_indices を持つもの。
     ・新ボタン「地域プロファイル追加」：国・都市・緯度・経度・通貨・単価年度・3指数・根拠メモを入力して保存。
       初期値は現在画面の値と案件の緯度経度。保存後は一覧に表示され、最寄り判定にも使われる。
       内蔵プロファイル名は上書き不可。
     ・Module 5 の自動再計算（core/project_coordinator.py）と Module 2 も同じ一覧を読むため、
       追加プロファイルで保存した案件も再計算できる。

変更していないもの:
  - 各都市の資材・労務・生産性指数、単価、通貨（緯度経度を追加しただけ）。
  - 東京などを選んだときの建設費計算結果。
  - 保存済み Module 5 のプロファイル（保存済みの選択が優先。古い案件は手動扱い）。
  - 地域単価表（PATCH_052）、AI概算単価①〜⑥の手順。

確認方法（画面）:
  1. 春日井の案件で Module 5 を開く → 代表地域プロファイルが Japan / Nagoya、
     「近隣プロファイル … 約12km」と表示される。
  2. Japan / Tokyo を選ぶ → 他の欄をクリックしても東京のまま。「自動選択に戻す」で名古屋に戻る。
  3. 「地域プロファイル追加」で都市を追加 → 一覧に表示され、選択される。
