PATCH_004 — 260930 UTC — AZRAS Installer 5.0.4（AZRAS v2.2.0・4製品横断監査の指摘対応）
========================================

対象ファイル:
  - package_check.py（新規・tkinter 非依存）
  - azras_installer.py（パッケージ一覧・「インストール用コマンド」ボタン）
  - docs/AZRAS_Installation_Guide_JA.html / docs/AZRAS_Installation_Guide_EN.html
  - dev_checks/patch_004_python_package_check_self_check.py（新規）
  - VERSION.json

指摘（重大）:
  パッケージを入れていない Python で、01 Planning と 02 Evaluation が起動時に
  ModuleNotFoundError: No module named 'reportlab' で停止する。
  一方 Installer と手順書は「Python が検出済みなら追加インストールは不要」と案内していた。

方針（ご指示どおり）:
  不足パッケージとインストール用コマンドを表示するだけ。Installer はインストールしない。

修正:
  1. package_check.py
     - Installer と同じ AZRAS フォルダーにある各製品フォルダーを、ランチャーと同じ規則で探し、
       各製品の requirements.txt を読む（製品側の一覧に常に追従。Installer に一覧を持たない）。
     - 「used by dev_checks only」と注記された行は任意扱い（自己検査用）。
     - 検出した Python に import できるかだけを問い合わせる（pip は実行しない）。
     - pip 名と import 名の対応（Pillow→PIL、opencv-python→cv2、PyMuPDF→fitz 等）。
     - コマンド例：py -m pip install numpy pandas reportlab
       （空白を含むパスは引用符付き。py.exe は py）。
  2. azras_installer.py
     - Python の行の下に、パッケージごとの行（使用製品・必須/任意・検出済み/未検出）を表示。
     - 下部に不足パッケージ名を表示。
     - 「インストール用コマンド」ボタン：コマンドを表示し、クリップボードへコピー。
       任意（自己検査用）の不足分は別コマンドとして併記。
     - EXE 版では EXE の場所から製品フォルダーを探す。
  3. 手順書（日英）：「追加インストールは不要」を削除し、確認とコマンド実行の手順を追加。

確認:
  - パッケージ無しの Python：Planning / Evaluation の起動停止を再現。
    Installer の一覧で7件（numpy, opencv-python, pandas, Pillow, PyMuPDF, pypdf, reportlab）が未検出、
    表示されたコマンドを実行 → 全件検出済み → Planning / Evaluation とも起動成功。
  - 新規 dev_check（日英の実画面を含む）PASS、dev_checks 8本すべて PASS、pyflakes 警告なし。

変更していないもの:
  Python 本体の検出、ショートカット作成、ランチャー、Installer の版番号（5.0.4）。
