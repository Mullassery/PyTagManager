"""Deterministic CMP evidence rules.

Rules only report what the collected evidence can support. In particular,
they do not turn a detected banner into a compliance verdict, and they do
not treat a missing CMP signature as proof that consent management is absent.
"""

from __future__ import annotations

from typing import Dict, Iterable, List, Optional, Sequence, Tuple

from pytagmanager.cmp.adapters import ADAPTERS, google_categories_from_mode
from pytagmanager.cmp.models import (
    CmpDetection,
    CmpEvidence,
    CmpFinding,
    ConsentLifecycle,
    ConsentState,
    CookieMetadata,
    RequestObservation,
    dedupe_findings,
    sanitize_url,
)

_REPORTED_REQUEST_LIMIT = 5


def analyze_cmp(
    *,
    url: str,
    detections: Sequence[CmpDetection],
    initial_state: ConsentState,
    after_action_state: Optional[ConsentState],
    after_reload_state: Optional[ConsentState],
    lifecycle: ConsentLifecycle,
    requests: Sequence[RequestObservation],
    cookies: Sequence[CookieMetadata],
) -> Tuple[CmpFinding, ...]:
    findings: List[CmpFinding] = []
    findings.extend(_detection_findings(url, detections, initial_state, requests, cookies))
    findings.extend(_pre_consent_findings(url, detections, initial_state, requests))
    findings.extend(_lifecycle_findings(url, lifecycle, after_action_state, requests))
    findings.extend(_consent_mode_findings(url, initial_state, requests))
    findings.extend(_state_findings(url, initial_state, after_action_state, after_reload_state, lifecycle))
    return dedupe_findings(tuple(findings))


def _detection_findings(
    url: str,
    detections: Sequence[CmpDetection],
    initial_state: ConsentState,
    requests: Sequence[RequestObservation],
    cookies: Sequence[CookieMetadata],
) -> List[CmpFinding]:
    findings: List[CmpFinding] = []
    unknown_cookies = _recognized_cookie_names_without_detection(cookies, detections)
    if unknown_cookies:
        findings.append(
            CmpFinding.create(
                rule_id="cmp.consent_cookie_without_detection",
                category="discovery",
                severity="informational",
                confidence="suspected",
                title="Consent-related cookie observed without matching CMP detection",
                message=(
                    "A cookie name associated with a supported CMP is present, but that vendor's "
                    "script/global was not detected on this page. This can indicate a stale cookie, "
                    "a consent platform loaded from another subdomain, or incomplete detection."
                ),
                remediation="Confirm which consent system sets the cookie and whether it is still active on this page.",
                component="cmp_detection",
                detection_method="known CMP cookie-name matching",
                evidence=tuple(
                    CmpEvidence(
                        kind="cookie",
                        source="cookie",
                        summary=f"CMP-related cookie present without matching detection: {name}",
                        value=name,
                    )
                    for name in unknown_cookies
                ),
                subject=",".join(unknown_cookies),
            )
        )

    if not detections:
        tracking = [item for item in requests if item.is_tracking]
        findings.append(
            CmpFinding.create(
                rule_id="cmp.no_supported_cmp_detected",
                category="discovery",
                severity="informational",
                confidence="suspected",
                title="No supported CMP signature detected",
                message=(
                    "No supported consent-platform script, global, CMP network endpoint, "
                    "or known consent cookie was observed. This does not prove that consent "
                    "management is absent or ineffective."
                ),
                remediation=(
                    "Verify which consent platform is deployed, or supply a custom adapter/selectors "
                    "if this site uses an unsupported CMP."
                ),
                component="cmp_detection",
                detection_method="static markup, browser globals, cookies, and observed network endpoints",
                evidence=_detection_evidence(detections, cookies),
                subject=url,
            )
        )
        if tracking:
            findings.append(
                CmpFinding.create(
                    rule_id="cmp.tracking_without_supported_cmp",
                    category="consent",
                    severity="low",
                    confidence="suspected",
                    title="Tracking observed without a supported CMP signature",
                    message=(
                        f"{len(tracking)} analytics/advertising request(s) were observed, but no "
                        "supported CMP signature was detected. This may be a custom consent setup, "
                        "a server-side control, or no consent management at all; the evidence cannot "
                        "distinguish those cases."
                    ),
                    remediation=(
                        "Confirm the consent implementation and whether it applies to these requests "
                        "before drawing any compliance conclusion."
                    ),
                    component="cmp_detection",
                    detection_method="network requests plus CMP signature detection",
                    evidence=_request_evidence(tracking, "Tracking request observed"),
                    subject=url,
                )
            )
        return findings

    if not initial_state.has_categories:
        findings.append(
            CmpFinding.create(
                rule_id="cmp.consent_state_unavailable",
                category="consent",
                severity="low",
                confidence="high-confidence",
                title="CMP detected but consent category state is unavailable",
                message=(
                    "A consent platform was detected, but its category state could not be read "
                    "from a documented API or Google Consent Mode. Cookie presence alone was not "
                    "decoded into granted/denied categories."
                ),
                remediation=(
                    "If this vendor exposes a documented consent API, add an adapter for it. Otherwise "
                    "treat category behavior as unverified rather than assuming consent was granted or denied."
                ),
                component=detections[0].adapter_id,
                detection_method="detected CMP with no readable category state",
                evidence=_detection_evidence(detections, cookies),
                subject=detections[0].adapter_id,
            )
        )

    return findings


