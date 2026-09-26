PATCH_008 — 260922 UTC — v2.2.0
========================================

対象ファイル:
  - core/project_store.py
  - core/project_coordinator.py
  - dev_checks/patch_008_comparison_copy_guard_self_check.py（新規）

要望内容:
  03 Compare が作る比較用コピーでは、Module 6・7 だけを再計算し、
  それ以外は元Projectと同一に保つ。

対応:
  comparison_copy マーカー（AZRAS_COMPARISON_COPY_V1、01 Planning
  PATCH_043 と同一）を持つProjectでは、update_module_and_propagate が
  Module 3・4 の保存を拒否し、理由を表示する。Module 6・7 は従来どおり。
  マーカーの無い通常Projectの挙動は一切変わらない。

  Module 3/4 を止める理由は、これらが図面・数量・エネルギーという
  「コピーでは変えてはいけない入力」だけから決まるためで、コピーで
  作り直すと同じ建物の比較ではなくなる。数量の修正は元Projectで行い、
  03 Compare でコピーを作り直す運用とする。

回帰確認:
  - dev_checks/既存10本: 全てPASS
  - PATCH_008追加self-check: PASS（12項目）
  - pyflakes: 修正前後で警告が完全一致（差分0行）
