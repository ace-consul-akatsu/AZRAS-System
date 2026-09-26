# -*- coding: utf-8 -*-
"""PATCH_048: the MEP-schedule equipment block ends at the title block's
upper-case "... ENGINEERING" company line - for any company.

Module 1 used to stop an equipment block at one real client's company name,
written out in the source.  The source is published, so that name was replaced
by a general rule.  This check uses an invented company name only.

Run: python dev_checks/title_block_company_rule_self_check.py
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FAIL = []


def check(ok, label, detail=""):
    if ok:
        print(f"  [OK]   {label}")
    else:
        FAIL.append(f"{label} :: {detail}")
        print(f"  [NG]   {label} :: {detail}")


print("title_block_company_rule self-check")
src = (ROOT / "module1" / "app.py").read_text(encoding="utf-8")
line = next((l for l in src.splitlines() if l.startswith("_TITLE_BLOCK_ENGINEERING_COMPANY_RE=")), None)
check(line is not None, "the module-level title-block rule exists")
ns = {"re": re}
exec(line or "_TITLE_BLOCK_ENGINEERING_COMPANY_RE=None", ns)
R = ns["_TITLE_BLOCK_ENGINEERING_COMPANY_RE"]
check("_TITLE_BLOCK_ENGINEERING_COMPANY_RE.search(nt,m.end())" in src, "the sanitary-schedule parser uses it")
sentinels = re.search(r"for sentinel in \(([^)]*)\):", src[src.index("def _extract_sanitary_schedule_quantities"):])
check(sentinels is not None and "ENGINEERING" not in sentinels.group(1),
      "no company name is written out in the sentinel list", sentinels.group(1) if sentinels else "")

if R is not None:
    t = "GW-1 ガス瞬間湯沸器 16号\nメーカー XX\nABC PLANT ENGINEERING CO.,LTD.\n図面番号 P-02"
    m = R.search(t)
    check(m is not None and m.start() == t.index("ABC"), "an upper-case '... ENGINEERING' company line ends the block")
    t = "DP-1 汚水ポンプ 0.4kW 設計 XYZ ENGINEERING 株式会社"
    m = R.search(t)
    check(m is not None and m.start() == t.index("XYZ"), "also when the company name is mid-line")
    for label, t in (("lower-case engineering", "DP-1 pump for engineering plastic parts"),
                     ("no company line", "DP-1 汚水ポンプ\n仕様 200V 3φ\nLIXIL BC-ZA10S")):
        check(R.search(t) is None, f"no false stop: {label}")

print()
if FAIL:
    print("[NG] title_block_company_rule self-check FAILED:")
    for f in FAIL:
        print("   -", f)
    raise SystemExit(1)
print("TITLE_BLOCK_COMPANY_RULE_PASS")
