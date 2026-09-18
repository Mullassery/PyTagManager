"""Tests for Phase 1.95 item 5's tagging-vs-performance join
(docs/VISION.md §16)."""

from __future__ import annotations

from pytagmanager.perf.experiments import IsolationExperimentResult
from pytagmanager.perf.scripts import ScriptEntry, ScriptInventory
from pytagmanager.perf.tagging_join import build_tagging_performance_tradeoffs
from pytagmanager.tagexec.graph import NODE_VENDOR_SCRIPT, GraphNode, TagExecutionGraph

_PAGE_URL = "https://shop.example.com/"


def _script(url, category=None, vendor=None, transfer_bytes=100.0):
    return ScriptEntry(
        url=url,
        domain="example.com",
        is_first_party=False,
        resource_type="Script",
        initiator_type="parser",
        initiator_url=None,
        load_mechanism="async",
        transfer_bytes=transfer_bytes,
        load_duration_ms=10.0,
        vendor=vendor,
        category=category,
    )


def test_unclassified_scripts_are_excluded():
    inventory = ScriptInventory(page_url=_PAGE_URL, scripts=(_script("https://shop.example.com/app.js"),))
    assert build_tagging_performance_tradeoffs(inventory) == []


def test_classified_script_produces_a_tradeoff_entry():
    inventory = ScriptInventory(
        page_url=_PAGE_URL,
        scripts=(_script("https://connect.facebook.net/fbevents.js", category="ads", vendor="Meta Pixel"),),
    )
    tradeoffs = build_tagging_performance_tradeoffs(inventory)
    assert len(tradeoffs) == 1
    assert tradeoffs[0].vendor == "Meta Pixel"
    assert tradeoffs[0].category == "ads"


def test_matching_isolation_result_supplies_cost_deltas():
    script_url = "https://connect.facebook.net/fbevents.js"
    inventory = ScriptInventory(page_url=_PAGE_URL, scripts=(_script(script_url, category="ads", vendor="Meta Pixel"),))
    from pytagmanager.perf.measure import PerformanceBaseline, PerformanceSnapshot

    def snap(**overrides):
        defaults = dict(
            lcp_ms=1000.0, lcp_url=None, cls=0.0, fcp_ms=500.0, tbt_ms=100.0, inp_ms=None,
            dom_content_loaded_ms=900.0, load_event_ms=1200.0, transfer_bytes=0.0, request_count=0, long_task_count=0,
        )
        defaults.update(overrides)
        return PerformanceSnapshot(**defaults)

    result = IsolationExperimentResult(
        target_description=f"script {script_url}",
        blocked_urls=(script_url,),
        baseline=PerformanceBaseline(url=_PAGE_URL, runs=(snap(tbt_ms=150.0, lcp_ms=1200.0),)),
        experiment=PerformanceBaseline(url=_PAGE_URL, runs=(snap(tbt_ms=50.0, lcp_ms=1100.0),)),
    )

    tradeoffs = build_tagging_performance_tradeoffs(inventory, [result])
    assert tradeoffs[0].tbt_delta_ms == 100.0
    assert tradeoffs[0].lcp_delta_ms == 100.0


def test_no_matching_result_leaves_cost_fields_none_not_zero():
    inventory = ScriptInventory(
        page_url=_PAGE_URL,
        scripts=(_script("https://connect.facebook.net/fbevents.js", category="ads", vendor="Meta Pixel"),),
    )
    tradeoffs = build_tagging_performance_tradeoffs(inventory, [])
    assert tradeoffs[0].tbt_delta_ms is None
    assert tradeoffs[0].lcp_delta_ms is None


def test_matches_graph_node_by_vendor_label():
    script_url = "https://connect.facebook.net/fbevents.js"
    inventory = ScriptInventory(page_url=_PAGE_URL, scripts=(_script(script_url, category="ads", vendor="Meta Pixel"),))
    graph = TagExecutionGraph(
        nodes=(GraphNode(node_id="vendor:Meta Pixel:x", kind=NODE_VENDOR_SCRIPT, label="Meta Pixel", page_url=_PAGE_URL),)
    )
    tradeoffs = build_tagging_performance_tradeoffs(inventory, [], graph)
    assert tradeoffs[0].graph_node_id == "vendor:Meta Pixel:x"


def test_no_graph_node_match_is_none():
    inventory = ScriptInventory(
        page_url=_PAGE_URL,
        scripts=(_script("https://connect.facebook.net/fbevents.js", category="ads", vendor="Meta Pixel"),),
    )
    graph = TagExecutionGraph(nodes=())
    tradeoffs = build_tagging_performance_tradeoffs(inventory, [], graph)
    assert tradeoffs[0].graph_node_id is None
