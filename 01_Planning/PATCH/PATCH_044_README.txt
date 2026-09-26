PATCH_044 — 260923 UTC — v2.2.0
========================================

対象ファイル:
  - module1/app.py
  - dev_checks/patch_044_unified_human_correction_self_check.py（新規）

要望内容:
  Module 1 の概略数量／詳細数量表で明らかにおかしい行をダブルクリックした時、
  従来の「数量だけの入力」→「暫定一般仕様の別画面」という分断をやめる。
  ダブルクリックした行を人間修正一覧へ追加し、さらに別の行をダブルクリック
  すると同じ一覧へ追加する。数量・算定根拠・参照元（指示者名）を同じ画面で
  承認し、Module 1 表へ戻す。従来の表①の未確定数量／図面矛盾も同じ画面へ
  統合する。

対応:
  1. 「表① 未確定数量・人手確認」を「人間修正・確認（表①）」へ改称。
     表①は独立した隠し表ではなく、この統合画面そのものとした。
  2. 概略数量／詳細数量の任意の編集可能行をダブルクリックすると、
     manual_review_selected_by_user として人間修正キューへ追加し、統合画面を開く。
     統合画面が既に開いている場合は新しい画面を増やさず、その行を同じ一覧へ
     追加・選択する。
  3. 統合画面は左側に複数行の一覧、右側に選択行の編集欄を配置。
       ・承認数量
       ・単位
       ・承認する算定根拠
       ・参照元／指示者名
       ・備考
     を一度に入力できる。
  4. 暫定一般仕様行では、従来の「暫定仕様・材料」「原単位／ピッチ／断熱厚」
     も同じ右側編集欄へ表示する。従来の条件から数量を再計算する機能も
     「条件から数量再計算」として残した。
  5. 承認時は Module 1 の行へ以下を正式反映する。
       数量       -> accepted_quantity / display_quantity
       算定根拠   -> evidence / formula / human_approved_calculation_basis
       参照元     -> source_mode / human_instruction_by / decision_maker
     status/evidence_status は confirmed、downstream_use は
     allowed_manual_confirmed とし、Project JSONへ保存可能。
  6. 0 m3 のような「存在しないことを人間が承認した数量」も有効な決定として
     概略数量表から消さない。基礎下断熱材=0 m3 のケースを想定。
  7. 「人間修正を解除」で数量・単位だけでなく、元の算定根拠・参照元・
     暫定仕様も復元する。

既存機能との関係:
  - 「不明・矛盾を画面で回答」の HUMAN_REVIEW_FINAL 系処理は変更していない。
    正式な設計条件回答による再計算経路を壊さない。
  - HUMAN_REVIEW_FINAL 反映済みの行は従来どおり直接上書きせず、正式回答の
    再取込を要求する。
  - 集計行（editable=False）は従来どおり直接修正不可。
  - PATCH_043までのPATCHフォルダーは削除・上書きしていない。

回帰確認:
  - Python全ソースcompile: PASS
  - dev_checks既存self-check: PASS
  - PATCH_044追加self-check: PASS
