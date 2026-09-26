from __future__ import annotations

import copy
import csv
import tempfile
import sys
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any

from core.project_store import load_project, save_project


@dataclass
class CheckItem:
    section: str
    item: str
    status: str
    detail: str


MODULE_NAMES = {
    "ja": {
        "module0": "共通データ・座標",
        "module1": "図面・数量・建物性能",
        "module2": "環境・CO₂・エネルギー",
        "module3": "修繕・更新・解体シナリオ",
        "module4": "長期・200年環境評価",
        "module5": "建設費",
        "module6": "200年事業収支・資産価値",
        "module7": "修繕・更新・解体積算",
    },
    "en": {
        "module0": "Common Data and Coordinates",
        "module1": "Drawings, Quantities and Building Performance",
        "module2": "Environment, CO₂ and Energy",
        "module3": "Repair, Renewal and Demolition Scenarios",
        "module4": "Long-Term 200-Year Environmental Assessment",
        "module5": "Construction Cost",
        "module6": "200-Year Business Cash Flow and Asset Value",
        "module7": "Repair, Renewal and Demolition Cost Estimation",
    },
}

TEXT = {
    "ja": {
        "file": "ファイル", "not_found": "Project JSONが見つかりません。",
        "load": "読込", "roundtrip": "保存・再読込",
        "temporary_ok": "一時コピーで正常",
        "project_id_mismatch": "project_idが一致しません。",
        "project_name": "プロジェクト名", "country": "国",
        "building_use": "用途", "latitude": "緯度", "longitude": "経度",
        "not_entered": "未入力", "scale_link": "Module 0→1連動",
        "scale_item": "階数・各階床面積・延べ床面積",
        "scale_detail": "階数={storeys}, 各階={floors}, 延べ={gfa} m²",
        "scale_error": "Module 1でPDF解析後、Project JSONを更新保存してください。",
        "result_saved": "結果保存済み / updated={updated}", "unknown": "不明",
        "no_snapshot": "入力条件スナップショットなし",
        "not_calculated": "未計算または未保存", "link_status": "連動状態",
        "error": "エラー", "module_link": "Module連動",
        "prerequisite": "{module}の前提データ", "normal": "正常",
        "missing": "不足: {items}", "pdf_file": "PDFファイル",
        "weather_file": "気象ファイル", "annual_summary": "年間集計結果",
        "total_construction_cost": "総建設費", "zero_invalid": "0または無効",
        "cashflow_100": "200年キャッシュフロー",
        "cashflow_200": "200年事業収支", "years": "{count}年分",
        "app_structure": "アプリ構成",
        "required_files": "必須ファイル・フォルダー",
    },
    "en": {
        "file": "File", "not_found": "Project JSON was not found.",
        "load": "Load", "roundtrip": "Save and Reload",
        "temporary_ok": "Temporary-copy test passed",
        "project_id_mismatch": "The project_id values do not match.",
        "project_name": "Project Name", "country": "Country",
        "building_use": "Building Use", "latitude": "Latitude",
        "longitude": "Longitude", "not_entered": "Not entered",
        "scale_link": "Module 0→1 Link",
        "scale_item": "Storeys, Floor Areas and Gross Floor Area",
        "scale_detail": "Storeys={storeys}, floors={floors}, GFA={gfa} m²",
        "scale_error": "Run PDF analysis in Module 1 and update the Project JSON.",
        "result_saved": "Result saved / updated={updated}", "unknown": "Unknown",
        "no_snapshot": "No input-condition snapshot",
        "not_calculated": "Not calculated or not saved",
        "link_status": "Link Status", "error": "Error",
        "module_link": "Module Links",
        "prerequisite": "Prerequisites for {module}", "normal": "Normal",
        "missing": "Missing: {items}", "pdf_file": "PDF File",
        "weather_file": "Weather File",
        "annual_summary": "Annual Summary Results",
        "total_construction_cost": "Total Construction Cost",
        "zero_invalid": "Zero or invalid", "cashflow_100": "200-Year Cash Flow",
        "cashflow_200": "200-Year Business Cash Flow",
        "years": "{count} years", "app_structure": "Application Structure",
        "required_files": "Required Files and Folders",
    },
}

