"""Real-browser end-to-end test for Phase 1.95 item 3: building a
dependency graph from a real `ScriptInventory` (item 2)."""

from __future__ import annotations

from pytagmanager.perf.dependency_graph import (
    RELATIONSHIP_LOADED_BY_PARSER,
    build_dependency_graph,
)
from pytagmanager.perf.scripts import build_script_inventory

_PAGE = "perf_scripts.html"


def test_dependency_graph_from_a_real_script_inventory(fixture_server):
    page_url = f"{fixture_server}/{_PAGE}"
    inventory = build_script_inventory(page_url, headless=True, wait_ms=1500)
    graph = build_dependency_graph(inventory)

    local_script_url = next(
        s.url for s in inventory.scripts if s.url.endswith("local_first_party.js")
    )
    local_edge = next(e for e in graph.edges if e.child_url == local_script_url)
    assert local_edge.parent_url == page_url
    assert local_edge.relationship == RELATIONSHIP_LOADED_BY_PARSER

    vendor_script_url = next(s.url for s in inventory.scripts if "fbevents.js" in s.url)
    vendor_edge = next(e for e in graph.edges if e.child_url == vendor_script_url)
    # The vendor script is injected by an inline <script> block, which has
    # no src of its own -- CDP reports its stack frame as the containing
    # document's URL, so the real-world parent here is the page itself.
    assert vendor_edge.parent_url == page_url
