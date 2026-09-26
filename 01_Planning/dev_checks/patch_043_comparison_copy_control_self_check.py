# -*- coding: utf-8 -*-
"""PATCH_043 self-check: comparison copies created by 03 Compare.

A copy may only be re-priced (Module 5) and re-evaluated (02 Evaluation 6/7).
Upstream inputs are never changed or re-saved on a copy, its unified prices
cannot be overwritten by an AI import or a manual edit, and prices written from
a premise book are identified as such in the Module 5 result.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.project_store import comparison_copy_block_reason, comparison_copy_info  # noqa: E402
from core.project_coordinator import update_module_and_propagate  # noqa: E402
from services.construction_cost_engine_v9_4 import _price_basis_fingerprint  # noqa: E402

FAIL = []


def check(ok, label, detail=""):
    if ok:
        print(f"  [OK]   {label}")
    else:
        FAIL.append(f"{label} :: {detail}")
        print(f"  [NG]   {label} :: {detail}")


COPY = {"project_id": "copy-1", "comparison_copy": {
    "schema": "AZRAS_COMPARISON_COPY_V1", "group_id": "G1", "premise_book_file": "PB.json",
    "premise_book_version": "v1", "source_project_path": "C:/JSON/260918_RC_Rahmen_Sample/260918_RC_Rahmen_Sample.json",
    "allowed_modules": ["module5", "module6", "module7"]}}
PLAIN = {"project_id": "p-1"}

print("PATCH_043 self-check")
print("-- 1. what a copy may and may not do")
check(comparison_copy_info(COPY) is not None and comparison_copy_info(PLAIN) is None,
      "a copy is recognised by its marker; an ordinary Project is not")
check(comparison_copy_info({"comparison_copy": {"schema": "OTHER"}}) is None,
      "an unrelated marker schema is not treated as a copy")
check(comparison_copy_block_reason(COPY, "module5") is None, "Module 5 may be recalculated and saved on a copy")
for action in ("module0", "module1", "module2", "module9", "module10", "detailed_configuration"):
    check(bool(comparison_copy_block_reason(COPY, action)), f"{action} is blocked on a copy")
for action in ("module5_ai_cost_import", "module5_manual_unit_cost_edit"):
    check(bool(comparison_copy_block_reason(COPY, action)), f"{action} is blocked on a copy")
for action in ("module0", "module1", "module2", "module5", "module5_ai_cost_import", "module5_manual_unit_cost_edit", "module10"):
    check(comparison_copy_block_reason(PLAIN, action) is None, f"{action} is never blocked on an ordinary Project")
msg = comparison_copy_block_reason(COPY, "module1", "ja")
check("元Project" in msg and "03 Compare" in msg, "the Japanese message names the source Project and the fix")
check("Source Project" in comparison_copy_block_reason(COPY, "module1", "en"), "an English message exists")

print("-- 2. the save choke point refuses a blocked module")
try:
    update_module_and_propagate(dict(COPY), "unused.json", "module1", {}, {}, ROOT)
    check(False, "Module 1 save on a copy raises")
except ValueError as exc:
    check("比較用コピー" in str(exc), "Module 1 save on a copy raises with the copy message", str(exc)[:60])

print("-- 3. every other save path is guarded")
guards = {
    "module0/app.py": 'comparison_copy_block_reason(self.project, "module0"',
    "core/detailed_configuration_ui.py": 'comparison_copy_block_reason(self.project, "detailed_configuration"',
    "regional_analysis/module9_ui.py": 'comparison_copy_block_reason(project, "module10"',
    "module5/app.py": '_comparison_copy_price_block("module5_ai_cost_import")',
}
for path, needle in guards.items():
    check(needle in (ROOT / path).read_text(encoding="utf-8"), f"{path} is guarded")
m5 = (ROOT / "module5" / "app.py").read_text(encoding="utf-8")
check('_comparison_copy_price_block("module5_manual_unit_cost_edit")' in m5, "the manual unit-cost editor is guarded")
reg = (ROOT / "regional_analysis" / "module9_ui.py").read_text(encoding="utf-8")
i_guard = reg.index('_blocked = comparison_copy_block_reason(project, "module10"')
i_missing = reg.index('if row.get("enabled", True) and (not row.get("epw_path")')
check(i_guard < i_missing, "regional analysis stops before any file is generated")

print("-- 4. premise-book prices are identified in the Module 5 result")
cg = [{"unit_price_source": "local_installed_all_in", "pricing_status": "comparison_group_confirmed",
       "pricing_structure": "installed_all_in"}] * 6
ai = [{"unit_price_source": "local_installed_all_in", "pricing_status": "ai_post_review_rechecked_provisional",
       "pricing_structure": "installed_all_in"}] * 3
db = [{"unit_price_source": "regional_dataset", "pricing_status": "planning_city_initial_estimate_2026",
       "pricing_structure": "component_split"}] * 2
fp = _price_basis_fingerprint({"pricing_mode": "ai_approximate_cost_session_local_currency"}, cg + ai, COPY)
check(fp["basis_token"] == "comparison_group_premise_book", "shared prices + method-specific AI prices = premise book",
      fp["basis_token"])
check(fp["premise_book_file"] == "PB.json" and fp["premise_book_version"] == "v1" and fp["comparison_group_id"] == "G1",
      "the premise book file, version and group are recorded")
fp2 = _price_basis_fingerprint({"pricing_mode": "x"}, cg + db, COPY)
check(fp2["basis_token"] == "mixed_comparison_group_and_regional_database",
      "premise-book prices mixed with database prices are reported as mixed", fp2["basis_token"])
fp3 = _price_basis_fingerprint({"pricing_mode": "x"}, ai, PLAIN)
check(fp3["basis_token"] == "ai_approximate_cost_session" and fp3["premise_book_file"] is None,
      "an ordinary AI-priced Project is unchanged", fp3["basis_token"])

print()
if FAIL:
    print("[NG] PATCH_043 self-check FAILED:")
    for f in FAIL:
        print("   -", f)
    raise SystemExit(1)
print("PATCH_043_COMPARISON_COPY_CONTROL_PASS")
