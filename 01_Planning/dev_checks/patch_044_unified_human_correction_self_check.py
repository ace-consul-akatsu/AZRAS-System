from pathlib import Path
import ast

ROOT=Path(__file__).resolve().parents[1]
p=ROOT/'module1'/'app.py'
s=p.read_text(encoding='utf-8')
ast.parse(s)
checks={
    'toolbar renamed to unified screen':'人間修正・確認（表①）' in s,
    'double click queues row':'row["manual_review_selected_by_user"]=True' in s,
    'double click opens same human review screen':'self._open_manual_quantity_review_table(focus_row=row)' in s,
    'quantity maps to accepted quantity':'row["accepted_quantity"]=q' in s,
    'approved basis stored visibly':'row["human_approved_calculation_basis"]=approved_basis' in s and 'row["evidence"]=approved_basis' in s,
    'instructor becomes visible source':'row["source_mode"]=instructor' in s and 'row["human_instruction_by"]=instructor' in s,
    'provisional specification retained':'row["designer_specification"]=spec' in s,
    'parameter recalculation retained':'条件から数量再計算' in s and 'def recalc_from_parameter()' in s,
    'human-approved zero remains primary':'if bool(row.get("manual_override_table1")):\n            return True' in s,
    'old HUMAN_REVIEW_FINAL gate retained':'human_review_parameter_recalculation' in s,
}
failed=[k for k,v in checks.items() if not v]
for k,v in checks.items():
    print(('  [OK]   ' if v else '  [FAIL] ')+k)
if failed:
    raise SystemExit('PATCH_044_FAILED: '+', '.join(failed))
print('\nPATCH_044_UNIFIED_HUMAN_CORRECTION_PASS')
