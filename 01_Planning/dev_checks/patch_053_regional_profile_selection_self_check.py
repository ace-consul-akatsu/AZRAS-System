# -*- coding: utf-8 -*-
"""PATCH_053 self-check: Module 5 representative regional profile.

1. A profile picked from the list is kept (it was replaced by the automatic
   profile on the next <FocusIn> of the window, so Nagoya jumped back to Tokyo).
2. Automatic selection = nearest profile in the Project's country by the
   Project coordinates (Kasugai -> Nagoya), with the older fallbacks kept for
   Projects without coordinates.
3. The profile list is built from the profiles on disk (user-added profiles
   and regional-cost datasets), and a user profile can be added.
"""
import json
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import services.construction_cost_engine_v9_4 as E  # noqa: E402
import services.regional_profile_catalog as C  # noqa: E402

FAIL = []


def check(ok, label, detail=""):
    if ok:
        print(f"  [OK]   {label}")
    else:
        FAIL.append(f"{label} :: {detail}")
        print(f"  [NG]   {label} :: {detail}")


ADDRESS = "2-18-7 Matsukawadomachi, Kasugai-shi, Aichi-ken"
KASUGAI = (35.2475, 136.9722)

print("PATCH_053 self-check")
DB = C.load_construction_cost_database(ROOT)


def R(**common):
    return E.resolve_location_profile_from_project({"common": common}, DB)


print("-- 1. nearest profile in the country (coordinates)")
r = R(country="Japan", project_location=ADDRESS, latitude=KASUGAI[0], longitude=KASUGAI[1])
check(r["location_key"] == "Japan / Nagoya" and r["match_level"] == "nearest_in_country",
      "romanised Kasugai address + coordinates -> Nagoya (nearest)", f'{r["location_key"]} {r["match_level"]}')
check(r["nearest_distance_km"] is not None and r["nearest_distance_km"] < 30 and r["profile_is_regional_match"],
      "distance reported and treated as a regional match", r["nearest_distance_km"])
r = R(country="Japan", project_location="Hakata-ku, Fukuoka-shi", latitude=33.59, longitude=130.42)
check(r["location_key"] == "Japan / Nagoya" and r["profile_is_regional_match"] is False,
      "a distant city gets the nearest profile but no regional-match status", f'{r["location_key"]} {r["nearest_distance_km"]}')
r = R(country="Kenya", project_location="Nairobi", latitude=-1.29, longitude=36.82)
check(r["match_level"] == "nearest_outside_country", "a country without profiles is reported as outside the country", r["match_level"])
r = R(country="Japan", city="名古屋市", latitude=35.0, longitude=139.0)
check(r["match_level"] == "matched_city" and r["location_key"] == "Japan / Nagoya", "a named city still wins over distance", r["match_level"])

print("-- 2. fallbacks without coordinates")
r = R(country="Japan", project_location=ADDRESS)
check(r["location_key"] == "Japan / Nagoya" and r["match_level"] == "matched_prefecture",
      "romanised 'Aichi-ken' -> Nagoya without coordinates", f'{r["location_key"]} {r["match_level"]}')
r = R(country="Japan", project_location="Hakata-ku, Fukuoka-shi")
check(r["location_key"] == "Japan / Tokyo" and r["match_level"] == "country_reference_fallback",
      "no coordinates and no match -> country reference city (unchanged)", f'{r["location_key"]} {r["match_level"]}')
r = R(country="Japan", project_location="Kamiemachi, Fukuoka")
check(r["location_key"] == "Japan / Tokyo", "'mie' is matched as a whole word only", r["location_key"])

print("-- 3. built-in profiles: coordinates added, prices unchanged")
raw = json.loads((ROOT / "data" / C.DATABASE_FILE).read_text(encoding="utf-8"))["locations"]
check(all(C.location_coordinates(v) for k, v in raw.items() if k != "User Defined"),
      "every built-in city profile has coordinates")
tokyo = dict(raw["Japan / Tokyo"])
check((tokyo["material_index"], tokyo["labor_index"], tokyo["productivity_index"]) == (112.0, 118.0, 95.0)
      and raw["Japan / Nagoya"]["labor_index"] == 105.0, "indices unchanged")

print("-- 4. profile list from disk + user profile")
tmp = Path(tempfile.mkdtemp())
(tmp / "data" / "regional_cost").mkdir(parents=True)
shutil.copy(ROOT / "data" / C.DATABASE_FILE, tmp / "data" / C.DATABASE_FILE)
(tmp / "data" / "regional_cost" / "IT_Milan_2026.json").write_text(json.dumps({
    "region_key": "Italy / Milan", "currency": "EUR", "data_date": "2026-05-01",
    "regional_indices": {"material_index": 90, "labor_index": 92, "productivity_index": 97},
    "latitude": 45.46, "longitude": 9.19}), encoding="utf-8")
builtin = C.builtin_location_keys(tmp)
prof = C.build_user_profile("Japan", "Fukuoka", 33.59, 130.40, "jpy", 2026, 101, 103, 99, "test")
path = C.save_user_profile(tmp, prof, builtin)
check(path.name == "Japan_Fukuoka.json" and path.parent.name == "regional_profiles", "user profile saved", str(path))
db2 = C.load_construction_cost_database(tmp)
keys = list(db2["locations"])
check("Japan / Fukuoka" in keys and "Italy / Milan" in keys and keys[-1] == "User Defined",
      "user profile and dataset profile appear in the list (User Defined last)", keys[-4:])
