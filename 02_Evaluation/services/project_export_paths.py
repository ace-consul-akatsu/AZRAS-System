from __future__ import annotations

import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

_INVALID = re.compile(r'[<>:"/\\|?*\x00-\x1f]')

MODULE_EXPORT_NAMES = {
    2: "Module2_時間別環境計算",
    3: "Module3_修繕更新シナリオ",
    4: "Module4_長期環境評価",
    5: "Module5_建設費内訳",
    6: "Module6_修繕更新解体積算",
    7: "Module7_災害復旧レジリエンス評価",
    8: "Module8_200年事業収支",
    9: "Module9_地域別Project_JSON",
    10: "Module10_地域比較",
}


def safe_name(value: Any, fallback: str = "Project") -> str:
    text = str(value or "").strip()
    text = _INVALID.sub("_", text)
    text = re.sub(r"\s+", "_", text).strip(" ._")
    return text or fallback


def project_method_name(project: dict[str, Any] | None) -> str:
    common = (project or {}).get("common", {})
    return safe_name(
        common.get("construction_method_detail_name_ja")
        or common.get("construction_method_name_ja")
        or common.get("construction_method_id")
        or "工法未設定",
        "工法未設定",
    )


def project_name(project: dict[str, Any] | None) -> str:
    common = (project or {}).get("common", {})
    return safe_name(common.get("project_name") or "Project")


def default_project_filename(project: dict[str, Any] | None, extension: str = ".json") -> str:
    stamp = datetime.now().strftime("%y%m%d")
    return f"{stamp}_{project_method_name(project)}_{project_name(project)}{extension}"


def application_directory(root_dir: str | Path | None = None) -> Path:
    """Return the folder containing the distributed EXE.

    In a PyInstaller build, root_dir often points inside ``_internal``.  Using
    sys.executable keeps the portable ``EXE/Data/JSON`` fallback beside the EXE.
    """
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    if root_dir is not None:
        return Path(root_dir).resolve()
    return Path.cwd().resolve()


def storage_config_path() -> Path:
    base = Path(os.environ.get("APPDATA") or Path.home()) / "AZRAS_Platform"
    base.mkdir(parents=True, exist_ok=True)
    return base / "storage_settings.json"


def load_storage_settings() -> dict[str, Any]:
    path = storage_config_path()
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def save_storage_settings(settings: dict[str, Any]) -> None:
    path = storage_config_path()
    path.write_text(json.dumps(settings, ensure_ascii=False, indent=2), encoding="utf-8")


def configured_json_directory() -> Path | None:
    raw = load_storage_settings().get("json_save_directory")
    if not raw:
        return None
    try:
        path = Path(str(raw)).expanduser()
        path.mkdir(parents=True, exist_ok=True)
        return path
    except Exception:
        return None


def set_configured_json_directory(directory: str | Path | None) -> Path | None:
    settings = load_storage_settings()
    if directory:
        path = Path(directory).expanduser().resolve()
        path.mkdir(parents=True, exist_ok=True)
        settings["json_save_directory"] = str(path)
        settings["updated_at"] = datetime.now().isoformat(timespec="seconds")
        save_storage_settings(settings)
        return path
    settings.pop("json_save_directory", None)
    settings["updated_at"] = datetime.now().isoformat(timespec="seconds")
    save_storage_settings(settings)
    return None


def find_json_directory(root_dir: str | Path) -> Path:
    """Resolve the default Project JSON folder.

    Priority:
      1. User-selected folder stored in AppData.
      2. Portable fallback beside the EXE: ``EXE/Data/JSON``.

    Existing projects and their CSV exports remain beside the opened JSON file.
    """
    configured = configured_json_directory()
    if configured is not None:
        return configured

    portable = application_directory(root_dir) / "Data" / "JSON"
    portable.mkdir(parents=True, exist_ok=True)
    return portable


def _data_root_from_path(path: str | Path) -> Path:
    """Return the nearest Data directory, or a safe parent fallback."""
    path = Path(path).resolve()
    start = path if path.is_dir() else path.parent
    for candidate in (start, *start.parents):
        if candidate.name.casefold() == "data":
            return candidate
    if start.name.casefold() == "json":
        return start.parent
    return start


def project_bundle_name(project_path: str | Path) -> str:
    """One folder per property for Project JSON and every module export."""
    project_path = Path(project_path)
    stem = safe_name(project_path.stem)
    suffix = "_module0_data"
    if stem.casefold().endswith(suffix.casefold()):
        return stem
    return f"{stem}{suffix}"


def project_bundle_directory(project_path: str | Path) -> Path:
    project_path = Path(project_path).resolve()
    # If the JSON is already inside its unified folder, reuse it.
    if project_path.parent.name.casefold() == project_bundle_name(project_path).casefold():
        folder = project_path.parent
    else:
        folder = _data_root_from_path(project_path) / project_bundle_name(project_path)
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def unified_project_json_path(selected_path: str | Path) -> Path:
    """Route a selected/new JSON filename into the property's single folder."""
    selected_path = Path(selected_path).resolve()
    folder = project_bundle_directory(selected_path)
    return folder / selected_path.name


def project_output_directory(project_path: str | Path, module_no: int) -> Path:
    # module_no is retained for API compatibility. All modules now share one
    # property folder instead of creating module0_data, module2_data, ...
    return project_bundle_directory(project_path)


def weather_method_directory(data_root: str | Path, project: dict[str, Any] | None) -> Path:
    """Store all regional weather files together under one method folder."""
    folder = Path(data_root).resolve() / f"{project_method_name(project)}_気象情報"
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def default_export_path(project_path: str | Path, module_no: int, suffix: str = ".csv", label: str | None = None) -> Path:
    folder = project_output_directory(project_path, module_no)
    base = safe_name(label or MODULE_EXPORT_NAMES.get(module_no, f"Module{module_no}_出力"))
    return folder / f"{base}{suffix}"
