# AZRAS System v2.2.0

[English](README.md) | **日本語**

<!-- Zenodo で DOI が発行されたら XXXXXXX（全バージョン共通の Concept DOI）を置き換えて、コメントを外してください:
[![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.XXXXXXX.svg)](https://doi.org/10.5281/zenodo.XXXXXXX)
-->
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

AZRAS System は、建物を **200年間のライフサイクル** で計画・評価・比較するためのオープンソースのデスクトップソフトです。CAD図面をPDF印刷したものを起点に、数量拾い、環境・エネルギー解析、修繕・更新・解体のシナリオ、長期の事業性評価までを一貫して行い、工法・仕様・建設地の違いを横並びで比較します。

本ソフトウェアは、**AI研究および事業目的** のために利用されることを前提として無償で提供しています。

## できること

- **PDF図面からの数量拾い** — AZRAS 自身が図面を読み取り、読み取れない項目だけをAIに依頼します。
- **複数AIの独立回答を根拠付きで比較** — 同じ依頼パッケージを複数のAIサービス（ChatGPT、Claude、Gemini など）に回答させられます。各回答は根拠・計算根拠とともに別々の候補として保持し、同じ意味・同じ単位の数量どうしだけを比較します。**多数決では決めず**、未解決の項目は人間の確認に回します。数量は「確定」「想定・暫定」「要確認」の3段階に区分します。
- **AIの定点観測** — 同じ図面・同じ依頼文を、時期を変えて複数のAIへ再送できます。SHA-256 で図面の同一性を保証するため、AIの図面読解能力の変化を長期的に観測できます。
- **環境・エネルギー** — 地域の年間8,760時間の気象データに基づくCO2排出量・エネルギー消費量の算出。断熱仕様を変えた場合の比較。
- **200年評価** — 修繕・更新・解体のシナリオと費用、現在価値を含む200年間の事業収支。
- **比較** — 同じ計画を、工法・仕様・気候を変えて比較（保存済みの結果だけを読み取ります）。

AZRAS Planning は **AIサービスのAPIを呼び出しません**。依頼ファイルを書き出し、利用者が自分の選んだAIサービスとやり取りし、返ってきたJSONを検証したうえで取り込みます。

## 製品構成

| フォルダ | 製品 | 役割 |
|---|---|---|
| `00_Installer` | AZRAS Installer 5.0.4 | 動作環境の確認、デスクトップアイコンの作成、ランチャー |
| `01_Planning` | AZRAS Planning 2.2.0 | 計画条件、図面解析、数量、AI積算、Project JSON |
| `02_Evaluation` | AZRAS Evaluation 2.2.0 | 200年環境、更新シナリオと費用、200年事業 |
| `03_Compare` | AZRAS Compare 2.2.0 | 保存済み Project JSON の結果を読み取り専用で比較 |

データの流れ：**01 Planning → 02 Evaluation（計算・保存）→ 03 Compare（保存済み結果の読み取りのみ）**。製品間のデータ受け渡しは Project JSON（スキーマ 3.0、[schemas/project_schema_v3_0.json](schemas/project_schema_v3_0.json)）だけで行います。

## 動作環境

- Windows 10 / 11
- Python 3.13（64ビット）— [python.org](https://www.python.org/) から入手（Tkinter を含みます）
- Python パッケージ：[requirements.txt](requirements.txt) を参照

## 使い始め方

1. このリポジトリをダウンロード（**Code → Download ZIP**）し、フォルダ構成のまま解凍します。
2. 解凍したフォルダで Python パッケージをインストールします。
   ```
   py -m pip install -r requirements.txt
   ```
3. `00_Installer\run_AZRAS_Installer_without_build.bat` を実行します。Python の確認と、デスクトップ・スタートメニューへの AZRAS アイコンの作成ができます。
4. そのアイコン、または `00_Installer\run_AZRAS_Launcher_without_build.bat` から AZRAS を起動し、Planning・Evaluation・Compare を選びます。

各製品は、それぞれのフォルダにある `run_AZRAS_<製品名>_without_build.bat` から単独でも起動できます。

Windows 用の実行ファイル（EXE）は `build_AZRAS_Planning.bat`・`build_AZRAS_Evaluation.bat`（PyInstaller）で作成できます。EXE の版情報は `VERSION.json` から自動生成されます。

## 説明文書

詳しい文書（Word、日本語・英語）：

| 文書 | 日本語 | English |
|---|---|---|
| 概要説明 | [日本語](docs/ja/01_AZRAS_Overview_v2_2_0_JA.docx) | [English](docs/en/01_AZRAS_Overview_v2_2_0_EN.docx) |
| 取扱説明書 | [日本語](docs/ja/02_AZRAS_User_Manual_v2_2_0_JA.docx) | [English](docs/en/02_AZRAS_User_Manual_v2_2_0_EN.docx) |
| 特徴 | [日本語](docs/ja/03_AZRAS_Key_Features_v2_2_0_JA.docx) | [English](docs/en/03_AZRAS_Key_Features_v2_2_0_EN.docx) |
| 開発憲章（AIでAZRASを改修する際の原則） | [日本語](docs/ja/04_AZRAS_Development_Constitution_v0_4_JA.docx) | [English](docs/en/04_AZRAS_Development_Constitution_v0_4_EN.docx) |
| 今後の発展方法 | [日本語](docs/ja/05_AZRAS_Further_Development_v2_2_0_JA.docx) | [English](docs/en/05_AZRAS_Further_Development_v2_2_0_EN.docx) |
| 正式開発史（2026年6月〜9月7日） | [日本語](docs/ja/06_AZRAS_Official_Development_History_v2_0_JA.docx) | [English](docs/en/06_AZRAS_Official_Development_History_v2_0_EN.docx) |
| 正式開発史 更新版（2026年9月7日以降） | [日本語](docs/ja/06_AZRAS_Official_Development_History_v2_4_JA.docx) | [English](docs/en/06_AZRAS_Official_Development_History_v2_4_EN.docx) |

## サンプルデータ

同じ建物プランを3つの工法で設計した図面（PDF）です。そのまま AZRAS Planning に読み込めます。

- [AZRAS（RCアップライト工法）](examples/261001_0150_AZRAS.pdf)
- [木造 2×6](examples/261001_0150_2x6.pdf)
- [一般RCラーメン](examples/261001_0150_RC_Rahmen.pdf)

v2.2.0 で最後まで処理したサンプルプロジェクト一式（保存済み結果を含む Project JSON、地域別バリエーション、ChatGPT・Claude・Meta AI の独立回答を含む複数AI積算ラウンド）は、別のデータセットとして Zenodo で公開しています（CC BY 4.0）。<!-- 登録後、ここにデータセットの DOI を追記します。 -->

## 引用方法

研究で AZRAS System を利用した場合は、引用をお願いします。GitHub の **「Cite this repository」** ボタン（[CITATION.cff](CITATION.cff) から生成）で APA・BibTeX 形式を取得できます。

> Akatsu, M. (2026). *AZRAS System* (Version 2.2.0) [Computer software]. ACE Comprehensive Consulting Co., Ltd. https://github.com/ace-consul-akatsu/AZRAS-System

```bibtex
@software{akatsu_azras_system_2026,
  author    = {Akatsu, Makito},
  title     = {AZRAS System},
  version   = {2.2.0},
  year      = {2026},
  publisher = {ACE Comprehensive Consulting Co., Ltd.},
  url       = {https://github.com/ace-consul-akatsu/AZRAS-System}
}
```

Zenodo への登録後、ここに DOI を追記します。

## 免責

計算・解析・比較の結果はすべて、企画・比較・研究のための参考情報です。設計性能、構造安全性、法令適合性、費用、工期、投資成果を保証するものではなく、複数のAIの回答が一致しても正しさは保証されません。入力値・AIの回答・結果は利用者自身が確認し、重要な判断では資格を有する専門家に確認してください。

ご利用の前に、必ず免責文の全文をお読みください。

- [利用にあたっての免責（日本語）](docs/DISCLAIMER.ja.md)
- [Disclaimer of Use (English)](docs/DISCLAIMER.md)

印刷・正式配布用の Word 版は [docs/](docs/) にあります。

日本語版と英語版に相違がある場合は、日本語版が優先します。

## ライセンス

[MIT License](LICENSE) — Copyright (c) 2026 ACE Comprehensive Consulting Co., Ltd.（株式会社ACE総合コンサル）

## リポジトリの構成

| 場所 | 内容 |
|---|---|
| `00_Installer/` … `03_Compare/` | 4製品 |
| `docs/` | 免責文（Markdown・Word、日英）、`docs/en/`・`docs/ja/` に詳しい説明文書（英語・日本語） |
| `schemas/` | 製品が使うスキーマの公開用写し（Project JSON 3.0、AI積算） |
| `examples/` | 同じプランを3工法で設計した図面 |
| `tests/` | 全製品と製品間の接続を1コマンドで検査 |

## 開発者向け

- リポジトリのルートで `python tests/run_all.py` を実行すると、すべての検査を一度に行います。各製品の自己検査（`dev_checks/`）と、リポジトリの検査（スキーマの写し、免責文の本文、Project JSON の受け渡し、市場家賃の受け渡し、ランチャー）です。実行できなかった検査は不合格として扱います。
- 各製品の版は `VERSION.json` が唯一の正本です。
- 修正内容と回帰記録は、各製品の `PATCH/` フォルダにあります。
- `schemas/` のファイルは写しで、ソフトは製品フォルダ内の原本を読みます。`tests/check_schemas.py` が両者の一致を保ちます。

## 関連リンク

- ホームページ：https://ace-consul-akatsu.github.io
- AZRAS 建築システム（RCアップライト工法）の設計思想と検証データ：[Adaptive-Zero-Rebuild-Asset-System-AZRAS](https://github.com/ace-consul-akatsu/Adaptive-Zero-Rebuild-Asset-System-AZRAS)

---

開発：**株式会社ACE総合コンサル**（ACE Comprehensive Consulting Co., Ltd.）愛知県春日井市
