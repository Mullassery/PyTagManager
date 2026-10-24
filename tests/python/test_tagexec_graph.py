"""Tests for Phase 1.85 items 5+6: the Tag Execution Graph assembly and
its unified evidence-label vocabulary (docs/VISION.md §17)."""

from __future__ import annotations

from pytagmanager.diagnostics.trace import InteractionTrace, InteractionTraceStep
from pytagmanager.tagexec.duplicates import (
    DuplicateCandidate,
    DuplicateFinding,
    RuntimeDuplicateEvidence,
)
from pytagmanager.tagexec.graph import (
    EVIDENCE_INFERRED,
    EVIDENCE_LEVELS,
    EVIDENCE_OBSERVED,
    EVIDENCE_SUSPECTED,
    NODE_ENDPOINT,
    NODE_GTM_CONTAINER,
    NODE_SUSPECTED_VENDOR_RELAY,
    NODE_VENDOR_SCRIPT,
    build_graph_json,
    build_tag_execution_graph,
)
from pytagmanager.tagexec.server_side import ServerSideIndicator
from pytagmanager.tagexec.static_scan import (
    GtmContainerDetection,
    StaticScanResult,
    VendorDetection,
)


def _scan(page_url="https://example.com/", gtm_containers=(), vendors=()):
    return StaticScanResult(page_url=page_url, gtm_containers=gtm_containers, vendors=vendors)


def _step(stage, event_type, timestamp, event_name="", payload=None):
    return InteractionTraceStep(
        stage=stage,
        event_type=event_type,
        event_name=event_name,
        timestamp=timestamp,
        source="test",
        selector=None,
        payload=payload or {},
    )


def _trace(
    steps,
    page_url="https://example.com/",
    journey_id="j1",
    business_event="add_to_cart",
):
    return InteractionTrace(
        journey_id=journey_id,
        business_event=business_event,
        page_url=page_url,
        element_selector="#buy",
        start_time=0.0,
        end_time=1.0,
        status="healthy",
        steps=tuple(steps),
    )


# ---- static scan nodes ----


def test_gtm_containers_and_vendors_become_nodes():
    scan = _scan(
        gtm_containers=(GtmContainerDetection("GTM-AAA1111", "script_tag"),),
        vendors=(VendorDetection(vendor="GA4", category="analytics", evidence="gtag config G-X"),),
    )
    graph = build_tag_execution_graph([scan], [])
    kinds = {n.kind for n in graph.nodes}
    assert NODE_GTM_CONTAINER in kinds
    assert NODE_VENDOR_SCRIPT in kinds
    assert graph.node("gtm:GTM-AAA1111") is not None


# ---- trace chain ----


def test_trace_steps_are_chained_with_observed_edges():
    trace = _trace(
        [
            _step("interaction", "click", 1.0),
            _step("datalayer", "datalayer_push", 1.1, event_name="add_to_cart"),
            _step(
                "network",
                "network_request",
                1.2,
                payload={"url": "https://www.google-analytics.com/g/collect"},
            ),
        ]
    )
    graph = build_tag_execution_graph([], [trace])

    step_nodes = [n for n in graph.nodes if n.node_id.startswith("trace:j1:step:")]
    assert len(step_nodes) == 3
    assert all(
        e.evidence == EVIDENCE_OBSERVED for e in graph.edges if e.source_id.startswith("trace:")
    )


def test_network_step_links_to_an_endpoint_node():
    trace = _trace(
        [
            _step(
                "network",
                "network_request",
                1.0,
                payload={"url": "https://www.google-analytics.com/g/collect?x=1"},
            )
        ]
    )
    graph = build_tag_execution_graph([], [trace])

    endpoint = graph.node("endpoint:www.google-analytics.com")
    assert endpoint is not None
    assert endpoint.kind == NODE_ENDPOINT
    edges_to_endpoint = graph.incoming("endpoint:www.google-analytics.com")
    assert len(edges_to_endpoint) == 1
    assert edges_to_endpoint[0].evidence == EVIDENCE_OBSERVED


def test_empty_trace_produces_no_step_nodes():
    trace = _trace([])
    graph = build_tag_execution_graph([], [trace])
    assert graph.nodes == ()
    assert graph.edges == ()


# ---- server-side indicator edges ----


def test_first_party_indicator_adds_inferred_relay_edge_for_likely_confidence():
    trace = _trace(
        [
            _step(
                "network",
                "network_request",
                1.0,
                payload={"url": "https://shop.example.com/g/collect?v=2"},
            )
        ],
        page_url="https://shop.example.com/",
    )
    indicator = ServerSideIndicator(
        kind="first_party_collection_endpoint",
        page_url="https://shop.example.com/",
        business_event="add_to_cart",
        evidence="https://shop.example.com/g/collect?v=2",
        confidence="Likely",
        message="Likely server-side tagging endpoint: ...",
    )
    graph = build_tag_execution_graph([], [trace], server_side_indicators=[indicator])

    relay_edges = [e for e in graph.edges if e.target_id.startswith("relay:")]
    assert len(relay_edges) == 1
    assert relay_edges[0].evidence == EVIDENCE_INFERRED
    relay_node = graph.node(relay_edges[0].target_id)
    assert relay_node.kind == NODE_SUSPECTED_VENDOR_RELAY


