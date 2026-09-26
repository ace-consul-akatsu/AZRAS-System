
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import copy
import hashlib
import json

DEPENDENCIES = {
    # PATCH_208 current 02_AZRAS_Evaluation graph.
    # Planning supplies formal Module 1/2/5 results. Evaluation owns 3/4/6/7.
    # Retired monolithic Module 8 and future Disaster/Module 9 are not active.
    "module1": ["module2", "module3", "module5"],
    "module2": ["module4"],
    "module3": ["module4", "module7"],
    "module4": [],
    "module5": ["module4", "module6", "module7"],
    "module6": [],
    "module7": ["module6"],
}

def _now() -> str:
    return datetime.now(timezone.utc).isoformat()

def _hash(value: Any) -> str:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()[:16]

def ensure_project_structure(project: dict[str, Any]) -> dict[str, Any]:
    project.setdefault("schema_version", "2.0")
    project.setdefault("platform_version", "9.4.0")
    project.setdefault("module_outputs", {})
    for i in range(1, 8):
        project["module_outputs"].setdefault(f"module{i}", None)
    project.setdefault("module_status", {})
    for i in range(1, 8):
        project["module_status"].setdefault(f"module{i}", {
            "status": "not_calculated",
            "updated_at": None,
            "save_mode": None,
            "source_modules": [],
            "message": "",
        })
    # PATCH_208: Module 8 (old monolithic business module) and Module 9
    # (future Disaster product) may exist in old Project JSONs, but are not active
    # Evaluation dependencies and must never be marked for recalculation.
    for legacy_key in ("module8","module9"):
        legacy_output = project.get("module_outputs", {}).get(legacy_key)
        if not isinstance(legacy_output, dict):
            project.get("module_status", {}).pop(legacy_key, None)

    project.setdefault("audit_log", [])
    project.setdefault("validation", {"warnings": [], "errors": []})
    project.setdefault("linkage", {
        "dependency_map": DEPENDENCIES,
        "last_propagation": None,
    })
    project["linkage"]["dependency_map"] = copy.deepcopy(DEPENDENCIES)
    return project

def impacted_modules(source: str) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    queue = list(DEPENDENCIES.get(source, []))
    while queue:
        item = queue.pop(0)
        if item in seen:
            continue
        seen.add(item)
        result.append(item)
        queue.extend(DEPENDENCIES.get(item, []))
    return result

def _load_json(root_dir: Path, name: str) -> dict[str, Any]:
    return json.loads((root_dir / "data" / name).read_text(encoding="utf-8"))

def _auto_recalculate(module_key: str, project: dict[str, Any], root_dir: Path) -> tuple[str, Any, str]:
    existing = project["module_outputs"].get(module_key)
    if not isinstance(existing, dict):
        return "pending", None, "保存済み設定がないため、初回は対象Moduleで計算してください。"
    snapshot = existing.get("_input_snapshot")
    if not isinstance(snapshot, dict):
        return "pending", None, "旧形式データのため入力条件が保存されていません。対象Moduleで一度更新保存してください。"

    try:
        if module_key == "module2":
            from services.environment_engine_v9_1 import run_environment
            weather_file = snapshot.get("weather_file", "")
            if not weather_file or not Path(weather_file).exists():
                return "pending", None, "気象データファイルが見つかりません。"
            _, result = run_environment(project, weather_file, snapshot["settings"])

        elif module_key == "module3":
            from services.renewal_scenario_engine_v9_2 import generate_scenario
            component_db = _load_json(root_dir, "component_life_database_v9_2.json")
            profile_db = _load_json(root_dir, "construction_scenario_profiles_v9_2.json")
            result = generate_scenario(
                project, component_db, profile_db,
                snapshot["profile_key"], int(snapshot["period"]),
                snapshot.get("language", "ja"),
                snapshot["layout_policy"], bool(snapshot["keep_same"])
            )

        elif module_key == "module4":
            from services.long_term_environment_engine_v9_3 import evaluate_long_term_environment
            factors = _load_json(root_dir, "environmental_lca_factors_v9_3.json")
            snapshot["period"] = 200
            result = evaluate_long_term_environment(
                project, factors, 200,
                float(snapshot["operational_change"]),
                float(snapshot["grid_change"]),
                bool(snapshot["include_credit"]),
                bool(snapshot["include_biogenic"]),
                bool(snapshot.get("future_climate_enabled", False)),
                float(snapshot.get("future_warming_100", 0.0)),
                float(snapshot.get("future_warming_200", 0.0)),
                int(float(snapshot.get("future_climate_interval", 20))),
                str(snapshot.get("grid_scenario", "standard"))
            )

        elif module_key == "module5":
            from services.construction_cost_engine_v9_4 import calculate_construction_cost
            db = _load_json(root_dir, "construction_cost_database_v9_4.json")
            result = calculate_construction_cost(
                project, db, snapshot["location"],
                snapshot["settings"], snapshot["equipment_selection"]
            )

        elif module_key == "module6":
            from services.investment_engine_v9_5 import calculate_investment
            snapshot["settings"] = dict(snapshot.get("settings") or {})
            snapshot["settings"]["analysis_years"] = 200
            result = calculate_investment(project, snapshot["settings"])

        elif module_key == "module7":
            from services.repair_demolition_cost_engine_v9_6 import calculate
            db = _load_json(root_dir, "repair_demolition_cost_assumptions_v9_6.json")
            result = calculate(project, db, snapshot["settings"])

        else:
            return "pending", None, "自動再計算アダプターがありません。"

        if not isinstance(result, dict):
            result = {"result": result}
        result["_input_snapshot"] = copy.deepcopy(snapshot)
        result["_meta"] = {
            "status": "auto_updated",
            "save_mode": "automatic_linkage",
            "updated_at": _now(),
            "source_hash": _hash(snapshot),
        }
        return "auto_updated", result, "自動再計算・自動保存が完了しました。"
    except Exception as exc:
        return "error", None, f"{type(exc).__name__}: {exc}"

