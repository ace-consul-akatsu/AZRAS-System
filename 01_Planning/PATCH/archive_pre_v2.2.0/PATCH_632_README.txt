PATCH_632 — Module 9/10: fix regional JSON legend showing base address for all cities

Problem:
In Module 10 (地域比較 / Regional Comparison), every generated region
(Sapporo, Los Angeles, Dubai, Bangkok, Sydney, Berlin, Oslo, ...) was
labeled with the ORIGINAL base project's address (e.g.
"愛知県春日井市松河戸町2-18-7") in the chart legend and every table's
"地域/Region" column, even though the underlying monthly/annual energy
and CO2 figures correctly differed per city (confirming the EPW/climate
calculation itself was not affected).

Root cause:
regional_analysis/project_generator.py:_update_module0_location() writes
country/city/address/latitude/longitude into project["common"] for each
derived regional Project JSON, but did not update
project["common"]["project_location"].

project_location is the field behind Module 0's "都市・所在地 / City /
Location" input and is documented in module0/app.py as authoritative.
build_module10_snapshot() (same file) derives the label with:
    city_name = str(common.get("project_location") or common.get("city") or ...)
so project_location, left unchanged at the original base address, always
won over the correctly-updated city field.

Fix:
_update_module0_location() now also sets
    common["project_location"] = address
alongside country/city/address/lat/lon, so every derived regional JSON's
Module 0 is fully replaced (matching the documented intent: "派生JSONの
Module 0（国・都市・所在地・緯度・経度）も各地域へ置き換えます").

Action required after applying this patch:
Existing regional JSON files already generated before this patch (e.g.
20_JSON/260914_AZRAS_002/*) still have the old project_location baked in
and will keep showing the wrong label until regenerated. In Module 9,
re-run "追加地域JSONを計算・物件フォルダへ保存" (or delete and re-add
the cities) to regenerate them with the fix applied, then reload Module
10 with "地域別Project JSONを再読込".

Files changed:
- regional_analysis/project_generator.py (_update_module0_location only)
