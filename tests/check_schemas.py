# -*- coding: utf-8 -*-
"""Every public schema copy in schemas/ is byte-identical to its original(s) in the products.

Run from the repository root:  python tests/check_schemas.py
"""
import hashlib
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
fail = []
manifest = json.loads((REPO / "schemas" / "manifest.json").read_text(encoding="utf-8"))
listed = {e["file"] for e in manifest["schemas"]}
on_disk = {p.name for p in (REPO / "schemas").glob("*.json") if p.name != "manifest.json"}
if listed != on_disk:
    fail.append(f"schemas/ files and manifest.json differ: {sorted(listed ^ on_disk)}")
for entry in manifest["schemas"]:
    copy = REPO / "schemas" / entry["file"]
    digest = hashlib.sha256(copy.read_bytes()).hexdigest() if copy.exists() else None
    for original in entry["originals"]:
        src = REPO / original
        if not src.exists():
            fail.append(f"{original}: original not found")
        elif hashlib.sha256(src.read_bytes()).hexdigest() != digest:
            fail.append(f"schemas/{entry['file']} differs from {original}")
        else:
            print(f"  [OK]   schemas/{entry['file']} == {original}")
    try:
        json.loads(copy.read_text(encoding="utf-8-sig"))
    except ValueError as exc:
        fail.append(f"schemas/{entry['file']}: invalid JSON ({exc})")
for f in fail:
    print("  [NG]  ", f)
print("CHECK_SCHEMAS_" + ("FAIL" if fail else "PASS"))
sys.exit(1 if fail else 0)
