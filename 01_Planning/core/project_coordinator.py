
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import copy
import hashlib
import json
import traceback

DEPENDENCIES = {
    # PATCH 607: Planning owns only current Planning outputs.
    # Evaluation-owned Module 3/4/6/7 and retired Module 8/9 are not
    # invalidated or recalculated from the Planning executable.
    "module1": ["module2", "module5"],
    "module2": [],
    "module5": [],
}


RECALC_REQUIRED_UPSTREAMS = {
    "module2": ["module1"],
    "module5": ["module1"],
}

def module_output_is_current(project: dict[str, Any], module_key: str) -> bool:
    output = (project.get("module_outputs") or {}).get(module_key)
    if not isinstance(output, dict) or not output:
        return False
    meta = output.get("_meta") if isinstance(output.get("_meta"), dict) else {}
    if meta.get("is_current") is False:
        return False
    status_info = (project.get("module_status") or {}).get(module_key)
    if isinstance(status_info, dict):
        status = str(status_info.get("status") or "")
        if status in {"recalculation_pending", "error", "stale"}:
            return False
    # PATCH 517: only the current Project JSON contract is supported.
    # Legacy outputs are removed by project_store migration and never reach
    # downstream current-output checks.
    return True

def require_current_module_output(project: dict[str, Any], module_key: str, label: str | None = None) -> dict[str, Any]:
    output = (project.get("module_outputs") or {}).get(module_key)
    if not isinstance(output, dict) or not output:
        raise ValueError(f"{label or module_key} output is required.")
    if not module_output_is_current(project, module_key):
        raise ValueError(f"{label or module_key} output is stale; recalculate and save it before downstream calculation.")
    return output

def _mark_output_stale(project: dict[str, Any], module_key: str, source_module: str, timestamp: str) -> None:
    output = (project.get("module_outputs") or {}).get(module_key)
    if not isinstance(output, dict) or not output:
        return
    meta = output.setdefault("_meta", {})
    if not isinstance(meta, dict):
        meta = {}
        output["_meta"] = meta
    meta.update({
        "is_current": False,
        "stale_since": timestamp,
        "stale_trigger": source_module,
        "stale_reason": f"Upstream {source_module} changed; automatic recalculation has not completed.",
    })

def _blocking_upstreams(project: dict[str, Any], module_key: str) -> list[str]:
    blocked = []
    for upstream in RECALC_REQUIRED_UPSTREAMS.get(module_key, []):
        if not module_output_is_current(project, upstream):
            blocked.append(upstream)
    return blocked

def _now() -> str:
    return datetime.now(timezone.utc).isoformat()

def _hash(value: Any) -> str:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()[:16]

def module_output_fingerprint(project: dict[str, Any], module_key: str) -> str | None:
    """Return a stable fingerprint for the exact saved module output."""
    output = (project.get("module_outputs") or {}).get(module_key) if isinstance(project, dict) else None
    if not isinstance(output, dict) or not output:
        return None
    return _hash(output)


def module1_cost_dependency_fingerprint(project: dict[str, Any]) -> str | None:
    """Fingerprint Module 1 inputs that can affect Module 5 construction cost.

    PATCH_537: true-north/orientation-only edits must not stale Module 5.
    Cost still depends on quantities, geometry areas, construction details, MEP takeoff,
    and other non-orientation Module 1 content.
    """
    output = (project.get("module_outputs") or {}).get("module1") if isinstance(project, dict) else None
    if not isinstance(output, dict) or not output:
        return None

    orientation_keys = {
        "north_rotation_deg", "north_rotation", "orientation_evidence",
        "north_rotation_resolution", "north_rotation_input_deg",
        "north_rotation_confirmed", "true_azimuth_deg", "local_azimuth_deg",
        "azimuth_deg", "orientation_basis",
    }

    def scrub(value: Any) -> Any:
        if isinstance(value, dict):
            return {k: scrub(v) for k, v in value.items() if k not in orientation_keys}
        if isinstance(value, list):
            return [scrub(v) for v in value]
        return value

    return _hash(scrub(output))

