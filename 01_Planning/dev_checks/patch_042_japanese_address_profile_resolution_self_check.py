# -*- coding: utf-8 -*-
"""PATCH_042 self-check: Japanese project addresses resolve to the registered
regional profile instead of silently falling back to the national reference
city.
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import services.construction_cost_engine_v9_4 as E  # noqa: E402

FAIL = []


def check(ok, label, detail=""):
    if ok:
        print(f"  [OK]   {label}")
    else:
        FAIL.append(f"{label} :: {detail}")
        print(f"  [NG]   {label} :: {detail}")


DB = json.loads((ROOT / "data" / "construction_cost_database_v9_4.json").read_text(encoding="utf-8"))


def R(country, city, address=None):
    return E.resolve_location_profile_from_project(
        {"common": {"country": country, "city": city, "project_location": address or city}}, DB)


print("PATCH_042 self-check")
print("-- 1. the reported case: a full Aichi street address")
r = R("Japan", "愛知県春日井市松河戸町2-18-7")
check(r["location_key"] == "Japan / Nagoya", "Kasugai resolves to Nagoya, not Tokyo", r["location_key"])
check(r["match_level"] == "matched_city" and r["matched_alias"] == "春日井",
      "it is reported as an alias city match", f'{r["match_level"]} {r["matched_alias"]}')
check(r["profile_is_regional_match"] is True and r["profile_is_country_fallback"] is False,
      "regional-match flags are set")

print("-- 2. prefecture fallback only where a representative city exists")
for addr, key, pref in (("愛知県豊田市元城町1-1", "Japan / Nagoya", "愛知県"),
                        ("岐阜県岐阜市司町40-1", "Japan / Nagoya", "岐阜県"),
                        ("三重県津市広明町13", "Japan / Nagoya", "三重県"),
                        ("北海道旭川市6条通9丁目", "Japan / Sapporo", "北海道"),
                        ("神奈川県横浜市中区港町1-1", "Japan / Tokyo", "神奈川県")):
    r = R("Japan", addr)
    check(r["location_key"] == key and r["match_level"] == "matched_prefecture" and r["matched_prefecture"] == pref,
          f"{pref} resolves to {key} as a prefecture match", f'{r["location_key"]} {r["match_level"]}')
r = R("Japan", "大阪府大阪市北区梅田1-1")
check(r["match_level"] == "country_reference_fallback",
      "a prefecture with no registered representative city is still reported honestly as a fallback",
      r["match_level"])

print("-- 3. existing behaviour is unchanged")
for city, key in (("名古屋", "Japan / Nagoya"), ("東京", "Japan / Tokyo"), ("札幌", "Japan / Sapporo"),
                  ("Nagoya", "Japan / Nagoya"), ("New York", "United States / New York")):
    r = R("Japan" if key.startswith("Japan") else "United States", city)
    check(r["location_key"] == key and r["match_level"] == "matched_city",
          f"{city} still resolves to {key} as a city match", f'{r["location_key"]} {r["match_level"]}')
r = R("United States", "IND HEAD PARK, イリノイ州 60525 アメリカ合衆国")
check(r["location_key"] == "United States / New York" and r["match_level"] == "country_reference_fallback",
      "an unregistered US city keeps the PATCH_039 country-fallback report", f'{r["location_key"]} {r["match_level"]}')
r = R("Japan", "愛知県名古屋市中区三の丸3-1-1")
check(r["location_key"] == "Japan / Nagoya" and r["matched_alias"] == "名古屋",
      "the longer, more specific alias wins inside a full address", str(r["matched_alias"]))

print("-- 4. a saved profile is never switched silently")
m5 = (ROOT / "module5" / "app.py").read_text(encoding="utf-8")
check('"matched_prefecture_representative_city"' in m5, "Module 5 recognises the prefecture match")
check("案件所在地に対応する代表プロファイルは" in m5 and "The project address resolves to" in m5,
      "a saved profile that differs from the address is reported, not overwritten")

print()
if FAIL:
    print("[NG] PATCH_042 self-check FAILED:")
    for f in FAIL:
        print("   -", f)
    raise SystemExit(1)
print("PATCH_042_JAPANESE_ADDRESS_PROFILE_RESOLUTION_PASS")
