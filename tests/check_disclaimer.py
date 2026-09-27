# -*- coding: utf-8 -*-
"""docs/DISCLAIMER.md and DISCLAIMER.ja.md carry exactly the text of the Word versions.

The Word files are the formal documents; the Markdown files are for reading on
GitHub.  This check compares them paragraph by paragraph (Markdown markup and
the language-switch line are ignored).

Run from the repository root:  python tests/check_disclaimer.py
"""
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))
from _docx_text import paragraphs  # noqa: E402

PAIRS = (("docs/DISCLAIMER.md", "docs/25_AZRAS_System_v2_2_0_Disclaimer_of_Use_EN.docx"),
         ("docs/DISCLAIMER.ja.md", "docs/25_AZRAS_System_v2_2_0_Disclaimer_of_Use_JA.docx"))


def markdown_paragraphs(text):
    out = []
    for block in re.split(r"\n\s*\n", text.strip()):
        if "](DISCLAIMER" in block:
            continue  # language switch line
        block = re.sub(r"^#+\s*", "", block)
        block = block.replace("<br>\n", "\n").replace("<br>", "\n")
        block = re.sub(r"\*\*(.+?)\*\*", r"\1", block)
        block = block.replace("\\*", "*").strip()
        if block:
            out.append(block)
    return out


fail = []
for md, docx in PAIRS:
    a = markdown_paragraphs((REPO / md).read_text(encoding="utf-8"))
    b = [t for _style, t in paragraphs(REPO / docx)]
    if a == b:
        print(f"  [OK]   {md} == {docx} ({len(a)} paragraphs)")
    else:
        first = next((i for i, (x, y) in enumerate(zip(a, b)) if x != y), min(len(a), len(b)))
        fail.append(f"{md} differs from {docx} at paragraph {first + 1}")
for f in fail:
    print("  [NG]  ", f)
print("CHECK_DISCLAIMER_" + ("FAIL" if fail else "PASS"))
sys.exit(1 if fail else 0)
