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

詳しい文書（日本語）：

- [概要説明](docs/ja/01_AZRAS_%E6%A6%82%E8%A6%81%E8%AA%AC%E6%98%8E_v2_2_0_JA.docx)
- [取扱説明書](docs/ja/02_AZRAS_%E5%8F%96%E6%89%B1%E8%AA%AC%E6%98%8E%E6%9B%B8_v2_2_0_JA.docx)
- [特徴](docs/ja/03_AZRAS_%E7%89%B9%E5%BE%B4_v2_2_0_JA.docx)
- [開発憲章（AIでAZRASを改修する際の原則）](docs/ja/04_AZRAS_%E9%96%8B%E7%99%BA%E6%86%B2%E7%AB%A0_v0_4_%E7%B5%B1%E5%90%88%E7%89%88_JA.docx)
- [今後の発展方法](docs/ja/05_AZRAS_%E4%BB%8A%E5%BE%8C%E3%81%AE%E7%99%BA%E5%B1%95%E6%96%B9%E6%B3%95_v2_2_0_JA.docx)
- [正式開発史（2026年6月〜9月7日）](docs/ja/06_AZRAS_%E6%AD%A3%E5%BC%8F%E9%96%8B%E7%99%BA%E5%8F%B2_v2.0_JA.docx)
- [正式開発史 更新版（2026年9月7日以降）](docs/ja/06_AZRAS_%E6%AD%A3%E5%BC%8F%E9%96%8B%E7%99%BA%E5%8F%B2_v2_4_JA.docx)

## サンプルデータ

同じ建物プランを3つの工法で設計した図面（PDF）です。そのまま AZRAS Planning に読み込めます。

- [AZRAS（RCアップライト工法）](examples/260805_AZRAS.pdf)
- [木造 2×6](examples/260805_2%C3%976.pdf)
- [一般RCラーメン](examples/260805_RC_Rahmen.pdf)

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
| `docs/` | 免責文（Markdown・Word、日英）、`docs/ja/` に詳しい説明文書 |
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
