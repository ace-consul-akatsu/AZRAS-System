from __future__ import annotations

import hashlib
import ipaddress
import json
import re
from datetime import datetime, timezone, timedelta
from pathlib import Path
from urllib.parse import urlsplit

# AZRAS-side evidence boundary. This does NOT claim control over an AI provider's
# private network. It controls which source references AZRAS will accept and retain.
_ALLOWED_SCHEMES = {"http", "https"}
_BLOCKED_HOSTS = {
    "localhost", "localhost.localdomain", "ip6-localhost", "ip6-loopback",
}
_BLOCKED_SUFFIXES = (
    ".local", ".internal", ".intranet", ".lan", ".home", ".corp",
)
_URL_RE = re.compile(r"\b[a-zA-Z][a-zA-Z0-9+.-]*://[^\s\"'<>]+")


class PublicEvidencePolicyError(ValueError):
    def __init__(self, message: str, report: dict):
        super().__init__(message)
        self.report = report


def _walk_strings(value):
    if isinstance(value, dict):
        for v in value.values():
            yield from _walk_strings(v)
    elif isinstance(value, (list, tuple, set)):
        for v in value:
            yield from _walk_strings(v)
    elif isinstance(value, str):
        yield value


def extract_declared_source_urls(payload) -> list[str]:
    """Collect explicit URI strings without trying to read provider-private reasoning."""
    urls = []
    seen = set()
    for text in _walk_strings(payload):
        for match in _URL_RE.findall(text):
            url = match.rstrip(".,);]}>")
            if url not in seen:
                seen.add(url)
                urls.append(url)
    return urls


def _classify_url(url: str) -> list[dict]:
    issues = []
    try:
        parts = urlsplit(url)
    except Exception:
        return [{"code": "malformed_url", "severity": "reject", "url": url}]
    scheme = (parts.scheme or "").lower()
    host = (parts.hostname or "").strip().lower().rstrip(".")
    if scheme not in _ALLOWED_SCHEMES:
        issues.append({"code": "non_public_web_scheme", "severity": "reject", "url": url, "scheme": scheme})
    if parts.username is not None or parts.password is not None:
        issues.append({"code": "credential_bearing_url", "severity": "reject", "url": url})
    if not host:
        issues.append({"code": "missing_url_host", "severity": "reject", "url": url})
        return issues
    if host in _BLOCKED_HOSTS or any(host.endswith(s) for s in _BLOCKED_SUFFIXES):
        issues.append({"code": "private_or_local_hostname", "severity": "reject", "url": url, "host": host})
    try:
        ip = ipaddress.ip_address(host.split("%", 1)[0])
    except ValueError:
        ip = None
    if ip is not None:
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_multicast or ip.is_reserved or ip.is_unspecified:
            issues.append({"code": "private_or_nonpublic_ip", "severity": "reject", "url": url, "host": host})
    elif "." not in host:
        # Single-label DNS names are overwhelmingly intranet/local names. Reject rather
        # than silently accepting a source that cannot be distinguished from closed-net evidence.
        issues.append({"code": "single_label_nonpublic_hostname", "severity": "reject", "url": url, "host": host})
    if scheme == "http":
        issues.append({"code": "unencrypted_http_source", "severity": "warning", "url": url, "host": host})
    return issues


def inspect_public_evidence_urls(payload) -> dict:
    urls = extract_declared_source_urls(payload)
    anomalies = []
    for url in urls:
        anomalies.extend(_classify_url(url))
    return {
        "policy": "public_http_https_only",
        "urls": urls,
        "anomalies": anomalies,
        "rejected_urls": sorted({a.get("url") for a in anomalies if a.get("severity") == "reject" and a.get("url")}),
        "warning_urls": sorted({a.get("url") for a in anomalies if a.get("severity") == "warning" and a.get("url")}),
        "provider_side_network_control_claimed": False,
        "note": "AZRAS validates observable evidence references only; it does not claim control over an AI provider's internal networking.",
    }


def enforce_public_evidence_urls(payload) -> dict:
    report = inspect_public_evidence_urls(payload)
    if report.get("rejected_urls"):
        raise PublicEvidencePolicyError(
            "AI evidence contains a URL outside the AZRAS public HTTP/HTTPS import boundary: "
            + ", ".join(report["rejected_urls"][:5]),
            report,
        )
    return report


def _sha256_path(path) -> str | None:
    try:
        p = Path(path)
        h = hashlib.sha256()
        with p.open("rb") as f:
            for chunk in iter(lambda: f.read(1024 * 1024), b""):
                h.update(chunk)
        return h.hexdigest()
    except Exception:
        return None


def _reviewer(payload) -> str:
    if not isinstance(payload, dict):
        return "unknown"
    analysis = payload.get("analysis") if isinstance(payload.get("analysis"), dict) else {}
    return str(analysis.get("ai_reviewer") or payload.get("ai_reviewer") or payload.get("reviewer") or "unknown")


def _research_role(payload) -> str | None:
    if not isinstance(payload, dict):
        return None
    analysis = payload.get("analysis") if isinstance(payload.get("analysis"), dict) else {}
    value = analysis.get("research_role") or analysis.get("type")
    return str(value) if value not in (None, "") else None


