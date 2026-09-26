from __future__ import annotations

from core.version import PRODUCT_NAME, VERSION, DISPLAY_NAME, DISPLAY_NAME_SHORT
COMPANY_EN = "ACE Comprehensive Consulting Co., Ltd."
COMPANY_JA = "株式会社ACE総合コンサル"
COPYRIGHT = f"© 2026 {COMPANY_EN}"
PRINT_FOOTER_COMPANY = f"{COMPANY_EN} / {COMPANY_JA}"
GITHUB = "https://github.com/ace-consul-akatsu"

# The license shown in the License window.  It is the same MIT License as
# LICENSE.txt (dev_checks/license_consistency_self_check.py keeps them equal).
LICENSE_EN = """MIT License

Copyright (c) 2026 ACE Comprehensive Consulting Co., Ltd.

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE."""

LICENSE_JA = """本ソフトウェアは MIT License の下で提供されます。
著作権者：株式会社ACE総合コンサル（ACE Comprehensive Consulting Co., Ltd.）

・本ソフトウェアは無償で、使用・複製・改変・結合・公開・配布・再許諾・販売を含め、制限なく取り扱うことができます。営利・非営利を問いません。
・条件：本ソフトウェアの複製または重要な部分を配布する場合は、上記の著作権表示と本許諾表示を必ず含めてください。
・本ソフトウェアは「現状のまま」提供され、商品性、特定目的への適合性、権利非侵害を含め、明示・黙示を問わず一切保証しません。
・著作者および著作権者は、本ソフトウェアまたはその使用その他の取扱いに起因または関連して生じるいかなる請求、損害その他の責任も負いません。

設計・施工・投資その他の判断は、利用者自身の責任で計算結果を十分に確認したうえで行ってください。
詳細は別途配布の「AZRAS System v2.2.0 利用にあたっての免責」（日本語版・英語版）を併せてご確認ください。"""

LICENSE_BILINGUAL = f"{LICENSE_EN}\n\n{'-' * 60}\n日本語（参考訳。法的には上記の英文が優先します）\n\n{LICENSE_JA}"
