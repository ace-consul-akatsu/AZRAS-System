# -*- coding: utf-8 -*-
"""v2.2.0 baseline: the product is licensed under the MIT License.

The AZRAS-System repository is published under the MIT License (root LICENSE).
Each product's LICENSE.txt used to carry a different, custom permission text,
so the same download stated two licenses.  This check keeps LICENSE.txt equal
to the MIT License of the repository (copyright holder: ACE Comprehensive
Consulting Co., Ltd.) followed by a Japanese reference summary, and - where the
product has a License window - keeps that window showing the same text.

Run: python dev_checks/license_consistency_self_check.py
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

MIT_EN = """MIT License

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
FAIL = []


def check(ok, label, detail=""):
    if ok:
        print(f"  [OK]   {label}")
    else:
        FAIL.append(f"{label} :: {detail}")
        print(f"  [NG]   {label} :: {detail}")


print("license_consistency self-check")
text = (ROOT / "LICENSE.txt").read_text(encoding="utf-8-sig").replace("\r\n", "\n")
check(text.startswith(MIT_EN + "\n"), "LICENSE.txt is the full MIT License (ACE Comprehensive Consulting Co., Ltd.)",
      text[:60])
check("日本語（参考訳。法的には上記の英文が優先します）" in text, "LICENSE.txt has the Japanese reference summary")
for old in ("Commercial use: Permitted", "改変・再配布も可能です"):
    check(old not in text, f"the old custom license text is gone ({old})")
branding = ROOT / "core" / "branding.py"
if branding.exists() and "LICENSE_BILINGUAL" in branding.read_text(encoding="utf-8"):
    from core.branding import LICENSE_BILINGUAL  # noqa: E402
    check(LICENSE_BILINGUAL + "\n" == text, "the License window shows exactly LICENSE.txt")

print()
if FAIL:
    print("[NG] license_consistency self-check FAILED:")
    for f in FAIL:
        print("   -", f)
    raise SystemExit(1)
print("LICENSE_CONSISTENCY_PASS")
