"""Text rendering for CMP audit reports."""

from __future__ import annotations

from typing import Optional

from pytagmanager.cmp.models import CmpAuditReport, ConsentState

_SEVERITY_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3, "informational": 4}


def _format_consent(state: Optional[ConsentState]) -> str:
    if state is None:
        return "not captured"
    known = {
        name: value
        for name, value in state.categories.items()
        if value is not None
    }
    if known:
        categories = ", ".join(
            f"{name}={'granted' if value else 'denied'}" for name, value in sorted(known.items())
        )
    else:
        categories = "categories unavailable"
    sources = ", ".join(state.sources) if state.sources else "no readable signal"
    return f"{sources} ({categories}), confidence={state.confidence}"


def render_cmp_audit_report(report: CmpAuditReport) -> str:
    lines = [f"CMP audit: {report.url}", f"Mode: {report.mode}"]
    lines.append("")
    lines.append(f"Detected CMPs: {len(report.detections)}")
    for detection in report.detections:
        lines.append(
            f"  - {detection.vendor} ({detection.adapter_id}, "
            f"{detection.confidence}, adapter v{detection.adapter_contract_version})"
        )
        for capability in detection.capabilities:
            lines.append(f"      capability: {capability}")
        for note in detection.notes:
            lines.append(f"      note: {note}")

    lines.append("")
    lines.append("Consent state:")
    lines.append(f"  initial: {_format_consent(report.consent_initial)}")
    if report.consent_initial.tcf:
        tcf = report.consent_initial.tcf
        granted = sorted(
            purpose for purpose, value in tcf.get("purpose_consents", {}).items() if value
        )
        lines.append(
            "  TCF v2: gdpr_applies="
            f"{tcf.get('gdpr_applies')}, event_status={tcf.get('event_status') or 'unknown'}, "
            f"granted_purposes={','.join(granted) or 'none'}"
        )
    if report.consent_initial.gpp:
        gpp = report.consent_initial.gpp
        lines.append(
            "  GPP: sections="
            f"{','.join(gpp.get('applicable_sections', [])) or 'none'}, "
            f"signal_status={gpp.get('signal_status') or 'unknown'}"
        )
    if report.lifecycle.requested_action != "none":
        lines.append(f"  requested action: {report.lifecycle.requested_action}")
        lines.append(f"  performed: {report.lifecycle.performed}")
        if report.lifecycle.selector:
            lines.append(f"  selector: {report.lifecycle.selector}")
        if report.lifecycle.failure_reason:
            lines.append(f"  failure: {report.lifecycle.failure_reason}")
        lines.append(f"  after action: {_format_consent(report.consent_after_action)}")
        if report.lifecycle.reloaded:
            lines.append(f"  after reload: {_format_consent(report.consent_after_reload)}")

    tracking = report.tracking_requests
    lines.append("")
    lines.append(f"Observed tracking requests: {len(tracking)}")
    for request in tracking[:10]:
        lines.append(
            f"  - [{request.phase}] {request.category}: {request.host}{_path_only(request.url)}"
        )

    lines.append("")
    lines.append(f"Findings: {len(report.findings)}")
    for finding in sorted(
        report.findings,
        key=lambda item: (_SEVERITY_ORDER.get(item.severity, 99), item.rule_id, item.finding_id),
    ):
        lines.append(
            f"  [{finding.severity.upper()}/{finding.confidence}] "
            f"{finding.rule_id}: {finding.title}"
        )
        lines.append(f"      {finding.message}")
        for evidence in finding.evidence[:5]:
            detail = f" ({evidence.value})" if evidence.value else ""
            lines.append(f"      evidence: {evidence.summary}{detail}")
        lines.append(f"      remediation: {finding.remediation}")

    if report.limitations:
        lines.append("")
        lines.append("Limitations:")
        for limitation in report.limitations:
            lines.append(f"  - {limitation}")
    return "\n".join(lines)


def _path_only(url: str) -> str:
    from urllib.parse import urlsplit

    parsed = urlsplit(url or "")
    return parsed.path or ""
