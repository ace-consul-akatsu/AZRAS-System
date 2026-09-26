from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from module5.app import Module5App


class _Var:
    def __init__(self, value):
        self.value = value
    def get(self):
        return self.value


def main():
    obj = object.__new__(Module5App)
    obj.project_path = Path('/tmp/260923_RC_Rahmen_Sample.json')
    obj.currency = _Var('JPY')
    obj._authoritative_project_cost_location = lambda: '愛知県春日井市松河戸町2-18-7'
    obj._ai_cost_request_scope = lambda: {
        'items': [{'cost_item_key': 'concrete', 'unit': 'm3'}],
        'equipment_packages': [],
        'gross_floor_area_m2': 245.1,
    }
    obj._ai_cost_recheck_context = lambda: {
        'primary': {},
        'confirmed_supported_items': [],
        'independent_reviews': [],
    }

    request = obj._ai_cost_recheck_request_text()
    expected_answer = 'YYMMDD_HHMM_AZRAS_AI_APPROX_COST_FINAL_260923_RC_Rahmen_Sample_chatgpt.json'
    assert expected_answer in request, expected_answer
    assert 'FINAL marker is mandatory' in request

    src = (ROOT / 'module5' / 'app.py').read_text(encoding='utf-8')
    assert 'AZRAS_AI_APPROX_COST_CHATGPT_FINAL_RECHECK_REQUEST.txt' in src
    assert 'AZRAS_AI_APPROX_COST_CHATGPT_RECHECK_REQUEST.txt' not in src
    assert '⑤ ChatGPT最終再確認依頼書' in src
    assert '⑥ ChatGPT最終再確認JSON取込 → 終了' in src

    print('PATCH_046 AI cost FINAL filename self-check: PASS')


if __name__ == '__main__':
    main()
