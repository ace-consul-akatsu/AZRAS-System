# -*- coding: utf-8 -*-
"""Every file and folder name in the repository is plain ASCII.

Japanese or other non-ASCII file names are decoded differently by different
ZIP tools (Windows' built-in extractor reads them as Shift-JIS unless the
archive marks them as UTF-8), which garbled nine file names in the first
upload of this repository and broke the links to them.  Content may be in
any language; only the names must be ASCII.

Run from the repository root:  python tests/check_filenames.py
"""
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
bad = [str(p.relative_to(REPO)) for p in REPO.rglob("*")
       if ".git" not in p.parts and any(ord(c) > 127 for c in p.name)]
for b in bad:
    print("  [NG]   non-ASCII name:", b)
print(f"  checked {sum(1 for p in REPO.rglob('*') if '.git' not in p.parts)} paths")
print("CHECK_FILENAMES_" + ("FAIL" if bad else "PASS"))
sys.exit(1 if bad else 0)
