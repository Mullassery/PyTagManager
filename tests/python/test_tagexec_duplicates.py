"""Tests for Phase 1.85 item 2's duplicate/conflicting implementation
detection (docs/VISION.md §17): static candidates only escalate to a
finding once runtime evidence (Interaction Trace network requests)
corroborates them."""

from __future__ import annotations

from pytagmanager.diagnostics.trace import InteractionTrace, InteractionTraceStep
from pytagmanager.tagexec.duplicates import (
    CANDIDATE_DUPLICATE_VENDOR_IMPLEMENTATION,
    CANDIDATE_GTM_PLUS_HARDCODED_VENDOR,
    CANDIDATE_MULTIPLE_GTM_CONTAINERS,
    analyze_duplicates,
    find_duplicate_candidates,
    find_runtime_duplicate_evidence,
)
from pytagmanager.tagexec.static_scan import (
    GtmContainerDetection,
    StaticScanResult,
    VendorDetection,
)


def _scan(gtm_containers=(), vendors=()):
    return StaticScanResult(
        page_url="https://example.com/", gtm_containers=gtm_containers, vendors=vendors
    )


def _network_step(url, params, timestamp=1.0):
    return InteractionTraceStep(
        stage="network",
        event_type="network_request",
        event_name="",
        timestamp=timestamp,
        source="network",
        selector=None,
        payload={"url": url, "params": params},
    )


def _trace(steps, journey_id="j1", business_event="add_to_cart"):
    return InteractionTrace(
        journey_id=journey_id,
        business_event=business_event,
        page_url="https://example.com/",
        element_selector="#buy",
        start_time=0.0,
        end_time=1.0,
        status="healthy",
        steps=tuple(steps),
    )


# ---- static candidate detection ----


def test_multiple_gtm_containers_is_a_candidate():
    scan = _scan(
        gtm_containers=(
            GtmContainerDetection("GTM-AAA1111", "script_tag"),
            GtmContainerDetection("GTM-BBB2222", "script_tag"),
        )
    )
    candidates = find_duplicate_candidates(scan)
    kinds = {c.kind for c in candidates}
    assert CANDIDATE_MULTIPLE_GTM_CONTAINERS in kinds


def test_single_gtm_container_is_not_a_candidate():
    scan = _scan(gtm_containers=(GtmContainerDetection("GTM-AAA1111", "script_tag"),))
    candidates = find_duplicate_candidates(scan)
    assert not any(c.kind == CANDIDATE_MULTIPLE_GTM_CONTAINERS for c in candidates)


def test_gtm_plus_hardcoded_analytics_vendor_is_a_candidate():
    scan = _scan(
        gtm_containers=(GtmContainerDetection("GTM-AAA1111", "script_tag"),),
        vendors=(
            VendorDetection(vendor="GA4", category="analytics", evidence="gtag config G-ABC"),
        ),
    )
    candidates = find_duplicate_candidates(scan)
    assert any(c.kind == CANDIDATE_GTM_PLUS_HARDCODED_VENDOR for c in candidates)


def test_gtm_plus_hardcoded_chat_vendor_is_not_a_candidate():
    # Chat widgets don't overlap with what a GTM container's own tags send.
    scan = _scan(
        gtm_containers=(GtmContainerDetection("GTM-AAA1111", "script_tag"),),
        vendors=(
            VendorDetection(vendor="Intercom", category="chat", evidence="widget.intercom.io"),
        ),
    )
    candidates = find_duplicate_candidates(scan)
    assert not any(c.kind == CANDIDATE_GTM_PLUS_HARDCODED_VENDOR for c in candidates)


def test_same_vendor_with_distinct_evidence_is_a_duplicate_vendor_candidate():
    scan = _scan(
        vendors=(
            VendorDetection(vendor="GA4", category="analytics", evidence="gtag config G-AAA"),
            VendorDetection(vendor="GA4", category="analytics", evidence="gtag config G-BBB"),
        )
    )
    candidates = find_duplicate_candidates(scan)
    assert any(c.kind == CANDIDATE_DUPLICATE_VENDOR_IMPLEMENTATION for c in candidates)


def test_no_candidates_for_a_clean_single_implementation_page():
    scan = _scan(
        gtm_containers=(GtmContainerDetection("GTM-AAA1111", "script_tag"),),
        vendors=(
            VendorDetection(vendor="Intercom", category="chat", evidence="widget.intercom.io"),
        ),
    )
    assert find_duplicate_candidates(scan) == []


# ---- runtime evidence ----


def test_runtime_evidence_requires_at_least_two_network_requests():
    trace = _trace(
        [_network_step("https://www.google-analytics.com/g/collect", {"en": "add_to_cart"})]
    )
    assert find_runtime_duplicate_evidence(trace) is None


def test_runtime_evidence_computes_payload_similarity():
    trace = _trace(
        [
            _network_step(
                "https://www.google-analytics.com/g/collect",
                {"en": "add_to_cart", "value": "9.99"},
            ),
            _network_step(
                "https://www.google-analytics.com/g/collect",
                {"en": "add_to_cart", "value": "9.99"},
            ),
        ]
    )
    evidence = find_runtime_duplicate_evidence(trace)
    assert evidence is not None
    assert evidence.request_count == 2
    assert evidence.payload_similarity == 1.0


def test_runtime_evidence_similarity_partial_overlap():
    trace = _trace(
        [
            _network_step(
                "https://www.google-analytics.com/g/collect",
                {"en": "add_to_cart", "value": "9.99"},
            ),
            _network_step(
                "https://www.google-analytics.com/g/collect",
                {"en": "add_to_cart", "value": "0.00"},
            ),
        ]
    )
    evidence = find_runtime_duplicate_evidence(trace)
    assert 0.0 < evidence.payload_similarity < 1.0


# ---- escalation: candidate + runtime evidence -> finding ----


def test_candidate_without_runtime_evidence_produces_no_finding():
    scan = _scan(
        gtm_containers=(
            GtmContainerDetection("GTM-AAA1111", "script_tag"),
            GtmContainerDetection("GTM-BBB2222", "script_tag"),
        )
    )
    trace = _trace(
        [_network_step("https://www.google-analytics.com/g/collect", {"en": "add_to_cart"})]
    )

    findings = analyze_duplicates(scan, [trace])
    assert findings == []


def test_candidate_with_runtime_evidence_escalates_to_a_finding():
    scan = _scan(
        gtm_containers=(
            GtmContainerDetection("GTM-AAA1111", "script_tag"),
            GtmContainerDetection("GTM-BBB2222", "script_tag"),
        )
    )
    trace = _trace(
        [
            _network_step("https://www.google-analytics.com/g/collect", {"en": "add_to_cart"}),
            _network_step("https://www.google-analytics.com/g/collect", {"en": "add_to_cart"}),
        ]
    )

    findings = analyze_duplicates(scan, [trace])
    assert len(findings) == 1
    finding = findings[0]
    assert finding.candidate.kind == CANDIDATE_MULTIPLE_GTM_CONTAINERS
    assert "GTM-AAA1111" in finding.message
    assert "GTM-BBB2222" in finding.message
    assert "add_to_cart" in finding.message


def test_no_static_candidates_produces_no_findings_even_with_runtime_evidence():
    scan = _scan(gtm_containers=(GtmContainerDetection("GTM-AAA1111", "script_tag"),))
    trace = _trace(
        [
            _network_step("https://www.google-analytics.com/g/collect", {"en": "add_to_cart"}),
            _network_step("https://www.google-analytics.com/g/collect", {"en": "add_to_cart"}),
        ]
    )
    assert analyze_duplicates(scan, [trace]) == []
