"""Regression check for PATCH_026: selecting a folder literally named "JSON" as
the Project JSON/CSV save destination must save INSIDE that folder, not one
level above it. See services/project_export_paths.py: _data_root_from_path().
"""
from pathlib import Path
import sys, tempfile

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from services.project_export_paths import project_bundle_directory

with tempfile.TemporaryDirectory() as tmp:
    tmp = Path(tmp)

    # A: brand-new project saved directly into a user-chosen folder named "JSON"
    # with no "Data" ancestor anywhere above it (e.g. .../AZRAS_v2.2.0/JSON).
    custom_json = tmp / "Dropbox" / "015_AZRAS" / "AZRAS_v2.2.0" / "JSON"
    custom_json.mkdir(parents=True)
    new_file = custom_json / "260918_RC_Rahmen_Sample.json"
    folder = project_bundle_directory(new_file)
    if folder.parent != custom_json:
        print("[NG] new project bundle escaped the selected JSON folder:", folder)
        raise SystemExit(1)

    # B: legacy portable fallback layout EXE/Data/JSON must still resolve under Data,
    # not under Data/JSON.
    portable_json = tmp / "AZRAS_EXE" / "Data" / "JSON"
    portable_json.mkdir(parents=True)
    folder2 = project_bundle_directory(portable_json / "MyProject.json")
    if folder2.parent != (tmp / "AZRAS_EXE" / "Data"):
        print("[NG] portable EXE/Data/JSON layout regressed:", folder2)
        raise SystemExit(1)

    # C: re-saving an already-bundled project (parent folder name == project name)
    # must stay in place, not move.
    existing_bundle = custom_json / "260918_AZRAS_Sample"
    existing_bundle.mkdir(parents=True)
    existing_file = existing_bundle / "260918_AZRAS_Sample.json"
    existing_file.write_text("{}")
    folder3 = project_bundle_directory(existing_file)
    if folder3 != existing_bundle:
        print("[NG] existing bundled project was moved:", folder3)
        raise SystemExit(1)

print("JSON_SAVE_FOLDER_REGRESSION_PASS")