def _pre_consent_findings(
    url: str,
    detections: Sequence[CmpDetection],
    initial_state: ConsentState,
    requests: Sequence[RequestObservation],
) -> List[CmpFinding]:
    findings: List[CmpFinding] = []
    initial_requests = [item for item in requests if item.phase == "initial" and item.is_tracking]
    if not initial_requests:
        return findings
    by_category: Dict[str, List[RequestObservation]] = {}
    for request in initial_requests:
        by_category.setdefault(request.category, []).append(request)

    for category, category_requests in sorted(by_category.items()):
        value = initial_state.category(category)
        if value is True:
            continue
        if not detections and value is None:
            continue
        certainty = "high-confidence" if value is False else "suspected"
        severity = "high" if value is False else "medium"
        if value is False:
            message = (
                f"{len(category_requests)} {category} request(s) were observed before any consent "
                f"interaction while the observed consent state said {category} was denied."
            )
        else:
            message = (
                f"{len(category_requests)} {category} request(s) were observed before any consent "
                "interaction. The available evidence could not establish whether prior consent was "
                "stored, so this is a lead to verify rather than a proven violation."
            )
        findings.append(
            CmpFinding.create(
                rule_id=f"cmp.tracking_before_consent.{category}",
                category="consent",
                severity=severity,
                confidence=certainty,
                title=f"{category.title()} requests observed before consent",
                message=message,
                remediation=(
                    "Verify the consent state for this session, then ensure the tag is gated on the "
                    "corresponding consent category before any collection request fires."
                ),
                component=f"consent:{category}",
                detection_method="request timestamp ordering against consent state captured at page load",
                evidence=_request_evidence(
                    category_requests,
                    f"{category.title()} request observed before consent",
                )
                + _state_evidence(initial_state),
                subject=f"{url}:{category}",
            )
        )
    return findings


