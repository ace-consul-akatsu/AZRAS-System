from pathlib import Path
import sys
_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

def pv(rate,c): return sum(cf/((1+rate)**i) for i,cf in enumerate(c))
c=[-100]+[20]*10
assert pv(.02,c)>pv(.04,c)>pv(.06,c)
print("DISCOUNT_RATE_SENSITIVITY_PASS")
