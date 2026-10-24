"""Tests for the interactive HTML/SVG rendering of the Tag Execution Graph
(RECHECK-052: the graph was previously JSON-only)."""

from __future__ import annotations

import json

from pytagmanager.diagnostics.trace import InteractionTrace, InteractionTraceStep
from pytagmanager.tagexec.graph import (
    EVIDENCE_OBSERVED,
    build_graph_html,
    build_tag_execution_graph,
)
from pytagmanager.tagexec.static_scan import (
    StaticScanResult,
    VendorDetection,
)


def _scan(page_url="https://example.com/", gtm_containers=(), vendors=()):
    return StaticScanResult(page_url=page_url, gtm_containers=gtm_containers, vendors=vendors)


def _step(event_type, timestamp):
    return InteractionTraceStep(
        stage="click",
        event_type=event_type,
        event_name=event_type,
        timestamp=timestamp,
        source="test",
        selector=None,
        payload={},
    )


def _trace_graph():
    trace = InteractionTrace(
        journey_id="j1",
        business_event="add_to_cart",
        page_url="https://example.com/",
        element_selector="#buy",
        start_time=0.0,
        end_time=1.0,
        status="healthy",
        steps=(_step("click", 0.0), _step("datalayer_push", 0.1)),
    )
    return build_tag_execution_graph([], [trace])


def _graph_with_vendor(label="GA4"):
    scan = _scan(vendors=(VendorDetection(vendor=label, category="analytics", evidence="gtag"),))
    return build_tag_execution_graph([scan], [])


def test_returns_standalone_html_document():
    html = build_graph_html(_graph_with_vendor())
    assert html.startswith("<!DOCTYPE html>")
    assert "<svg" in html
    assert "</html>" in html


def test_embeds_machine_readable_graph_data():
    graph = _graph_with_vendor()
    html = build_graph_html(graph)
    marker = '<script id="graph-data" type="application/json">'
    start = html.index(marker) + len(marker)
    end = html.index("</script>", start)
    payload = json.loads(html[start:end])
    assert [n["label"] for n in payload["nodes"]] == ["GA4"]


def test_node_label_is_escaped():
    html = build_graph_html(_graph_with_vendor(label="<script>alert(1)</script>"))
    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;" in html


def test_observed_edges_have_no_dash_pattern():
    graph = _trace_graph()
    assert any(e.evidence == EVIDENCE_OBSERVED for e in graph.edges)
    html = build_graph_html(graph)
    observed_lines = [line for line in html.splitlines() if 'class="edge"' in line]
    assert observed_lines
    for line in observed_lines:
        assert "stroke-dasharray" not in line


def test_empty_graph_renders_without_error():
    html = build_graph_html(build_tag_execution_graph([], []))
    assert "<svg" in html
    assert "0 node(s), 0 edge(s)" in html
