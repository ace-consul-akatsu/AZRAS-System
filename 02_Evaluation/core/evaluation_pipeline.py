from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any

from core.project_store import save_project
from services.renewal_scenario_engine_v9_2 import generate_scenario
from services.repair_demolition_cost_engine_v9_6 import calculate as calculate_lifecycle_cost


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load_json(root_dir: Path, name: str) -> dict[str, Any]:
    return json.loads((root_dir / "data" / name).read_text(encoding="utf-8"))


def _detect_profile(project: dict[str, Any], profile_db: dict[str, Any]) -> str | None:
    common = project.get("common") or {}
    detailed = common.get("detailed_configuration") or {}
    general = detailed.get("general") or {}
    tokens = " ".join(
        str(x or "").strip().lower()
        for x in (
            common.get("construction_method_id"),
            common.get("construction_method_detail_id"),
            detailed.get("building_system"),
            general.get("structure"),
            general.get("method"),
        )
    )
    candidates: list[str] = []
    if "azras" in tokens:
        candidates.append("AZRAS")
    if any(x in tokens for x in ("2x6", "2×6", "wood_frame", "timber")):
        candidates.append("2x6 Timber")
    if any(x in tokens for x in ("rc_wall", "wall_rc", "wall-type")):
        candidates.append("RC Wall")
    if any(x in tokens for x in ("rc_frame", "conventional_rc", "moment_frame")):
        candidates.append("RC Frame")
    if any(x in tokens for x in ("steel_frame", "steel")):
        candidates.append("Steel Frame")
    if any(x in tokens for x in ("clt", "mass_timber")):
        candidates.append("CLT / Mass Timber")

    profiles = profile_db.get("profiles") or {}
    for key in candidates:
        if key in profiles:
            return key

    legacy = ((project.get("module_outputs") or {}).get("module1") or {}).get("selected_building_profile")
    return legacy if legacy in profiles else None


def _stamp_internal(result: dict[str, Any], source: str) -> dict[str, Any]:
    result = deepcopy(result)
    result["_evaluation_internal_support"] = {
        "status": "calculated",
        "purpose": "support_200_year_environment_and_business_only",
        "source": source,
        "updated_at": _now(),
        "visible_as_independent_screen": False,
    }
    return result


def ensure_internal_200_year_support(
    project: dict[str, Any],
    project_path: str | Path,
    root_dir: str | Path,
    language: str = "ja",
) -> dict[str, Any]:
    """Prepare lifecycle support data for the current Evaluation UI.

    Current Evaluation exposes four approved screens:
    Module 3 scenario, Module 4 200-year environment, Module 7 lifecycle cost,
    and Module 6 200-year business. Planning supplies formal Module 1/2/5 data.

    Monetary values are based on the Module 5 construction-cost result already
    saved by Planning. Evaluation does not fetch or create detailed/provider prices.
    """
    root_dir = Path(root_dir)
    outputs = project.setdefault("module_outputs", {})

    missing = [key for key in ("module1", "module2", "module5") if not isinstance(outputs.get(key), dict) or not outputs.get(key)]
    if missing:
        raise ValueError(
            "Planning Project JSONに必要な結果がありません: " + ", ".join(missing)
            if language == "ja"
            else "Required Planning Project JSON results are missing: " + ", ".join(missing)
        )

    m5 = outputs.get("module5") or {}
    total_cost = ((m5.get("summary") or {}).get("total_construction_cost"))
    try:
        total_cost = float(total_cost)
    except (TypeError, ValueError):
        total_cost = 0.0
    if total_cost <= 0:
        raise ValueError(
            "Planningの概算建設費が保存されていません。01_AZRAS_Planningで概算建設費を計算・保存してください。"
            if language == "ja"
            else "No approximate construction cost is saved. Calculate and save it in 01_AZRAS_Planning first."
        )

    provider_mode = str(m5.get("cost_provider_mode") or m5.get("provider_mode") or "approximate").strip().lower()
    if provider_mode == "detailed":
        raise ValueError(
            "02_AZRAS_Evaluationの200年事業は概算値を使用します。01_AZRAS_Planningで概算建設費を再計算・保存してください。"
            if language == "ja"
            else "02_AZRAS_Evaluation uses approximate values for 200-year business evaluation. Recalculate and save the approximate construction cost in 01_AZRAS_Planning."
        )

    component_db = _load_json(root_dir, "component_life_database_v9_2.json")
    profile_db = _load_json(root_dir, "construction_scenario_profiles_v9_2.json")
    profile_key = _detect_profile(project, profile_db)
    if not profile_key:
        raise ValueError(
            "建物構造・工法から200年更新シナリオを特定できません。Planningの構造・工法設定を確認してください。"
            if language == "ja"
            else "A 200-year renewal scenario could not be identified from the building structure/method. Check the Planning structure/method settings."
        )

    profile = (profile_db.get("profiles") or {}).get(profile_key) or {}
    rebuild_cycle = max(int(profile.get("default_rebuild_cycle_years", 0) or 0), 0)
    module3 = generate_scenario(
        project,
        component_db,
        profile_db,
        profile_key,
        200,
        language,
        "adaptive",
        True,
        rebuild_cycle,
    )
    module3["_input_snapshot"] = {
        "profile_key": profile_key,
        "period": 200,
        "language": language,
        "layout_policy": "adaptive",
        "keep_same": True,
        "rebuild_cycle_years": rebuild_cycle,
        "source": "02_AZRAS_Evaluation automatic internal scenario",
    }
    outputs["module3"] = _stamp_internal(module3, "standard_profile_200_year_scenario")

    cost_db = _load_json(root_dir, "repair_demolition_cost_assumptions_v9_6.json")
    settings = dict(cost_db.get("factors") or {})
    module7 = calculate_lifecycle_cost(project, cost_db, settings)
    module7["_input_snapshot"] = {
        "settings": deepcopy(settings),
        "source": "02_AZRAS_Evaluation automatic approximate lifecycle cost",
    }
    module7["cost_basis"] = {
        "type": "approximate",
        "source": "Planning module5 approximate construction cost + Evaluation standard lifecycle assumptions",
        "detailed_estimate": False,
    }
    outputs["module7"] = _stamp_internal(module7, "approximate_lifecycle_cost_support")

    project.setdefault("evaluation", {})["current_scope"] = {
        "module3_visible": True,
        "module4_visible": True,
        "module5_visible": False,
        "module6_visible": True,
        "module7_visible": True,
        "public_screens": [
            "repair_renewal_demolition_scenario",
            "200_year_environment",
            "repair_renewal_demolition_cost",
            "200_year_business",
        ],
        "planning_inputs": ["module1", "module2", "module5"],
        "retired_modules_not_used": ["module8", "module9"],
        "monetary_basis": "approximate",
        "updated_at": _now(),
    }
    # Remove stale metadata from prior simplified-UI experiments.
    project.get("evaluation", {}).pop("internal_support", None)

    save_project(project, project_path)
    return project
