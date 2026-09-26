from __future__ import annotations
from pathlib import Path
from typing import Any
import json

def _f(v, default=0.0):
    try: return float(v)
    except (TypeError, ValueError): return default

def load_rules(root_dir: str | Path) -> dict[str, Any]:
    p = Path(root_dir) / "data" / "regulatory_hazard_screening_rules_v1.json"
    return json.loads(p.read_text(encoding="utf-8"))

def apply_regulatory_hazard_rules(root_dir: str | Path, screening: dict[str, Any], project: dict[str, Any] | None=None) -> dict[str, Any]:
    project = project or {}
    master = load_rules(root_dir)
    evidence = screening.get("local_construction_evidence") or {}
    country = str(evidence.get("nearest_reference_country") or "")
    common = project.get("common") or {}
    location = common.get("location") or {}
    # Prefer a project-supplied country if available; proxy-country is only a fallback.
    project_country = str(location.get("country") or common.get("country") or "")
    effective_country = project_country or country

    # Hazard proxy currently comes from the nearest representative city in the existing suitability DB.
    suitability = json.loads((Path(root_dir)/"data"/"regional_suitability_database_v1.json").read_text(encoding="utf-8"))
    nearest_name = evidence.get("nearest_reference_city")
    nearest = next((x for x in (suitability.get("cities") or []) if x.get("name")==nearest_name), {})
    hazards = {k:_f(nearest.get(k)) for k in ("seismic","wind","flood","snow","fire")}

    applied = []
    methods = {str(x.get("method_id")): x for x in (screening.get("methods") or [])}
    for rule in master.get("rules") or []:
        countries = (rule.get("scope") or {}).get("countries") or ["*"]
        if "*" not in countries and effective_country not in countries:
            continue
        trigger = rule.get("trigger") or {}
        hazard = str(trigger.get("hazard") or "")
        if hazard and hazards.get(hazard,0.0) < _f(trigger.get("min_level")):
            continue
        for mid in rule.get("method_ids") or []:
            row = methods.get(mid)
            if not row:
                continue
            # Seed rules can only lower Candidate to Conditional. They cannot create Excluded.
            if rule.get("effect") == "Conditional" and row.get("status") == "Candidate":
                row["status"] = "Conditional"
            note_ja = str(rule.get("title_ja") or rule.get("rule_id"))
            note_en = str(rule.get("title_en") or rule.get("rule_id"))
            if note_ja not in (row.get("reasons_ja") or []):
                row.setdefault("reasons_ja", []).append(note_ja)
            if note_en not in (row.get("reasons_en") or []):
                row.setdefault("reasons_en", []).append(note_en)
            applied.append({
                "rule_id": rule.get("rule_id"),
                "method_id": mid,
                "effect": rule.get("effect"),
                "basis_type": rule.get("basis_type"),
                "legal_status": rule.get("legal_status"),
                "source_note": rule.get("source_note"),
            })

    statuses=("Candidate","Conditional","Excluded","Unknown")
    screening["counts"]={s:sum(1 for x in methods.values() if x.get("status")==s) for s in statuses}
    screening["regulatory_hazard_trace"]={
        "ruleset_version": master.get("ruleset_version"),
        "effective_country": effective_country or None,
        "country_source": "project" if project_country else ("representative_city_proxy" if country else "unknown"),
        "hazard_proxy": hazards,
        "applied_rules": applied,
        "policy": master.get("policy"),
        "warning": "This layer is preliminary screening, not a permit/code-compliance determination."
    }
    return screening