def _lifecycle_findings(
    url: str,
    lifecycle: ConsentLifecycle,
    after_action_state: Optional[ConsentState],
    requests: Sequence[RequestObservation],
) -> List[CmpFinding]:
    findings: List[CmpFinding] = []
    if lifecycle.requested_action != "none" and not lifecycle.performed:
        findings.append(
            CmpFinding.create(
                rule_id="cmp.consent_control_unavailable",
                category="consent",
                severity="medium",
                confidence="confirmed",
                title="Requested consent control could not be operated",
                message=(
                    f"The {lifecycle.requested_action} action was explicitly authorized, but no "
                    f"usable consent control was found ({lifecycle.failure_reason or 'unknown reason'}). "
                    "Post-choice behavior was not tested."
                ),
                remediation=(
                    "Supply a working selector for the deployed CMP version, or review whether the "
                    "consent UI is reachable and operable for this audience."
                ),
                component="consent_lifecycle",
                detection_method="explicit consent-action attempt",
                evidence=(
                    CmpEvidence(
                        kind="lifecycle",
                        source="browser",
                        summary=(
                            f"Consent action {lifecycle.requested_action} failed: "
                            f"{lifecycle.failure_reason or 'unknown reason'}"
                        ),
                        value=lifecycle.selector,
                    ),
                ),
                subject=f"{url}:{lifecycle.requested_action}",
            )
        )
        return findings

    if not lifecycle.performed:
        return findings

    post_action = [item for item in requests if item.phase in {"after_action", "after_reload"} and item.is_tracking]
    if lifecycle.requested_action == "reject" and post_action:
        findings.append(
            CmpFinding.create(
                rule_id="cmp.tracking_after_reject",
                category="consent",
                severity="critical",
                confidence="high-confidence",
                title="Tracking requests observed after reject-all",
                message=(
                    f"{len(post_action)} analytics/advertising request(s) were observed after an "
                    "explicit reject-all interaction in this isolated session."
                ),
                remediation=(
                    "Check that every analytics/advertising tag reads the rejected consent state "
                    "and that no collection request fires after rejection. Re-test with the real CMP "
                    "UI and a fresh profile."
                ),
                component="consent:reject",
                detection_method="explicit reject-all interaction followed by network observation",
                evidence=_request_evidence(post_action, "Tracking request observed after reject-all")
                + (_state_evidence(after_action_state) if after_action_state else ()),
                subject=f"{url}:reject",
            )
        )

    if after_action_state is not None and after_action_state.has_categories:
        if lifecycle.requested_action == "accept":
            denied = [
                name
                for name in ("analytics", "advertising")
                if after_action_state.is_denied(name)
            ]
            if denied:
                findings.append(
                    CmpFinding.create(
                        rule_id="cmp.accept_not_effective",
                        category="consent",
                        severity="medium",
                        confidence="high-confidence",
                        title="Accept action did not grant expected tracking categories",
                        message=(
                            "After the explicit accept-all interaction, the readable consent state "
                            f"still reported denied for: {', '.join(denied)}."
                        ),
                        remediation="Verify the accept control updates the same consent state read by the tags.",
                        component="consent:accept",
                        detection_method="consent state comparison before and after explicit accept",
                        evidence=_state_evidence(after_action_state),
                        subject=f"{url}:accept",
                    )
                )
        elif lifecycle.requested_action == "reject":
            granted = [
                name
                for name in ("analytics", "advertising")
                if after_action_state.is_granted(name)
            ]
            if granted:
                findings.append(
                    CmpFinding.create(
                        rule_id="cmp.reject_not_effective",
                        category="consent",
                        severity="high",
                        confidence="high-confidence",
                        title="Reject action did not deny expected tracking categories",
                        message=(
                            "After the explicit reject-all interaction, the readable consent state "
                            f"still reported granted for: {', '.join(granted)}."
                        ),
                        remediation="Verify the reject control updates the same consent state read by the tags.",
                        component="consent:reject",
                        detection_method="consent state comparison before and after explicit reject",
                        evidence=_state_evidence(after_action_state),
                        subject=f"{url}:reject",
                    )
                )
    return findings


def _consent_mode_findings(
    url: str,
    initial_state: ConsentState,
    requests: Sequence[RequestObservation],
) -> List[CmpFinding]:
    findings: List[CmpFinding] = []
    google_requests = [
        item
        for item in requests
        if item.is_tracking and ("google" in item.host.lower() or "googletagmanager" in item.host.lower())
    ]
    if initial_state.google_mode or not google_requests:
        return findings
    findings.append(
        CmpFinding.create(
            rule_id="cmp.google_consent_mode_missing",
            category="google_consent_mode",
            severity="medium",
            confidence="suspected",
            title="Google tracking observed without Consent Mode signals",
            message=(
                f"{len(google_requests)} Google analytics/advertising request(s) were observed, but "
                "no gtag consent default/update signal was captured. This may mean Consent Mode is "
                "not configured, is implemented outside the observed page, or is server-side."
            ),
            remediation=(
                "Confirm whether Google tags are configured with Consent Mode v2 and whether a "
                "default state is established before those tags load."
            ),
            component="google_consent_mode",
            detection_method="Google request observation plus consent_change event capture",
            evidence=_request_evidence(google_requests, "Google tracking request observed"),
            subject=url,
        )
    )
    return findings


