from pathlib import Path
import sys
_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from pathlib import Path
import ast
R=Path(__file__).resolve().parent.parent
for rel in ["services/investment_engine_v9_5.py","module6/app.py"]:
    ast.parse((R/rel).read_text(encoding="utf-8-sig"))
t=(R/"services/investment_engine_v9_5.py").read_text(encoding="utf-8-sig")
for token in ["constant_price_comparison","combined_construction_and_lifecycle_base_year","comparison_framework","\"200\":_scenario_horizon_summary(200"]:
    assert token in t, token
ui=(R/"module6/app.py").read_text(encoding="utf-8-sig")
for token in ["constant_price_tree","200年 NPV","60年・120年・180年・200年"]:
    assert token in ui, token
print("[OK] PATCH 138 three-layer comparison structure")
