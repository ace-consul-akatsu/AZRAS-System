# -*- coding: utf-8 -*-
"""PATCH_055 self-check: user-chosen folders for regional-cost JSON and regional profiles.

Before, both were written only inside the application folder
(data/regional_cost, data/regional_profiles) and were lost when the folder was
replaced with a full-version zip.  Now (same mechanism as the PATCH_054 price
table folder):
  * the folder is confirmed / changed when saving, and remembered;
  * the chosen folder AND the built-in/default folder are both read, so
    earlier files and the shipped datasets are still found;
  * the Module 5 calculation, the profile list and the automatic
    recalculation read the chosen folders.
"""
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
TMP = Path(tempfile.mkdtemp())
os.environ["APPDATA"] = str(TMP / "appdata")

import services.project_export_paths as P  # noqa: E402
import services.regional_profile_catalog as C  # noqa: E402
import services.construction_cost_engine_v9_4 as E  # noqa: E402

FAIL = []


def check(ok, label, detail=""):
    print(("  [OK]   " if ok else "  [NG]   ") + label + ("" if ok else f" :: {detail}"))
    if not ok:
        FAIL.append(label)


print("PATCH_055 self-check")
print("-- 1. settings")
for kind in ("price_table", "regional_cost", "regional_profile"):
    check(P.configured_user_data_directory(kind) is None, f"{kind}: not chosen by default")
rc_dir = TMP / "Dropbox" / "AZRAS_UserData" / "regional_cost"
pf_dir = TMP / "Dropbox" / "AZRAS_UserData" / "regional_profiles"
P.set_configured_user_data_directory("regional_cost", rc_dir)
P.set_configured_user_data_directory("regional_profile", pf_dir)
st = P.load_storage_settings()
check(st.get("regional_cost_user_directory") == str(rc_dir.resolve()) and st.get("regional_profile_directory") == str(pf_dir.resolve()),
      "both folders remembered in storage_settings.json", st)
check(P.configured_price_table_directory() is None and st.get("json_save_directory") is None,
      "price-table and Project JSON settings untouched")

print("-- 2. regional profiles: chosen folder + default folder are both read")
app_root = TMP / "app"
(app_root / "data" / "regional_profiles").mkdir(parents=True)
(app_root / "data" / "regional_cost").mkdir(parents=True)
shutil.copy(ROOT / "data" / C.DATABASE_FILE, app_root / "data" / C.DATABASE_FILE)
builtin = C.builtin_location_keys(app_root)
old = C.build_user_profile("Japan", "Kasugai", 35.2475, 136.9722, "JPY", 2026, 105, 106, 96)
(app_root / "data" / "regional_profiles" / "Japan_Kasugai.json").write_text(json.dumps(old), encoding="utf-8")
new = C.build_user_profile("Japan", "Fukuoka", 33.59, 130.40, "JPY", 2026, 101, 103, 99)
path = C.save_user_profile(app_root, new, builtin)
check(path.parent.resolve() == pf_dir.resolve(), "a new profile is saved in the chosen folder", path)
db = C.load_construction_cost_database(app_root)
check("Japan / Fukuoka" in db["locations"] and "Japan / Kasugai" in db["locations"],
      "profiles from both folders are in the list", sorted(db["locations"])[-5:])

print("-- 3. regional-cost JSON: chosen folder is searched by the calculation")
rc_dir.mkdir(parents=True, exist_ok=True)
ds = json.loads((ROOT / "data" / "regional_cost" / "JP_Nagoya_2026.json").read_text(encoding="utf-8"))
ds["data_date"] = "2027-02-01"
(rc_dir / "JP_Nagoya_2027_02_01.json").write_text(json.dumps(ds, ensure_ascii=False), encoding="utf-8")
loc = dict(json.loads((ROOT / "data" / C.DATABASE_FILE).read_text(encoding="utf-8"))["locations"]["Japan / Nagoya"])
out = E.load_external_regional_cost_dataset(loc)
check(str(out.get("external_dataset_path", "")).endswith("JP_Nagoya_2027_02_01.json"),
      "the newer file in the chosen folder is used (built-in 2026 file still a candidate)", out.get("external_dataset_path"))
check(int(out.get("external_dataset_candidate_count") or 0) >= 2, "built-in file still searched", out.get("external_dataset_candidate_count"))
(rc_dir / "IT_Milan_2026.json").write_text(json.dumps({
    "region_key": "Italy / Milan", "currency": "EUR", "data_date": "2026-05-01",
    "regional_indices": {"material_index": 90, "labor_index": 92, "productivity_index": 97}}), encoding="utf-8")
db = C.load_construction_cost_database(app_root)
check("Italy / Milan" in db["locations"] and Path(db["locations"]["Italy / Milan"]["dataset_file"]).is_absolute(),
      "a dataset with a new region in the chosen folder appears as a profile")