def _state_findings(
    url: str,
    initial_state: ConsentState,
    after_action_state: Optional[ConsentState],
    after_reload_state: Optional[ConsentState],
    lifecycle: ConsentLifecycle,
) -> List[CmpFinding]:
    findings: List[CmpFinding] = []

    if "cookiebot_consent" in initial_state.sources and initial_state.google_mode:
        google_categories = google_categories_from_mode(initial_state.google_mode)
        conflicts = []
        for name in ("analytics", "advertising", "preferences"):
            vendor = initial_state.category(name)
            google = google_categories.get(name)
            if vendor is not None and google is not None and vendor is not google:
                conflicts.append(f"{name}: CMP={'granted' if vendor else 'denied'}, Google={'granted' if google else 'denied'}")
        if conflicts:
            findings.append(
                CmpFinding.create(
                    rule_id="cmp.consent_signal_conflict",
                    category="consent",
                    severity="medium",
                    confidence="high-confidence",
                    title="CMP and Google Consent Mode disagree",
                    message="The vendor consent API and Google Consent Mode reported different states: " + "; ".join(conflicts),
                    remediation=(
                        "Check the integration between the CMP and Google tags. A mismatch can cause "
                        "tags to collect data the CMP believes is blocked, or to remain blocked after consent."
                    ),
                    component="consent_signal",
                    detection_method="vendor consent API compared with Google Consent Mode",
                    evidence=_state_evidence(initial_state),
                    subject=url,
                )
            )

    if not lifecycle.performed or after_action_state is None or after_reload_state is None:
        return findings

    if not after_action_state.has_categories or not after_reload_state.has_categories:
        findings.append(
            CmpFinding.create(
                rule_id="cmp.consent_persistence_unverified",
                category="consent",
                severity="informational",
                confidence="unverified",
                title="Consent persistence could not be verified",
                message=(
                    "The page was reloaded after a consent action, but the readable consent category "
                    "state was unavailable before or after reload. Cookie presence alone was not "
                    "treated as proof that the choice persisted."
                ),
                remediation="Use a CMP with a documented consent API, or review the consent record server-side.",
                component="consent:persistence",
                detection_method="consent action followed by reload",
                evidence=_state_evidence(after_action_state) + _state_evidence(after_reload_state),
                subject=f"{url}:persistence",
            )
        )
        return findings

    changed = []
    for name in ("analytics", "advertising", "preferences"):
        before = after_action_state.category(name)
        after = after_reload_state.category(name)
        if before is not None and after is not None and before is not after:
            changed.append(f"{name}: {'granted' if before else 'denied'} -> {'granted' if after else 'denied'}")
    if changed:
        findings.append(
            CmpFinding.create(
                rule_id="cmp.consent_not_persisted",
                category="consent",
                severity="medium",
                confidence="high-confidence",
                title="Consent choice changed after reload",
                message=(
                    "The consent state observed immediately after the explicit action differed after "
                    "a page reload: " + "; ".join(changed) + "."
                ),
                remediation=(
                    "Verify that the consent choice is stored and re-applied on reload, including for "
                    "returning visitors and the tags that are expected to remain blocked."
                ),
                component="consent:persistence",
                detection_method="consent state comparison after explicit action and page reload",
                evidence=_state_evidence(after_action_state) + _state_evidence(after_reload_state),
                subject=f"{url}:persistence",
            )
        )
    return findings


def _request_evidence(
    requests: Iterable[RequestObservation], summary_prefix: str
) -> Tuple[CmpEvidence, ...]:
    result = []
    for request in list(requests)[:_REPORTED_REQUEST_LIMIT]:
        result.append(
            CmpEvidence(
                kind="network",
                source="network",
                summary=f"{summary_prefix}: {request.host}",
                value=sanitize_url(request.url),
                timestamp=request.timestamp,
            )
        )
    return tuple(result)


def _state_evidence(state: ConsentState) -> Tuple[CmpEvidence, ...]:
    if state is None:
        return ()
    evidence = list(state.evidence)
    known = {name: value for name, value in state.categories.items() if value is not None}
    if known:
        evidence.append(
            CmpEvidence(
                kind="consent_state",
                source=",".join(state.sources),
                summary="Readable consent state",
                value=", ".join(
                    f"{name}={'granted' if value else 'denied'}"
                    for name, value in sorted(known.items())
                ),
                timestamp=state.timestamp,
            )
        )
    return tuple(evidence)


def _detection_evidence(
    detections: Sequence[CmpDetection], cookies: Sequence[CookieMetadata]
) -> Tuple[CmpEvidence, ...]:
    evidence = [item for detection in detections for item in detection.evidence]
    evidence.extend(
        CmpEvidence(
            kind="cookie",
            source="cookie",
            summary=f"CMP-related cookie present: {cookie.name}",
            value=cookie.name,
        )
        for cookie in cookies
        if cookie.cmp_related
    )
    return tuple(evidence)


def _recognized_cookie_names_without_detection(
    cookies: Sequence[CookieMetadata], detections: Sequence[CmpDetection]
) -> List[str]:
    detected_ids = {item.adapter_id for item in detections}
    known_names = {
        adapter.adapter_id: (adapter.cookie_names, adapter.cookie_prefixes)
        for adapter in ADAPTERS
        if adapter.adapter_id not in detected_ids
    }
    matches = set()
    for cookie in cookies:
        for adapter_id, (names, prefixes) in known_names.items():
            if cookie.name in names or any(
                cookie.name.lower().startswith(prefix.lower()) for prefix in prefixes
            ):
                matches.add(cookie.name)
    return sorted(matches)
