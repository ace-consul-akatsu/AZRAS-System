from pathlib import Path
import json, tempfile, sys

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from core.ai_security_audit import (
    PublicEvidencePolicyError,
    enforce_public_evidence_urls,
    record_ai_import_audit,
    record_ai_request_audit,
)

m1 = (_ROOT / "module1" / "app.py").read_text(encoding="utf-8-sig")
m5 = (_ROOT / "module5" / "app.py").read_text(encoding="utf-8-sig")

required = {
    "module1": [
        "AZRAS_AI_STANDARD_RULES_V3_EN",
        "estimated_matching_items",
        "building_profile_matching_summary",
        "building_profile_requiring_review",
        "enforce_public_evidence_urls",
        "record_ai_import_audit",
    ],
    "module5": [
        "AZRAS_AI_STANDARD_RULES_V3_EN",
        "SEARCH STOP RULE",
        "filtered_incomplete",
        "enforce_public_evidence_urls",
        "record_ai_import_audit",
    ],
}
for name, text in (("module1", m1), ("module5", m5)):
    missing = [x for x in required[name] if x not in text]
    if missing:
        print("[NG]", name, "missing", missing)
        raise SystemExit(1)

safe = {"source_url": "https://example.com/public-price.pdf"}
rep = enforce_public_evidence_urls(safe)
assert rep["rejected_urls"] == []

bad_payloads = [
    {"source_url": "http://127.0.0.1/private"},
    {"source_url": "https://10.0.0.8/internal"},
    {"source_url": "file:///C:/secret.txt"},
    {"source_url": "https://user:pass@example.com/private"},
    {"source_url": "https://intranet/resource"},
]
for bad in bad_payloads:
    try:
        enforce_public_evidence_urls(bad)
    except PublicEvidencePolicyError:
        pass
    else:
        print("[NG] unsafe URL was not rejected:", bad)
        raise SystemExit(1)

with tempfile.TemporaryDirectory() as td:
    td = Path(td)
    req = td / "request.txt"; req.write_text("test request", encoding="utf-8")
    resp = td / "response.json"; resp.write_text(json.dumps(safe), encoding="utf-8")
    record_ai_request_audit(td, "test_request", "test request", req)
    record_ai_import_audit(td, "test_import", resp, safe, url_policy_report=rep)
    assert (td / "AI_AUDIT_LOG.jsonl").exists()
    summary = json.loads((td / "AI_WEEKLY_ANOMALY_SUMMARY.json").read_text(encoding="utf-8"))
    assert summary["window_days"] == 7
    assert summary["event_count"] >= 2
    assert summary["reasoning_capture_policy"].startswith("Hidden chain-of-thought")

print("AI_REQUEST_EFFICIENCY_SECURITY_AUDIT_PASS")
