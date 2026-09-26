from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from module5.app import Module5App


def _stub():
    obj = object.__new__(Module5App)
    obj._authoritative_project_cost_location = lambda: "愛知県春日井市松河戸町2-18-7"
    obj._ui = lambda ja, en: ja
    return obj


def _scope():
    return {
        "items": [{"cost_item_key": "concrete", "unit": "m3"}],
        "equipment_packages": [],
        "gross_floor_area_m2": 245.1,
    }


def _reviewer_payload():
    return {
        "schema": "AZRAS_AI_APPROX_COST",
        "schema_version": "1.4",
        "analysis": {
            "ai_reviewer": "Meta AI",
            "research_role": "reviewer",
            "evolution_observation": {"response_timestamp": "2026-09-23T09:22:15Z"},
        },
        "location": {
            "authoritative_location": "愛知県春日井市松河戸町2-18-7",
            "country": "Japan",
        },
        "unit_costs": {
            "concrete": {
                "unit": "m3",
                "pricing_structure": "provisional_estimate",
                "price": 43170,
                "candidate_quality": {
                    "source_type": "government",
                    "scope_definition": "other",
                    "scope_includes": [],
                    "scope_excludes": [],
                    "assumptions_disclosed": True,
                    "geographic_level": "metro",
                    "unresolved_points": [],
                    "comparable_for_reconciliation": True,
                },
                "evidence": {
                    "status": "found",
                    "source_type": "government",
                    "source_title": "Synthetic JPY source",
                    "source_url": "https://example.com/jpy-source",
                    "source_unit": "JPY/m3",
                },
            }
        },
        "equipment_packages": {"hvac": {"price_JPY": None, "status": "unresolved"}},
        "review_findings": {},
    }


def main():
    obj = _stub()
    parsed = obj._parse_ai_cost_payload(_reviewer_payload(), "meta.json", _scope(), "JPY")
    assert parsed["research_role"] == "reviewer"
    assert parsed["currency_validation"]["mode"] == "reviewer_payload_inference"
    assert parsed["completed_at"] == "2026-09-23T09:22:15Z"
    assert "concrete" in parsed["unit_cost_candidates"]

    primary = _reviewer_payload()
    primary["analysis"] = {"ai_reviewer": "ChatGPT", "research_role": "primary_guide", "completed_at": "2026-09-23T09:01:00Z"}
    primary["research_execution"] = {"web_research_status": "completed", "web_search_attempted": True}
    try:
        obj._parse_ai_cost_payload(primary, "primary.json", _scope(), "JPY")
    except ValueError as exc:
        assert "currency mismatch" in str(exc)
    else:
        raise AssertionError("Primary guide without declared currency must remain rejected")

    wrong = {"schema": "AZRAS_AI_TAKEOFF_FINAL_REVIEW", "schema_version": "1.0"}
    try:
        obj._parse_ai_cost_payload(wrong, "takeoff.json", _scope(), "JPY")
    except ValueError as exc:
        msg = str(exc)
        assert "数量積算用" in msg and "AZRAS_AI_APPROX_COST" in msg
    else:
        raise AssertionError("Takeoff JSON must not be accepted by Module 5 cost importer")

    src = (ROOT / "module5" / "app.py").read_text(encoding="utf-8")
    assert "[MANDATORY REVIEW OUTPUT CONTRACT]" in src
    assert 'location.currency MUST be' in src
    assert 'Do NOT return AZRAS_AI_TAKEOFF' in src
    print("PATCH_045 AI cost reviewer import self-check: PASS")


if __name__ == "__main__":
    main()
