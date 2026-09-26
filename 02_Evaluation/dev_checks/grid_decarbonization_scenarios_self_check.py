from pathlib import Path
import sys
_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from services.grid_decarbonization_scenarios import resolve_grid_decarbonization_scenario
assert resolve_grid_decarbonization_scenario("low",99)==("low",-0.25)
assert resolve_grid_decarbonization_scenario("standard",99)==("standard",-0.5)
assert resolve_grid_decarbonization_scenario("high",99)==("high",-1.0)
assert resolve_grid_decarbonization_scenario("custom",-0.75)==("custom",-0.75)
print("GRID_DECARBONIZATION_SCENARIOS_PASS")
