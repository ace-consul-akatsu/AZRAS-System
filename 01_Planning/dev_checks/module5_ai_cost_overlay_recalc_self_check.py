from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
app=(ROOT/'module5'/'app.py').read_text(encoding='utf-8-sig')
engine=(ROOT/'services'/'construction_cost_engine_v9_4.py').read_text(encoding='utf-8-sig')
coord=(ROOT/'core'/'project_coordinator.py').read_text(encoding='utf-8-sig')

required_app=[
    '_recalculated=self.calculate(silent_success=True)',
    '"ai_cost_provider_overlay": self._current_ai_cost_overlay()',
    'self._restore_ai_cost_overlay_from_snapshot(snapshot)',
    '"project_binding":{',
]
required_engine=[
    '_bound_id=str(_binding.get("project_id") or "").strip()',
    'ai_post_review_rechecked_provisional',
    'ai_primary_basis_provisional',
]
required_coord=[
    '_overlay=snapshot.get("ai_cost_provider_overlay")',
    '_loc["_session_ai_unit_cost_overlay"]=copy.deepcopy(_overlay)',
]
missing=[]
for label,text,tokens in [('module5/app.py',app,required_app),('construction_cost_engine_v9_4.py',engine,required_engine),('project_coordinator.py',coord,required_coord)]:
    for token in tokens:
        if token not in text:
            missing.append(f'{label}: {token}')
if missing:
    print('[NG] PATCH_038 AI Cost Provider linkage regression:')
    for m in missing: print(' -',m)
    sys.exit(1)
print('MODULE5_AI_COST_OVERLAY_RECALC_PASS')
