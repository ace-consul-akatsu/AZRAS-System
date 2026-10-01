AZRAS Planning - user regional profiles (PATCH_053)
====================================================

Module 5 「地域プロファイル追加」 (Add regional profile) saves one JSON file per
city here: <Country>_<City>.json.  Every file in this folder is shown in the
代表地域プロファイル list and is used by the nearest-city automatic selection.

Fields: location_key ("Country / City"), country, city, latitude, longitude,
currency (3 letters), year, material_index, labor_index, productivity_index,
source_note.  Built-in profile names cannot be replaced.

data/regional_cost/*.json datasets whose region_key is not a built-in profile
and which carry regional_indices + currency are listed as well.
