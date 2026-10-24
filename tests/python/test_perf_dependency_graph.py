"""Tests for Phase 1.95 item 3's script dependency graph (docs/VISION.md
§16): script -> script relationships from initiator data, and the
transitive-closure query isolation experiments (item 4) need."""

from __future__ import annotations

from pytagmanager.perf.dependency_graph import (
    RELATIONSHIP_LOADED_BY_OTHER,
    RELATIONSHIP_LOADED_BY_PARSER,
    RELATIONSHIP_LOADED_BY_SCRIPT,
    build_dependency_graph,
)
from pytagmanager.perf.scripts import ScriptEntry, ScriptInventory

_PAGE_URL = "https://shop.example.com/"


def _entry(url, initiator_type="parser", initiator_url=None):
    return ScriptEntry(
        url=url,
        domain="example.com",
        is_first_party=True,
        resource_type="Script",
        initiator_type=initiator_type,
        initiator_url=initiator_url,
        load_mechanism="async",
        transfer_bytes=100.0,
        load_duration_ms=10.0,
        vendor=None,
        category=None,
    )


def test_parser_initiated_script_is_parented_to_the_page():
    inventory = ScriptInventory(
        page_url=_PAGE_URL, scripts=(_entry("https://shop.example.com/gtm.js"),)
    )
    graph = build_dependency_graph(inventory)

    assert len(graph.edges) == 1
    edge = graph.edges[0]
    assert edge.parent_url == _PAGE_URL
    assert edge.child_url == "https://shop.example.com/gtm.js"
    assert edge.relationship == RELATIONSHIP_LOADED_BY_PARSER


def test_script_initiated_script_is_parented_to_the_initiator():
    inventory = ScriptInventory(
        page_url=_PAGE_URL,
        scripts=(
            _entry("https://shop.example.com/gtm.js"),
            _entry(
                "https://www.google-analytics.com/ga4.js",
                initiator_type="script",
                initiator_url="https://shop.example.com/gtm.js",
            ),
        ),
    )
    graph = build_dependency_graph(inventory)

    child_edge = next(
        e for e in graph.edges if e.child_url == "https://www.google-analytics.com/ga4.js"
    )
    assert child_edge.parent_url == "https://shop.example.com/gtm.js"
    assert child_edge.relationship == RELATIONSHIP_LOADED_BY_SCRIPT


def test_script_initiator_with_no_resolvable_url_falls_back_to_page():
    # An inline <script> block has no src, so it never becomes its own
    # inventory node -- but CDP can still report initiator.type=="script"
    # with no usable stack frame URL in edge cases.
    inventory = ScriptInventory(
        page_url=_PAGE_URL,
        scripts=(
            _entry(
                "https://shop.example.com/injected.js",
                initiator_type="script",
                initiator_url=None,
            ),
        ),
    )
    graph = build_dependency_graph(inventory)
    assert graph.edges[0].parent_url == _PAGE_URL
    assert graph.edges[0].relationship == RELATIONSHIP_LOADED_BY_OTHER


def test_downstream_of_computes_transitive_closure():
    inventory = ScriptInventory(
        page_url=_PAGE_URL,
        scripts=(
            _entry("https://shop.example.com/gtm.js"),
            _entry(
                "https://ga4.example.com/a.js",
                initiator_type="script",
                initiator_url="https://shop.example.com/gtm.js",
            ),
            _entry(
                "https://pixel.example.com/b.js",
                initiator_type="script",
                initiator_url="https://shop.example.com/gtm.js",
            ),
            _entry(
                "https://sub.example.com/c.js",
                initiator_type="script",
                initiator_url="https://ga4.example.com/a.js",
            ),
            _entry("https://unrelated.example.com/z.js"),
        ),
    )
    graph = build_dependency_graph(inventory)

    downstream = graph.downstream_of("https://shop.example.com/gtm.js")
    assert downstream == {
        "https://ga4.example.com/a.js",
        "https://pixel.example.com/b.js",
        "https://sub.example.com/c.js",
    }
    assert "https://unrelated.example.com/z.js" not in downstream


def test_downstream_of_leaf_script_is_empty():
    inventory = ScriptInventory(
        page_url=_PAGE_URL,
        scripts=(
            _entry("https://shop.example.com/gtm.js"),
            _entry(
                "https://ga4.example.com/a.js",
                initiator_type="script",
                initiator_url="https://shop.example.com/gtm.js",
            ),
        ),
    )
    graph = build_dependency_graph(inventory)
    assert graph.downstream_of("https://ga4.example.com/a.js") == frozenset()


def test_downstream_of_handles_cycles_without_infinite_loop():
    # Shouldn't happen in real CDP data (a script can't be its own
    # ancestor in time), but the traversal must not hang if it did.
    inventory = ScriptInventory(
        page_url=_PAGE_URL,
        scripts=(
            _entry(
                "https://a.example.com/a.js",
                initiator_type="script",
                initiator_url="https://b.example.com/b.js",
            ),
            _entry(
                "https://b.example.com/b.js",
                initiator_type="script",
                initiator_url="https://a.example.com/a.js",
            ),
        ),
    )
    graph = build_dependency_graph(inventory)
    result = graph.downstream_of("https://a.example.com/a.js")
    assert result == {"https://b.example.com/b.js", "https://a.example.com/a.js"}


def test_children_of_returns_direct_children_only():
    inventory = ScriptInventory(
        page_url=_PAGE_URL,
        scripts=(
            _entry("https://shop.example.com/gtm.js"),
            _entry(
                "https://ga4.example.com/a.js",
                initiator_type="script",
                initiator_url="https://shop.example.com/gtm.js",
            ),
            _entry(
                "https://sub.example.com/c.js",
                initiator_type="script",
                initiator_url="https://ga4.example.com/a.js",
            ),
        ),
    )
    graph = build_dependency_graph(inventory)
    assert graph.children_of("https://shop.example.com/gtm.js") == ("https://ga4.example.com/a.js",)


def test_empty_inventory_produces_empty_graph():
    inventory = ScriptInventory(page_url=_PAGE_URL, scripts=())
    graph = build_dependency_graph(inventory)
    assert graph.edges == ()
    assert graph.downstream_of(_PAGE_URL) == frozenset()