def _refresh_rolling_summary(audit_dir: Path) -> dict | None:
    try:
        audit_dir.mkdir(parents=True, exist_ok=True)
        log_path = audit_dir / "AI_AUDIT_LOG.jsonl"
        now = datetime.now(timezone.utc)
        start = now - timedelta(days=7)
        events = []
        if log_path.exists():
            for raw in log_path.read_text(encoding="utf-8", errors="replace").splitlines():
                try:
                    event = json.loads(raw)
                    dt = datetime.fromisoformat(str(event.get("event_at") or "").replace("Z", "+00:00"))
                    if dt.tzinfo is None:
                        dt = dt.replace(tzinfo=timezone.utc)
                    if dt >= start:
                        events.append(event)
                except Exception:
                    continue
        anomaly_counts = {}
        reviewers = set()
        urls = set()
        anomaly_events = 0
        for event in events:
            reviewers.add(str(event.get("reviewer") or "unknown"))
            for url in event.get("declared_source_urls") or []:
                urls.add(str(url))
            codes = [str(x) for x in (event.get("anomaly_codes") or []) if str(x)]
            if codes:
                anomaly_events += 1
            for code in codes:
                anomaly_counts[code] = anomaly_counts.get(code, 0) + 1
        summary = {
            "schema": "AZRAS_AI_WEEKLY_ANOMALY_SUMMARY",
            "schema_version": "1.0",
            "generated_at": now.isoformat(timespec="seconds"),
            "window_start": start.isoformat(timespec="seconds"),
            "window_end": now.isoformat(timespec="seconds"),
            "window_days": 7,
            "event_count": len(events),
            "anomaly_event_count": anomaly_events,
            "anomaly_counts": anomaly_counts,
            "reviewers": sorted(reviewers),
            "unique_declared_source_url_count": len(urls),
            "review_owner": "AZRAS operator/designer",
            "review_recommended": bool(anomaly_events),
            "refresh_policy": "Refreshed whenever AZRAS generates an AI request or imports/rejects an AI response. No autonomous background job runs while AZRAS is closed.",
            "reasoning_capture_policy": "Hidden chain-of-thought is neither requested nor stored. AZRAS retains only observable request/response artifacts, explicit evidence/reason fields, source URLs, hashes, and validation anomalies.",
        }
        (audit_dir / "AI_WEEKLY_ANOMALY_SUMMARY.json").write_text(
            json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        return summary
    except Exception:
        return None


def record_ai_request_audit(audit_dir, workflow: str, request_text: str, request_path=None, metadata=None):
    """Record an observable request artifact; never records hidden model reasoning."""
    try:
        audit_dir = Path(audit_dir)
        audit_dir.mkdir(parents=True, exist_ok=True)
        event = {
            "schema": "AZRAS_AI_AUDIT_EVENT",
            "schema_version": "1.0",
            "event_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "event_type": "request_generated",
            "workflow": str(workflow),
            "reviewer": "not_yet_known",
            "request_file": Path(request_path).name if request_path else None,
            "request_sha256": hashlib.sha256(str(request_text).encode("utf-8")).hexdigest(),
            "declared_source_urls": [],
            "anomaly_codes": [],
            "metadata": metadata or {},
            "reasoning_capture_policy": "observable_artifacts_only_no_hidden_chain_of_thought",
        }
        with (audit_dir / "AI_AUDIT_LOG.jsonl").open("a", encoding="utf-8") as f:
            f.write(json.dumps(event, ensure_ascii=False, separators=(",", ":")) + "\n")
        _refresh_rolling_summary(audit_dir)
        return event
    except Exception:
        return None


def record_ai_import_audit(audit_dir, workflow: str, source_path, payload,
                           url_policy_report=None, contract_issues=None,
                           extra_anomalies=None, decision_summary=None):
    """Record observable AI response evidence, source references, and validation anomalies."""
    try:
        audit_dir = Path(audit_dir)
        audit_dir.mkdir(parents=True, exist_ok=True)
        report = url_policy_report if isinstance(url_policy_report, dict) else inspect_public_evidence_urls(payload)
        anomaly_codes = []
        for a in report.get("anomalies") or []:
            if str(a.get("severity") or "") == "reject":
                anomaly_codes.append(str(a.get("code") or "unsafe_source_url"))
        for issue in contract_issues or []:
            if str(issue):
                anomaly_codes.append("contract:" + str(issue))
        for issue in extra_anomalies or []:
            if isinstance(issue, dict):
                code = issue.get("code")
            else:
                code = issue
            if str(code or ""):
                anomaly_codes.append(str(code))
        event = {
            "schema": "AZRAS_AI_AUDIT_EVENT",
            "schema_version": "1.0",
            "event_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "event_type": "response_import",
            "workflow": str(workflow),
            "reviewer": _reviewer(payload),
            "research_role": _research_role(payload),
            "response_file": Path(source_path).name if source_path else None,
            "response_sha256": _sha256_path(source_path),
            "declared_source_urls": report.get("urls") or [],
            "url_policy": report.get("policy"),
            "url_policy_warnings": [a for a in (report.get("anomalies") or []) if a.get("severity") == "warning"],
            "anomaly_codes": sorted(set(anomaly_codes)),
            "contract_issues": list(contract_issues or []),
            "decision_summary": decision_summary or {},
            "reasoning_capture_policy": "observable_artifacts_only_no_hidden_chain_of_thought",
        }
        with (audit_dir / "AI_AUDIT_LOG.jsonl").open("a", encoding="utf-8") as f:
            f.write(json.dumps(event, ensure_ascii=False, separators=(",", ":")) + "\n")
        _refresh_rolling_summary(audit_dir)
        return event
    except Exception:
        return None
