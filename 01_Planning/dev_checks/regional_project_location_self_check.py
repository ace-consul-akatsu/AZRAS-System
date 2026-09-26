from pathlib import Path
import sys
_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

# PATCH_634 regression test for PATCH_632: Module 9 generates one derived
# Project JSON per selected city, replacing Module 0 (country/city/address/
# lat/lon) for each. Module 10's legend/table label is derived from
# common["project_location"] FIRST (it is Module 0's authoritative
# "都市・所在地" field), falling back to common["city"]. The historical bug:
# _update_module0_location() updated city/address/country/lat/lon but not
# project_location, so every regional JSON kept showing the ORIGINAL base
# project's address in Module 10, even though the underlying calculations
# correctly differed per city.
#
# This test creates a synthetic base project with a distinctive
# project_location, runs it through _update_module0_location for two
# different cities, and asserts that project_location (and therefore the
# label build_module10_snapshot will read) is replaced for each — not left
# at the base project's original address.

from regional_analysis.project_generator import _update_module0_location

BASE_ADDRESS = "愛知県春日井市松河戸町2-18-7"

def _base_project():
    return {
        "common": {
            "project_location": BASE_ADDRESS,
            "city": "Kasugai",
            "country": "Japan",
            "address": BASE_ADDRESS,
        },
        "module_outputs": {},
    }

cities = [
    {"name": "Sapporo", "country": "Japan", "latitude": 43.0618, "longitude": 141.3545},
    {"name": "Los Angeles", "country": "United States", "latitude": 34.0522, "longitude": -118.2437},
]

errors = []
for city in cities:
    project = _base_project()
    _update_module0_location(project, city)
    common = project["common"]
    if common.get("project_location") == BASE_ADDRESS:
        errors.append(
            f"{city['name']}: common['project_location'] still holds the base "
            f"project's address ({BASE_ADDRESS!r}) instead of being replaced "
            f"for this city — Module 10 would mislabel every region with the "
            f"same address (PATCH_632 regression)."
        )
    if city["name"] not in str(common.get("project_location") or ""):
        errors.append(
            f"{city['name']}: common['project_location'] ({common.get('project_location')!r}) "
            f"does not contain the city name."
        )
    if common.get("city") != city["name"]:
        errors.append(f"{city['name']}: common['city'] was not updated correctly.")

if errors:
    for e in errors:
        print("[NG]", e)
    raise SystemExit(1)
print("REGIONAL_PROJECT_LOCATION_LABEL_PASS")