print("-- 4. Module 5")
try:
    import tkinter as tk
    _r = tk.Tk(); _r.destroy(); have = True
except Exception as exc:  # noqa: BLE001
    have = False; print(f"  [SKIP] no display: {str(exc)[:60]}")
if have:
    import module5.app as M
    root = tk.Tk(); root.withdraw()
    app = M.Module5App(root, ROOT, language="ja")
    check(app._regional_cost_directory().resolve() == rc_dir.resolve(), "import/edit writes to the chosen regional-cost folder")
    dirs = [d.resolve() for d in app._regional_cost_read_directories()]
    check(dirs[0] == rc_dir.resolve() and (ROOT / "data" / "regional_cost").resolve() in dirs, "reads chosen folder first, then built-in", dirs)
    app.location.set("Japan / Nagoya")
    check(str(app._latest_regional_cost_json("Japan / Nagoya")).endswith("JP_Nagoya_2027_02_01.json"), "latest dataset found in the chosen folder",
          app._latest_regional_cost_json("Japan / Nagoya"))

    def press(*labels):
        def drive():
            dlg = [w for w in app.winfo_children() if isinstance(w, tk.Toplevel)][-1]
            b = {}

            def walk(w):
                for c in w.winfo_children():
                    try:
                        b[str(c.cget("text"))] = c
                    except Exception:  # noqa: BLE001
                        pass
                    walk(c)
            walk(dlg)
            for x in labels:
                b[x].invoke()
        app.after(200, drive)

    press("キャンセル")
    check(app._ask_save_folder("regional_cost", "t") is None, "cancel in the folder dialog")
    press("この保存先に保存")
    check(app._ask_save_folder("regional_cost", "t").resolve() == rc_dir.resolve(), "'save in this folder'")
    press("この保存先で登録")
    check(app._ask_price_table_folder("t") is not None, "price-table dialog unchanged (PATCH_054 button)")

    # Import flow end to end into the chosen folder.
    src = TMP / "import_src.json"
    ds2 = dict(ds); ds2["data_date"] = "2027-03-01"
    src.write_text(json.dumps(ds2, ensure_ascii=False), encoding="utf-8")
    M.filedialog.askopenfilename = lambda **k: str(src)
    msgs = []
    M.messagebox.showinfo = lambda *a, **k: msgs.append(a)
    M.messagebox.showerror = lambda *a, **k: msgs.append(("ERR",) + a)
    M.messagebox.askyesno = lambda *a, **k: True
    press("この保存先に保存")
    app.import_regional_cost_dataset()
    check((rc_dir / "JP_Nagoya_2027_03_01.json").exists() and not (ROOT / "data" / "regional_cost" / "JP_Nagoya_2027_03_01.json").exists(),
          "imported JSON saved in the chosen folder, not in the application", [m[0] for m in msgs])
    press("キャンセル")
    n_before = len(list(rc_dir.glob("*.json")))
    ds3 = dict(ds); ds3["data_date"] = "2027-04-01"; src.write_text(json.dumps(ds3, ensure_ascii=False), encoding="utf-8")
    app.import_regional_cost_dataset()
    check(len(list(rc_dir.glob("*.json"))) == n_before, "cancelling the folder dialog imports nothing")

    # Profile dialog shows the folder.
    app.open_add_location_profile_dialog()
    dlg = [w for w in app.winfo_children() if isinstance(w, tk.Toplevel)][-1]
    entries = []

    def walk(w):
        for c in w.winfo_children():
            if isinstance(c, tk.Entry):
                entries.append(c.get())
            walk(c)
    walk(dlg)
    check(str(pf_dir.resolve()) in entries or str(pf_dir) in entries, "profile dialog shows the chosen folder", entries[-1:])
    dlg.destroy()

    app.show_user_data_folders()
    win = [w for w in app.winfo_children() if isinstance(w, tk.Toplevel)][-1]
    texts = []

    def walk2(w):
        for c in w.winfo_children():
            try:
                texts.append(str(c.cget("text")))
            except Exception:  # noqa: BLE001
                pass
            walk2(c)
    walk2(win)
    check(all(t in texts for t in ("地域単価表", "地域単価JSON（手動取込・編集）", "地域プロファイル（追加分）")),
          "'user data folders' window lists the three folders")
    win.destroy()
    app.reset_user_folder("regional_cost")
    check(app._regional_cost_directory().resolve() == (ROOT / "data" / "regional_cost").resolve(), "'use default' returns to data/regional_cost")
    try:
        app.destroy(); root.destroy()
    except Exception:  # noqa: BLE001
        pass

shutil.rmtree(TMP, ignore_errors=True)
print()
if FAIL:
    print(f"PATCH_055 self-check: FAIL ({len(FAIL)})")
    sys.exit(1)
print("PATCH_055 self-check: PASS")