def ensure_project_structure(project: dict[str, Any]) -> dict[str, Any]:
    project.setdefault("schema_version", "2.0")
    project.setdefault("platform_version", "9.4.0")
    project.setdefault("module_outputs", {})
    for i in (1, 2, 5):
        project["module_outputs"].setdefault(f"module{i}", None)
    project.setdefault("module_status", {})
    for i in (1, 2, 5):
        project["module_status"].setdefault(f"module{i}", {
            "status": "not_calculated",
            "updated_at": None,
            "save_mode": None,
            "source_modules": [],
            "message": "",
        })
    project.setdefault("audit_log", [])
    project.setdefault("validation", {"warnings": [], "errors": []})
    linkage = project.setdefault("linkage", {})
    # PATCH 425: runtime dependency rules are canonical.  Existing Project JSON
    # may carry an older dependency_map from a previous release; setdefault
    # would preserve that stale map even though propagation already uses the
    # current constants.  Refresh the persisted audit contract on every
    # migrate/save so JSON and runtime cannot disagree.
    linkage["dependency_map"] = copy.deepcopy(DEPENDENCIES)
    linkage["recalc_required_upstreams"] = copy.deepcopy(RECALC_REQUIRED_UPSTREAMS)
    linkage.setdefault("last_propagation", None)
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
    blocked = _blocking_upstreams(project, module_key)
    if blocked:
        return "pending", None, "Upstream output is stale or unavailable: " + ", ".join(blocked)
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

        elif module_key == "module5":
            from services.construction_cost_engine_v9_4 import calculate_construction_cost
            # PATCH_053: include user-added / dataset regional profiles, so a
            # Project saved with such a profile can still be recalculated.
            from services.regional_profile_catalog import load_construction_cost_database
            db = load_construction_cost_database(root_dir)
            # PATCH_038: AI Cost Provider prices are Project inputs, not shared
            # regional DB data. Reattach the saved overlay before automatic
            # recalculation so upstream changes do not silently erase the prices.
            _overlay=snapshot.get("ai_cost_provider_overlay")
            _loc=(db.get("locations") or {}).get(snapshot.get("location"))
            if isinstance(_overlay,dict) and isinstance(_loc,dict):
                _loc["_session_ai_unit_cost_overlay"]=copy.deepcopy(_overlay)
            result = calculate_construction_cost(
                project, db, snapshot["location"],
                snapshot["settings"], snapshot["equipment_selection"]
            )

        else:
            return "pending", None, "No automatic recalculation adapter is available."

        if not isinstance(result, dict):
            result = {"result": result}
        result["_input_snapshot"] = copy.deepcopy(snapshot)
        result["_meta"] = {
            "status": "auto_updated",
            "save_mode": "automatic_linkage",
            "updated_at": _now(),
            "source_hash": _hash(snapshot),
            "is_current": True,
        }
        return "auto_updated", result, "Automatic recalculation and save completed."
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

    # PATCH_043: a comparison copy may only be re-priced / re-evaluated.
    _blocked = comparison_copy_block_reason(project, source_module)
    if _blocked:
        raise ValueError(_blocked)

    root_dir = Path(root_dir)
    ensure_project_structure(project)
    project.setdefault("metadata", {}).update({
        "canonical_language": "en",
        "canonical_schema_version": "2.6",
        "project_data_standard": "English Canonical",
    })
    timestamp = _now()

    result = copy.deepcopy(result)
    result["_input_snapshot"] = copy.deepcopy(input_snapshot)
    result["_meta"] = {
        "status": "saved",
        "save_mode": "manual_update_save",
        "updated_at": timestamp,
        "source_hash": _hash(input_snapshot),
        "is_current": True,
    }
    project["module_outputs"][source_module] = result
    project["module_status"][source_module] = {
        "status": "saved",
        "updated_at": timestamp,
        "save_mode": "manual_update_save",
        "source_modules": [],
        "message": "Updated and saved by user action.",
    }
    project["audit_log"].append({
        "timestamp": timestamp,
        "action": "manual_module_update_save",
        "module": source_module,
        "result_hash": _hash(result),
    })

    impacted = impacted_modules(source_module)
    invalidated = []
    for target in impacted:
        if isinstance(project["module_outputs"].get(target), dict) and project["module_outputs"].get(target):
            _mark_output_stale(project, target, source_module, timestamp)
            invalidated.append(target)
        project["module_status"][target] = {
            "status": "recalculation_pending",
            "updated_at": timestamp,
            "save_mode": "automatic_linkage",
            "source_modules": [source_module],
            "message": f"Invalidated because upstream {source_module} changed.",
        }

    report = {
        "source_module": source_module,
        "manual_saved": True,
        "invalidated": invalidated,
        "auto_updated": [],
        "pending": [],
        "errors": [],
    }

    for target in impacted:
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
