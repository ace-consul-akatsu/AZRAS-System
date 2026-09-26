from pathlib import Path
import sys
_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from pathlib import Path
import json, sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from services.future_climate_8760 import warming_delta_C
assert abs(warming_delta_C(0,2.0,3.0)-0.0)<1e-9
assert abs(warming_delta_C(50,2.0,3.0)-1.0)<1e-9
assert abs(warming_delta_C(100,2.0,3.0)-2.0)<1e-9
assert abs(warming_delta_C(150,2.0,3.0)-2.5)<1e-9
assert abs(warming_delta_C(200,2.0,3.0)-3.0)<1e-9
print("FUTURE_CLIMATE_TRAJECTORY_PASS")