def update_module_and_propagate(
    project: dict[str, Any],
    project_path: str | Path,
    source_module: str,
    result: dict[str, Any],
    input_snapshot: dict[str, Any],
    root_dir: str | Path,
) -> dict[str, Any]:
    from core.project_store import save_project, comparison_copy_block_reason

    # PATCH_008: a comparison copy may only be re-evaluated in Modules 6/7.
    _blocked = comparison_copy_block_reason(project, source_module)
    if _blocked:
        raise ValueError(_blocked)

    root_dir = Path(root_dir)
    ensure_project_structure(project)
    timestamp = _now()

    result = copy.deepcopy(result)
    result["_input_snapshot"] = copy.deepcopy(input_snapshot)
    result["_meta"] = {
        "status": "saved",
        "save_mode": "manual_update_save",
        "updated_at": timestamp,
        "source_hash": _hash(input_snapshot),
    }
    project["module_outputs"][source_module] = result
    project["module_status"][source_module] = {
        "status": "saved",
        "updated_at": timestamp,
        "save_mode": "manual_update_save",
        "source_modules": [],
        "message": "ユーザー操作により更新保存しました。",
    }
    project["audit_log"].append({
        "timestamp": timestamp,
        "action": "manual_module_update_save",
        "module": source_module,
        "result_hash": _hash(result),
    })

    report = {
        "source_module": source_module,
        "manual_saved": True,
        "auto_updated": [],
        "pending": [],
        "errors": [],
    }

    for target in impacted_modules(source_module):
        status, recalculated, message = _auto_recalculate(target, project, root_dir)
        if status == "auto_updated":
            project["module_outputs"][target] = recalculated
            project["module_status"][target] = {
                "status": "auto_updated",
                "updated_at": _now(),
                "save_mode": "automatic_linkage",
                "source_modules": [source_module],
                "message": message,
            }
            report["auto_updated"].append(target)
            project["audit_log"].append({
                "timestamp": _now(),
                "action": "automatic_linkage_update",
                "module": target,
                "triggered_by": source_module,
                "result_hash": _hash(recalculated),
            })
        elif status == "pending":
            project["module_status"][target] = {
                "status": "recalculation_pending",
                "updated_at": _now(),
                "save_mode": "automatic_linkage",
                "source_modules": [source_module],
                "message": message,
            }
            report["pending"].append({"module": target, "reason": message})
        else:
            project["module_status"][target] = {
                "status": "error",
                "updated_at": _now(),
                "save_mode": "automatic_linkage",
                "source_modules": [source_module],
                "message": message,
            }
            report["errors"].append({"module": target, "reason": message})

    project["linkage"]["last_propagation"] = {
        "timestamp": _now(),
        **report,
    }
    save_project(project, project_path)
    return report

def format_report(report: dict[str, Any], language: str = "ja") -> str:
    if language == "en":
        lines = [f'{report["source_module"]}: Project JSON updated.']
        if report["auto_updated"]:
            lines.append("Automatically recalculated/saved: " + ", ".join(report["auto_updated"]))
        if report["pending"]:
            lines.append("Pending: " + ", ".join(x["module"] for x in report["pending"]))
        if report["errors"]:
            lines.append("Errors: " + ", ".join(x["module"] for x in report["errors"]))
        return "\n".join(lines)

    lines = [f'{report["source_module"]}：Project JSONを更新保存しました。']
    if report["auto_updated"]:
        lines.append("連動先の自動再計算・自動保存：" + "、".join(report["auto_updated"]))
    if report["pending"]:
        lines.append("保留：" + "、".join(
            f'{x["module"]}（{x["reason"]}）' for x in report["pending"]
        ))
    if report["errors"]:
        lines.append("エラー：" + "、".join(
            f'{x["module"]}（{x["reason"]}）' for x in report["errors"]
        ))
    return "\n".join(lines)
