"""Normalized CMP-audit models.

These models deliberately separate *evidence* from *interpretation*: a
detection says a consent platform or consent signal was observed, while a
finding says what that observation may mean and how confident the rule is.
Absence of a detected CMP is not treated as proof of non-compliance, and a
visible banner is not treated as proof of consent enforcement.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Any, Dict, Optional, Tuple
from urllib.parse import urlsplit, urlunsplit

CATEGORIES = ("necessary", "preferences", "analytics", "advertising", "other")
TRACKING_CATEGORIES = frozenset({"analytics", "advertising"})
SEVERITIES = ("critical", "high", "medium", "low", "informational")
CONFIDENCE_LEVELS = ("confirmed", "high-confidence", "suspected", "unverified")

_SEVERITY_RANK = {name: index for index, name in enumerate(SEVERITIES)}
_CONFIDENCE_RANK = {name: index for index, name in enumerate(CONFIDENCE_LEVELS)}


def sanitize_url(url: str) -> str:
    """Drop query string and fragment before an observed URL becomes evidence.

    Consent URLs can carry identifiers or tokens in their query string. CMP
    reporting keeps origin + path only, never raw query values.
    """
    try:
        parsed = urlsplit(url)
    except (TypeError, ValueError):
        return ""
    return urlunsplit((parsed.scheme, parsed.netloc, parsed.path, "", ""))


@dataclass(frozen=True)
class CmpEvidence:
    kind: str
    summary: str
    source: str = ""
    value: str = ""
    page_url: str = ""
    timestamp: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "kind": self.kind,
            "summary": self.summary,
            "source": self.source,
            "value": self.value,
            "page_url": sanitize_url(self.page_url),
            "timestamp": self.timestamp,
        }


@dataclass(frozen=True)
class CmpDetection:
    adapter_id: str
    vendor: str
    adapter_contract_version: str
    confidence: str
    evidence: Tuple[CmpEvidence, ...] = ()
    capabilities: Tuple[str, ...] = ()
    accept_selectors: Tuple[str, ...] = ()
    reject_selectors: Tuple[str, ...] = ()
    notes: Tuple[str, ...] = ()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "adapter_id": self.adapter_id,
            "vendor": self.vendor,
            "adapter_contract_version": self.adapter_contract_version,
            "confidence": self.confidence,
            "capabilities": list(self.capabilities),
            "accept_selectors": list(self.accept_selectors),
            "reject_selectors": list(self.reject_selectors),
            "notes": list(self.notes),
            "evidence": [item.to_dict() for item in self.evidence],
        }


@dataclass(frozen=True)
class ConsentState:
    sources: Tuple[str, ...] = ()
    categories: Dict[str, Optional[bool]] = field(default_factory=dict)
    google_mode: Dict[str, str] = field(default_factory=dict)
    confidence: str = "unverified"
    timestamp: float = 0.0
    evidence: Tuple[CmpEvidence, ...] = ()

    def category(self, name: str) -> Optional[bool]:
        return self.categories.get(name)

    def is_granted(self, name: str) -> bool:
        return self.categories.get(name) is True

    def is_denied(self, name: str) -> bool:
        return self.categories.get(name) is False

    def is_known(self, name: str) -> bool:
        return self.categories.get(name) is not None

    @property
    def has_categories(self) -> bool:
        return any(value is not None for value in self.categories.values())

    def to_dict(self) -> Dict[str, Any]:
        return {
            "sources": list(self.sources),
            "categories": dict(self.categories),
            "google_mode": dict(self.google_mode),
            "confidence": self.confidence,
            "timestamp": self.timestamp,
            "evidence": [item.to_dict() for item in self.evidence],
        }


@dataclass(frozen=True)
class RequestObservation:
    url: str
    method: str
    category: str
    phase: str
    host: str
    timestamp: float = 0.0
    network_pattern: str = ""
    resource_type: str = ""

    @property
    def is_tracking(self) -> bool:
        return self.category in TRACKING_CATEGORIES

    def to_dict(self) -> Dict[str, Any]:
        return {
            "url": sanitize_url(self.url),
            "method": self.method,
            "category": self.category,
            "phase": self.phase,
            "host": self.host,
            "timestamp": self.timestamp,
            "network_pattern": self.network_pattern,
            "resource_type": self.resource_type,
        }


@dataclass(frozen=True)
class CookieMetadata:
    name: str
    domain: str = ""
    path: str = ""
    secure: bool = False
    http_only: bool = False
    same_site: str = ""
    expires: float = 0.0
    cmp_related: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "domain": self.domain,
            "path": self.path,
            "secure": self.secure,
            "http_only": self.http_only,
            "same_site": self.same_site,
            "expires": self.expires,
            "cmp_related": self.cmp_related,
        }


@dataclass(frozen=True)
class ConsentLifecycle:
    requested_action: str = "none"
    authorized: bool = False
    performed: bool = False
    selector: str = ""
    failure_reason: str = ""
    reloaded: bool = False
    started_at: float = 0.0
    completed_at: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "requested_action": self.requested_action,
            "authorized": self.authorized,
            "performed": self.performed,
            "selector": self.selector,
            "failure_reason": self.failure_reason,
            "reloaded": self.reloaded,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
        }


def _finding_id(rule_id: str, subject: str) -> str:
    digest = hashlib.sha256(subject.encode("utf-8")).hexdigest()[:10]
    return f"{rule_id}:{digest}" if subject else rule_id


@dataclass(frozen=True)
class CmpFinding:
    finding_id: str
    rule_id: str
    category: str
    severity: str
    confidence: str
    title: str
    message: str
    remediation: str
    component: str
    detection_method: str
    evidence: Tuple[CmpEvidence, ...] = ()
    timestamp: float = 0.0
    source: str = "pytagmanager"

    @classmethod
    def create(
        cls,
        *,
        rule_id: str,
        category: str,
        severity: str,
        confidence: str,
        title: str,
        message: str,
        remediation: str,
        component: str,
        detection_method: str,
        evidence: Tuple[CmpEvidence, ...] = (),
        subject: str = "",
        timestamp: float = 0.0,
    ) -> "CmpFinding":
        if severity not in SEVERITIES:
            raise ValueError(f"unknown severity: {severity}")
        if confidence not in CONFIDENCE_LEVELS:
            raise ValueError(f"unknown confidence: {confidence}")
        return cls(
            finding_id=_finding_id(rule_id, subject),
            rule_id=rule_id,
            category=category,
            severity=severity,
            confidence=confidence,
            title=title,
            message=message,
            remediation=remediation,
            component=component,
            detection_method=detection_method,
            evidence=tuple(evidence),
            timestamp=timestamp,
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "finding_id": self.finding_id,
            "rule_id": self.rule_id,
            "category": self.category,
            "severity": self.severity,
            "confidence": self.confidence,
            "title": self.title,
            "message": self.message,
            "remediation": self.remediation,
            "component": self.component,
            "detection_method": self.detection_method,
            "source": self.source,
            "timestamp": self.timestamp,
            "evidence": [item.to_dict() for item in self.evidence],
        }


def dedupe_findings(findings: Tuple[CmpFinding, ...]) -> Tuple[CmpFinding, ...]:
    """Merge findings with the same stable id, keeping the strongest claim.

    Evidence from every occurrence is preserved. Severity/confidence use the
    first (strongest) occurrence after sorting, so rule evaluation order does
    not change the final verdict.
    """
    ordered = sorted(
        findings,
        key=lambda item: (
            _SEVERITY_RANK.get(item.severity, 99),
            _CONFIDENCE_RANK.get(item.confidence, 99),
            item.finding_id,
        ),
    )
    merged: Dict[str, CmpFinding] = {}
    evidence: Dict[str, list] = {}
    for finding in ordered:
        if finding.finding_id not in merged:
            merged[finding.finding_id] = finding
            evidence[finding.finding_id] = list(finding.evidence)
        else:
            evidence[finding.finding_id].extend(finding.evidence)
    result = []
    for finding_id, finding in merged.items():
        unique = tuple({(e.kind, e.summary, e.value): e for e in evidence[finding_id]}.values())
        result.append(
            CmpFinding(
                finding_id=finding.finding_id,
                rule_id=finding.rule_id,
                category=finding.category,
                severity=finding.severity,
                confidence=finding.confidence,
                title=finding.title,
                message=finding.message,
                remediation=finding.remediation,
                component=finding.component,
                detection_method=finding.detection_method,
                evidence=unique,
                timestamp=finding.timestamp,
                source=finding.source,
            )
        )
    return tuple(result)


@dataclass(frozen=True)
class CmpAuditReport:
    url: str
    generated_at: float
    mode: str
    detections: Tuple[CmpDetection, ...] = ()
    consent_initial: ConsentState = field(default_factory=ConsentState)
    consent_after_action: Optional[ConsentState] = None
    consent_after_reload: Optional[ConsentState] = None
    lifecycle: ConsentLifecycle = field(default_factory=ConsentLifecycle)
    cookies: Tuple[CookieMetadata, ...] = ()
    requests: Tuple[RequestObservation, ...] = ()
    findings: Tuple[CmpFinding, ...] = ()
    limitations: Tuple[str, ...] = ()
    schema_version: int = 1

    @property
    def tracking_requests(self) -> Tuple[RequestObservation, ...]:
        return tuple(item for item in self.requests if item.is_tracking)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "url": sanitize_url(self.url),
            "generated_at": self.generated_at,
            "mode": self.mode,
            "detections": [item.to_dict() for item in self.detections],
            "consent": {
                "initial": self.consent_initial.to_dict(),
                "after_action": self.consent_after_action.to_dict() if self.consent_after_action else None,
                "after_reload": self.consent_after_reload.to_dict() if self.consent_after_reload else None,
            },
            "lifecycle": self.lifecycle.to_dict(),
            "cookies": [item.to_dict() for item in self.cookies],
            "requests": [item.to_dict() for item in self.requests],
            "findings": [item.to_dict() for item in self.findings],
            "limitations": list(self.limitations),
            "summary": {
                "detected_cmp_count": len(self.detections),
                "finding_count": len(self.findings),
                "tracking_request_count": len(self.tracking_requests),
            },
        }
