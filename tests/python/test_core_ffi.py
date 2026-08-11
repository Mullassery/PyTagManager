"""Direct tests of the Rust <-> Python FFI boundary (`pytagmanager._core`,
built by PyO3/maturin). These import `_core` directly and assert on the
real marshaled PyO3 classes (`SemanticGraph`, `SemanticNode`, `Page`)
rather than going through the Python-side wrapper in
`pytagmanager.discovery.crawl`, which existing tests already exercise
indirectly via `parse_html`.

Requires `maturin develop` (or an installed wheel) to have built the
extension module for the currently active Python interpreter.
"""

from __future__ import annotations

import socket

import pytest

from pytagmanager import _core


def _internet_reachable() -> bool:
    try:
        socket.create_connection(("example.com", 443), timeout=3).close()
        return True
    except OSError:
        return False


def test_parse_html_marshals_semantic_graph_and_node_across_ffi():
    html = """
        <html><body>
            <button data-testid="buy-now" aria-label="Buy now">Buy Now</button>
            <a href="/contact">Contact</a>
        </body></html>
    """
    graph = _core.parse_html(html, "https://example.com/product")

    # The real PyO3-generated classes, not stand-ins.
    assert isinstance(graph, _core.SemanticGraph)
    assert graph.url == "https://example.com/product"
    assert len(graph) == len(graph.nodes)  # __len__ marshaled correctly
    assert "SemanticGraph(" in repr(graph)
    assert all(isinstance(n, _core.SemanticNode) for n in graph.nodes)

    button = next(n for n in graph.nodes if n.tag == "button")
    assert button.stable_selector == '[data-testid="buy-now"]'
    assert button.aria_label == "Buy now"
    assert isinstance(button.attributes, dict)  # Rust HashMap<String,String> -> Python dict
    assert button.attributes["data-testid"] == "buy-now"
    assert isinstance(button.classes, list)  # Rust Vec<String> -> Python list
    assert button.parent_id is not None  # Option<usize> -> Python int, not None here
    assert "SemanticNode(" in repr(button)

    graph_find = graph.find_by_tag("a")
    assert len(graph_find) == 1
    assert graph_find[0].tag == "a"


def test_core_find_by_tag_is_case_insensitive():
    graph = _core.parse_html("<html><body><DIV id='x'></DIV></body></html>", "https://example.com")
    assert len(graph.find_by_tag("div")) == 1
    assert len(graph.find_by_tag("DIV")) == 1


def test_crawl_ssrf_guard_rejects_loopback_across_ffi():
    """The `crawl` pyfunction always uses `Fetcher::new()` (SSRF guard on,
    no way to disable it from Python). The orchestrator swallows individual
    page-fetch failures (including SSRF-guard rejections) rather than
    propagating them (a real, pre-existing crawl() behavior, not specific
    to the guard) -- so the observable result of a fully-blocked crawl is
    an empty page list, not a raised exception. `max_pages=2` is used
    because `max_pages=1` alone is enough to make `crawl()` return `[]`
    (the start URL is already counted as "seen" before the fetch loop
    runs), which would make this assertion pass for the wrong reason.
    """
    pages = _core.crawl("http://127.0.0.1:1/", max_pages=2, concurrency=1, respect_robots=False)
    assert pages == []


def test_crawl_rejects_cloud_metadata_address_across_ffi():
    pages = _core.crawl("http://169.254.169.254/", max_pages=2, concurrency=1, respect_robots=False)
    assert pages == []


@pytest.mark.skipif(not _internet_reachable(), reason="no internet access in this environment")
def test_crawl_returns_real_page_objects_over_ffi():
    """End-to-end through the actual PyO3 `crawl` pyfunction (Tokio runtime,
    real HTTP fetch, real DOM parse) against a stable, IANA-reserved
    documentation domain, asserting on the real marshaled `Page` objects.

    `max_pages=2`, not `1`: with `max_pages=1` the start URL is already
    counted as "seen" before the fetch loop's capacity check runs, so
    `crawl()` returns `[]` without ever fetching anything -- a real,
    pre-existing boundary quirk of `Frontier`/`has_capacity`, not a bug
    introduced here. `example.com` has no further links, so `max_pages=2`
    still yields exactly the one page.
    """
    pages = _core.crawl("https://example.com", max_pages=2, concurrency=1, respect_robots=False)

    assert isinstance(pages, list)
    assert len(pages) == 1
    page = pages[0]
    assert isinstance(page, _core.Page)
    assert page.url.startswith("https://example.com")
    assert page.status == 200
    assert isinstance(page.graph, _core.SemanticGraph)
    assert len(page.graph.nodes) > 0
    assert "Page(" in repr(page)
