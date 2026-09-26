from pathlib import Path
import sys
_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from services.lca_module_crosswalk import build_lca_module_crosswalk
s={
 "initial_embodied_co2_kg":100,"operational_co2_kg":200,"renewal_embodied_co2_kg":30,
 "demolition_co2_kg":20,"reuse_recycling_credit_kg":10,"net_lifecycle_co2_kg":340,
 "initial_embodied_energy_MJ":1000,"operational_energy_MJ":2000,"renewal_embodied_energy_MJ":300,
 "demolition_energy_MJ":200,"total_lifecycle_energy_MJ":3500,
}
x=build_lca_module_crosswalk(s)
assert [r["module_group"] for r in x["rows"]]==["A1-A5","B4-B5 proxy","B6","C1-C4","D"]
assert abs(x["reconciliation"]["co2_difference_kg"])<1e-9
assert abs(x["reconciliation"]["energy_difference_MJ"])<1e-9
print("LCA_MODULE_CROSSWALK_PASS")