DEPENDENCY_REQUIREMENTS = {
    "module2": ["module1"], "module3": ["module1"],
    "module4": ["module2", "module3"], "module5": ["module1"],
    "module6": ["module5", "module7"],
    "module7": ["module3", "module5"],
}


def _number(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _result_exists(project: dict[str, Any], module: str) -> bool:
    return isinstance(project.get("module_outputs", {}).get(module), dict)


def run_project_check(project_path: str | Path, root_dir: str | Path,
                      language: str = "ja") -> list[CheckItem]:
    project_path = Path(project_path)
    root_dir = Path(root_dir)
    language = language if language in ("ja", "en") else "ja"
    tx = TEXT[language]
    module_names = MODULE_NAMES[language]
    checks: list[CheckItem] = []

    if not project_path.exists():
        return [CheckItem("Project JSON", tx["file"], "ERROR", tx["not_found"])]

    try:
        project = load_project(project_path)
        checks.append(CheckItem("Project JSON", tx["load"], "OK", str(project_path)))
    except Exception as exc:
        return [CheckItem("Project JSON", tx["load"], "ERROR",
                          f"{type(exc).__name__}: {exc}")]

    try:
        with tempfile.TemporaryDirectory(prefix="azras_check_") as temp_dir:
            temp_path = Path(temp_dir) / "roundtrip.json"
            save_project(copy.deepcopy(project), temp_path)
            reloaded = load_project(temp_path)
            if reloaded.get("project_id") == project.get("project_id"):
                checks.append(CheckItem("Project JSON", tx["roundtrip"], "OK",
                                        tx["temporary_ok"]))
            else:
                checks.append(CheckItem("Project JSON", tx["roundtrip"], "ERROR",
                                        tx["project_id_mismatch"]))
    except Exception as exc:
        checks.append(CheckItem("Project JSON", tx["roundtrip"], "ERROR",
                                f"{type(exc).__name__}: {exc}"))

    common = project.get("common", {})
    for key, label in {
        "project_name": tx["project_name"], "country": tx["country"],
        "building_use": tx["building_use"], "latitude": tx["latitude"],
        "longitude": tx["longitude"],
    }.items():
        value = common.get(key)
        checks.append(CheckItem("Module 0", label,
                                "OK" if value not in (None, "") else "WARNING",
                                str(value) if value not in (None, "")
                                else tx["not_entered"]))

    storeys = _number(common.get("storeys"))
    floor_areas = common.get("floor_areas_m2") or []
    gfa = _number(common.get("scale_gfa_m2"))
    scale_ok = bool(storeys and storeys > 0 and floor_areas and gfa and gfa > 0)
    checks.append(CheckItem(
        tx["scale_link"], tx["scale_item"], "OK" if scale_ok else "ERROR",
        tx["scale_detail"].format(storeys=storeys, floors=floor_areas, gfa=gfa)
        if scale_ok else tx["scale_error"],
    ))

    outputs = project.get("module_outputs", {})
    statuses = project.get("module_status", {})
    # Module 8 was retired when 200-year business cash flow was consolidated
    # into current Evaluation Module 6. Keep project-schema compatibility,
    # but do not report the legacy internal key as an active module.
    for number in (1, 2, 3, 4, 5, 6, 7):
        key = f"module{number}"
        output = outputs.get(key)
        if isinstance(output, dict):
            meta = output.get("_meta") or {}
            snapshot = output.get("_input_snapshot")
            detail = tx["result_saved"].format(
                updated=meta.get("updated_at", tx["unknown"]))
            status = "OK"
            if not isinstance(snapshot, dict):
                status = "WARNING"
                detail += " / " + tx["no_snapshot"]
        else:
            status = "WARNING"
            detail = tx["not_calculated"]
        checks.append(CheckItem(f"Module {number}", module_names[key],
                                status, detail))
        module_status = statuses.get(key, {})
        if module_status.get("status") == "error":
            checks.append(CheckItem(
                f"Module {number}", tx["link_status"], "ERROR",
                module_status.get("message", tx["error"])))

    for module, dependencies in DEPENDENCY_REQUIREMENTS.items():
        if not _result_exists(project, module):
            continue
        missing = [dep for dep in dependencies
                   if not _result_exists(project, dep)]
        checks.append(CheckItem(
            tx["module_link"], tx["prerequisite"].format(module=module),
            "OK" if not missing else "ERROR",
            tx["normal"] if not missing
            else tx["missing"].format(items=", ".join(missing)),
        ))

    m1 = outputs.get("module1") or {}
    pdf = m1.get("source_pdf") or (m1.get("_input_snapshot") or {}).get("pdf")
    if pdf:
        checks.append(CheckItem("Module 1", tx["pdf_file"],
                                "OK" if Path(pdf).exists() else "WARNING",
                                str(pdf)))

    m2 = outputs.get("module2") or {}
    weather = m2.get("weather_file") or (
        m2.get("_input_snapshot") or {}).get("weather_file")
    if weather:
        checks.append(CheckItem("Module 2", tx["weather_file"],
                                "OK" if Path(weather).exists() else "WARNING",
                                str(weather)))
    if isinstance(m2, dict) and m2:
        critical = ["heating_load_kWh_per_year",
                    "cooling_load_kWh_per_year",
                    "total_building_electricity_kWh_per_year",
                    "operational_CO2_kg_per_year"]
        missing = [key for key in critical if key not in m2]
        checks.append(CheckItem(
            "Module 2", tx["annual_summary"],
            "OK" if not missing else "ERROR",
            tx["normal"] if not missing
            else tx["missing"].format(items=", ".join(missing))))

    m5 = outputs.get("module5") or {}
    total_cost = _number((m5.get("summary") or {}).get("total_construction_cost"))
    if isinstance(m5, dict) and m5:
        checks.append(CheckItem(
            "Module 5", tx["total_construction_cost"],
            "OK" if total_cost and total_cost > 0 else "ERROR",
            f"{total_cost:,.0f} JPY" if total_cost else tx["zero_invalid"]))

    m6 = outputs.get("module6") or {}
    if isinstance(m6, dict) and m6:
        cashflow = m6.get("cashflow") or []
        checks.append(CheckItem(
            "Module 6", tx["cashflow_100"],
            "OK" if len(cashflow) == 200 else "WARNING",
            tx["years"].format(count=len(cashflow))))

    # In a PyInstaller EXE the source folders are bundled into the executable
    # and are not expected beside the EXE. Check source folders only when the
    # application is running directly from Python.
    if getattr(sys, "frozen", False):
        missing_paths = []
    else:
        required_paths = [
            root_dir / "main.py",
            root_dir / "core",
            root_dir / "services",
            root_dir / "data",
            root_dir / "lang",
        ]
        missing_paths = [
            str(required_path)
            for required_path in required_paths
            if not required_path.exists()
        ]
    checks.append(CheckItem(
        tx["app_structure"], tx["required_files"],
        "OK" if not missing_paths else "ERROR",
        tx["normal"] if not missing_paths
        else tx["missing"].format(items=", ".join(missing_paths))))
    return checks


def summarize_checks(checks: list[CheckItem]) -> dict[str, int]:
    result = {"OK": 0, "WARNING": 0, "ERROR": 0}
    for item in checks:
        result[item.status] = result.get(item.status, 0) + 1
    return result


def export_checks_csv(checks: list[CheckItem], path: str | Path,
                      language: str = "ja") -> None:
    language = language if language in ("ja", "en") else "ja"
    headers = (
        {"section": "区分", "item": "確認項目",
         "status": "結果", "detail": "詳細"}
        if language == "ja"
        else {"section": "Category", "item": "Check Item",
              "status": "Result", "detail": "Details"}
    )
    with Path(path).open("w", newline="", encoding="utf-8-sig") as file:
        writer = csv.DictWriter(
            file, fieldnames=["section", "item", "status", "detail"])
        writer.writerow(headers)
        for item in checks:
            writer.writerow(asdict(item))