check(db2["locations"]["Japan / Fukuoka"]["currency"] == "JPY" and db2["locations"]["Japan / Fukuoka"]["labor_index"] == 103.0,
      "user profile values loaded")
r = E.resolve_location_profile_from_project({"common": {"country": "Japan", "project_location": "Hakata", "latitude": 33.59, "longitude": 130.42}}, db2)
check(r["location_key"] == "Japan / Fukuoka" and r["profile_is_regional_match"], "an added profile is used by the nearest selection", r["location_key"])
for bad in (("Japan", "Tokyo"),):
    try:
        C.save_user_profile(tmp, C.build_user_profile(bad[0], bad[1], 35, 139, "JPY", 2026, 1, 1, 1), builtin)
        check(False, "a built-in profile cannot be replaced")
    except ValueError:
        check(True, "a built-in profile cannot be replaced")
for args in (("Japan", "", 35, 139, "JPY", 2026, 1, 1, 1), ("Japan", "X", 135, 139, "JPY", 2026, 1, 1, 1),
             ("Japan", "X", 35, 139, "YEN!", 2026, 1, 1, 1), ("Japan", "X", 35, 139, "JPY", 2026, 0, 1, 1)):
    try:
        C.build_user_profile(*args)
        check(False, "invalid profile input is refused", args)
    except ValueError:
        pass
check(True, "invalid profile input is refused")
src_pc = (ROOT / "core" / "project_coordinator.py").read_text(encoding="utf-8")
check("load_construction_cost_database(root_dir)" in src_pc, "automatic recalculation loads the same profile catalog")

print("-- 5. Module 5 window: a manual choice survives <FocusIn>")
try:
    import tkinter as tk
    _p = tk.Tk(); _p.destroy()
    have_display = True
except Exception as exc:  # noqa: BLE001
    have_display = False
    print(f"  [SKIP] no display: {str(exc)[:60]}")
if have_display:
    import module5.app as M

    class Ctx:
        def __init__(self, project, path):
            self.project, self.path, self.display_path = project, path, str(path)

        def reload(self):
            return json.loads(json.dumps(self.project))

        def synchronize_from_disk(self):
            return json.loads(json.dumps(self.project))

    project = {"project_id": "P", "common": {"country": "Japan", "project_location": ADDRESS,
                                            "latitude": KASUGAI[0], "longitude": KASUGAI[1]}, "module_outputs": {}}
    root = tk.Tk(); root.withdraw()
    app = M.Module5App(root, ROOT, language="ja", project_context=Ctx(project, tmp / "P.json"))
    check(app.location.get() == "Japan / Nagoya", "auto selection on open -> Nagoya", app.location.get())
    check("近隣プロファイル" in app.project_cost_location.get() and "国の基準都市" not in app.project_cost_location.get(),
          "header says nearest profile, not country reference", app.project_cost_location.get())
    app.location.set("Japan / Tokyo")
    app.location_cb.event_generate("<<ComboboxSelected>>")
    root.update()
    app.refresh_project_from_context()
    check(app.location.get() == "Japan / Tokyo" and app.labor_index.get() in ("118.0", "118"),
          "manual Tokyo survives the FocusIn refresh", f"{app.location.get()} {app.labor_index.get()}")
    app.location.set("Japan / Nagoya"); app._on_location_selected()
    app.labor_index.set("107.5")
    app.refresh_project_from_context(); app.refresh_project_from_context()
    check(app.location.get() == "Japan / Nagoya" and app.labor_index.get() == "107.5",
          "manual Nagoya and a typed index survive repeated FocusIn", f"{app.location.get()} {app.labor_index.get()}")
    app.location.set("Japan / Sapporo"); app._on_location_selected()
    app.reset_location_to_auto()
    check(app.location.get() == "Japan / Nagoya" and app._location_selection_mode == "auto", "'back to automatic' returns to Nagoya")
    # Auto mode: unchanged Project -> a typed index is not reset on FocusIn either.
    app.labor_index.set("106")
    app.refresh_project_from_context()
    check(app.labor_index.get() == "106", "auto mode does not re-apply the profile when nothing changed", app.labor_index.get())
    texts = []

    def walk(w):
        for c in w.winfo_children():
            try:
                texts.append(str(c.cget("text")))
            except Exception:  # noqa: BLE001
                pass
            walk(c)
    walk(app)
    check("自動選択に戻す" in texts and "地域プロファイル追加" in texts, "the two new buttons exist")
    src = (ROOT / "module5" / "app.py").read_text(encoding="utf-8")
    check('"location_selection_mode": self._location_selection_mode' in src, "selection mode is saved in the Module 5 snapshot")
    try:
        app.destroy(); root.destroy()
    except Exception:  # noqa: BLE001
        pass

shutil.rmtree(tmp, ignore_errors=True)
print()
if FAIL:
    print(f"PATCH_053 self-check: FAIL ({len(FAIL)})")
    for f in FAIL:
        print("  - " + f)
    sys.exit(1)
print("PATCH_053 self-check: PASS")
