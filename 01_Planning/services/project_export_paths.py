from __future__ import annotations

import json
import os
import re
import sys
from datetime import datetime, timezone
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

def _remove_unset_method_token(value: Any) -> str:
    """Remove the legacy placeholder ``工法未設定`` from generated names."""
    text = safe_name(value, "")
    parts = [part for part in text.split("_") if part and part != "工法未設定"]
    return "_".join(parts)


def project_method_name(project: dict[str, Any] | None) -> str:
    common = (project or {}).get("common", {})
    return safe_name(
        common.get("construction_method_detail_name_ja")
        or common.get("construction_method_name_ja")
        or common.get("construction_method_id")
        or "",
        "",
    )


def project_name(project: dict[str, Any] | None) -> str:
    common = (project or {}).get("common", {})
    return safe_name(common.get("project_name") or "Project")


def default_project_filename(project: dict[str, Any] | None, extension: str = ".json") -> str:
    stamp = datetime.now(timezone.utc).strftime("%y%m%d")
    method = _remove_unset_method_token(project_method_name(project))
    name = _remove_unset_method_token(project_name(project)) or "Project"
    # Avoid duplicated dates when the user already included YYMMDD in the
    # Project Name (e.g. ``260831_テスト``).
    name_without_stamp = name[len(stamp) + 1:] if name.startswith(stamp + "_") else name
    if method:
        return f"{stamp}_{method}_{name_without_stamp}{extension}"
    return f"{stamp}_{name_without_stamp}{extension}"


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


def configured_price_table_directory() -> Path | None:
    """PATCH_054: folder chosen for the regional unit-price tables (地域単価表).

    None when the user has not chosen one; the caller then uses the default
    ``<Project JSON folder>/Regional_Unit_Price_Tables``.  The folder is used
    exactly as chosen (no sub-folder is added).
    """
    raw = load_storage_settings().get("regional_price_table_directory")
    if not raw:
        return None
    try:
        path = Path(str(raw)).expanduser()
        path.mkdir(parents=True, exist_ok=True)
        return path
    except Exception:
        return None


def set_configured_price_table_directory(directory: str | Path | None) -> Path | None:
    """PATCH_054: remember (or clear with None) the regional unit-price table folder."""
    settings = load_storage_settings()
    if directory:
        path = Path(directory).expanduser().resolve()
        path.mkdir(parents=True, exist_ok=True)
        settings["regional_price_table_directory"] = str(path)
    else:
        settings.pop("regional_price_table_directory", None)
        path = None
    settings["updated_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    save_storage_settings(settings)
    return path


def set_configured_json_directory(directory: str | Path | None) -> Path | None:
    settings = load_storage_settings()
    if directory:
        path = Path(directory).expanduser().resolve()
        path.mkdir(parents=True, exist_ok=True)
        settings["json_save_directory"] = str(path)
        settings["updated_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
        save_storage_settings(settings)
        return path
    settings.pop("json_save_directory", None)
    settings["updated_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
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
    """Return the nearest ``Data`` ancestor directory, or a safe parent fallback.

    PATCH_026 fix: this used to also treat a folder literally named ``json``
    (case-insensitive) as one level below the real root and jump up to its
    parent. That heuristic only made sense for the portable ``EXE/Data/JSON``
    fallback layout -- and that case is already handled by the ``Data``
    ancestor search above. When a user explicitly configures their own save
    folder and that folder happens to be named ``JSON`` (e.g. via Module 0's
    "Select Project JSON/CSV folder" dialog), the old code silently saved one
    directory above the folder the user actually selected. Removing the
    ``json``-name special case makes an explicitly selected folder authoritative.
    """
    path = Path(path).resolve()
    start = path if path.is_dir() else path.parent
    for candidate in (start, *start.parents):
        if candidate.name.casefold() == "data":
            return candidate
    return start


def project_bundle_name(project_path: str | Path) -> str:
    """One folder per property for Project JSON and every module export.

    New AZRAS projects use the clean Project name itself as the folder name.
    The historical ``_module0_data`` suffix is no longer added.
    """
    project_path = Path(project_path)
    stem = _remove_unset_method_token(project_path.stem) or "Project"
    legacy_suffix = "_module0_data"
    if stem.casefold().endswith(legacy_suffix.casefold()):
        stem = stem[:-len(legacy_suffix)] or "Project"
    return stem


def project_bundle_directory(project_path: str | Path) -> Path:
    project_path = Path(project_path).resolve()
    parent_name = project_path.parent.name.casefold()
    # Existing legacy ``*_module0_data`` folders remain usable when an old
    # project is opened, but new project folders are created without that
    # suffix.  If the user deliberately saves inside an existing project
    # folder, reuse that folder instead of nesting another one.
    if parent_name.endswith("_module0_data"):
        folder = project_path.parent
    elif parent_name == project_bundle_name(project_path).casefold():
        folder = project_path.parent
    else:
        # A current-format project folder is named after its first/basic JSON.
        # When a later detailed/final JSON is saved into that same folder, the
        # new file name is different from the folder name.  Reuse the folder if
        # it already contains its anchor ``<folder name>.json`` Project file.
        anchor = project_path.parent / f"{project_path.parent.name}.json"
        if anchor.exists():
            folder = project_path.parent
        else:
            folder = _data_root_from_path(project_path) / project_bundle_name(project_path)
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def unified_project_json_path(selected_path: str | Path) -> Path:
    """Route a selected/new JSON filename into the property's single folder.

    The obsolete ``工法未設定`` placeholder is removed from both the JSON name
    and its bundle folder so it cannot survive through an old suggested name.
    """
    selected_path = Path(selected_path).resolve()
    clean_stem = _remove_unset_method_token(selected_path.stem) or "Project"
    clean_path = selected_path.with_name(clean_stem + selected_path.suffix)
    folder = project_bundle_directory(clean_path)
    return folder / clean_path.name


def project_output_directory(project_path: str | Path, module_no: int) -> Path:
    # module_no is retained for API compatibility. All modules now share one
    # property folder instead of creating module0_data, module2_data, ...
    return project_bundle_directory(project_path)


def project_data_directory(project_path: str | Path, *, create: bool = False) -> Path:
    """Return the explicit per-Project runtime-data folder.

    PATCH_536: runtime downloads/caches must not create an unrelated top-level
    ``Data`` folder beside the application.  They belong inside the Project
    bundle so the user can see exactly which Project owns them.
    """
    folder = project_bundle_directory(project_path) / "Data"
    if create:
        folder.mkdir(parents=True, exist_ok=True)
    return folder


def weather_method_directory(data_root: str | Path, project: dict[str, Any] | None, *, create: bool = False) -> Path:
    """Return the method weather folder without creating it unless requested."""
    method = project_method_name(project)
    folder_name = f"{method}_気象情報" if method else "気象情報"
    folder = Path(data_root).resolve() / folder_name
    if create:
        folder.mkdir(parents=True, exist_ok=True)
    return folder


def default_export_path(project_path: str | Path, module_no: int, suffix: str = ".csv", label: str | None = None) -> Path:
    folder = project_output_directory(project_path, module_no)
    base = safe_name(label or MODULE_EXPORT_NAMES.get(module_no, f"Module{module_no}_出力"))
    return folder / f"{base}{suffix}"