def test_fanout_indicator_adds_suspected_edges_between_endpoints():
    trace = _trace(
        [
            _step(
                "network",
                "network_request",
                1.0,
                payload={"url": "https://vendor-a.example/collect"},
            ),
            _step(
                "network",
                "network_request",
                1.1,
                payload={"url": "https://vendor-b.example/collect"},
            ),
        ],
        page_url="https://shop.example.com/",
    )
    indicator = ServerSideIndicator(
        kind="fanout_to_multiple_destinations",
        page_url="https://shop.example.com/",
        business_event="add_to_cart",
        evidence="vendor-a.example, vendor-b.example",
        confidence="Possible",
        message="Possible fan-out: ...",
    )
    graph = build_tag_execution_graph([], [trace], server_side_indicators=[indicator])

    fanout_edges = [
        e
        for e in graph.edges
        if e.source_id == "endpoint:vendor-a.example" and e.target_id == "endpoint:vendor-b.example"
    ]
    assert len(fanout_edges) == 1
    assert fanout_edges[0].evidence == EVIDENCE_SUSPECTED


# ---- duplicate finding edges ----


def test_duplicate_gtm_containers_are_linked():
    scan = _scan(
        gtm_containers=(
            GtmContainerDetection("GTM-AAA1111", "script_tag"),
            GtmContainerDetection("GTM-BBB2222", "script_tag"),
        )
    )
    finding = DuplicateFinding(
        candidate=DuplicateCandidate(
            kind="multiple_gtm_containers",
            description="Multiple GTM containers detected",
            involved=("GTM-AAA1111", "GTM-BBB2222"),
        ),
        runtime_evidence=(
            RuntimeDuplicateEvidence(
                journey_id="j1",
                business_event="add_to_cart",
                request_count=2,
                request_urls=(),
                payload_similarity=1.0,
            ),
        ),
    )
    graph = build_tag_execution_graph([scan], [], duplicate_findings=[finding])

    edge = next(
        (
            e
            for e in graph.edges
            if {e.source_id, e.target_id} == {"gtm:GTM-AAA1111", "gtm:GTM-BBB2222"}
        ),
        None,
    )
    assert edge is not None
    assert edge.evidence == EVIDENCE_OBSERVED


def test_duplicate_finding_with_unresolvable_name_is_skipped_gracefully():
    scan = _scan(gtm_containers=(GtmContainerDetection("GTM-AAA1111", "script_tag"),))
    finding = DuplicateFinding(
        candidate=DuplicateCandidate(
            kind="gtm_plus_hardcoded_vendor",
            description="...",
            involved=("GTM-AAA1111", "SomeVendorNotInScan"),
        ),
        runtime_evidence=(
            RuntimeDuplicateEvidence(
                journey_id="j1",
                business_event="add_to_cart",
                request_count=2,
                request_urls=(),
                payload_similarity=1.0,
            ),
        ),
    )
    # Should not raise, and should not add a spurious edge with a missing node.
    graph = build_tag_execution_graph([scan], [], duplicate_findings=[finding])
    for edge in graph.edges:
        assert graph.node(edge.source_id) is not None
        assert graph.node(edge.target_id) is not None


# ---- evidence vocabulary discipline ----


def test_evidence_levels_match_vision_vocabulary():
    assert EVIDENCE_LEVELS == (
        "Observed",
        "Inferred",
        "Suspected",
        "Unknown",
        "Not observed",
    )


def test_no_edge_ever_uses_an_evidence_level_outside_the_vocabulary():
    scan = _scan(gtm_containers=(GtmContainerDetection("GTM-AAA1111", "script_tag"),))
    trace = _trace(
        [
            _step(
                "network",
                "network_request",
                1.0,
                payload={"url": "https://example.com/g/collect"},
            )
        ],
        page_url="https://example.com/",
    )
    indicator = ServerSideIndicator(
        kind="first_party_collection_endpoint",
        page_url="https://example.com/",
        business_event="add_to_cart",
        evidence="https://example.com/g/collect",
        confidence="Possible",
        message="Possible server-side tagging endpoint: ...",
    )
    graph = build_tag_execution_graph([scan], [trace], server_side_indicators=[indicator])
    for edge in graph.edges:
        assert edge.evidence in EVIDENCE_LEVELS


# ---- JSON serialization ----


def test_build_graph_json_round_trips_structure():
    scan = _scan(gtm_containers=(GtmContainerDetection("GTM-AAA1111", "script_tag"),))
    graph = build_tag_execution_graph([scan], [])
    payload = build_graph_json(graph)

    import json

    serialized = json.dumps(payload)  # must not raise
    assert '"GTM-AAA1111"' in serialized
    assert len(payload["nodes"]) == len(graph.nodes)
    assert len(payload["edges"]) == len(graph.edges)
