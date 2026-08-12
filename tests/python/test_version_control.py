"""Integration tests for the version-control / change-detection capability
(python/pytagmanager/version_control/{snapshot,diff}.py).

Unlike test_heuristics.py/test_gtm_export.py (which use hand-built
dataclasses), this drives the real Rust FFI boundary end-to-end: HTML ->
`pytagmanager._core.parse_html()` -> real `SemanticGraph`/`SemanticNode`
objects -> `recommend_for_graph()` -> `build_snapshot()` -> JSON file on
disk -> `load_snapshot()` -> `diff_snapshots()`. This is the same DOM-graph
and recommendation machinery a real `pytagmanager crawl` run produces (the
crawl-fixture HTML fixtures are parsed exactly like a fetched page would
be); only the network fetch itself is skipped, matching how
`test_core_ffi.py` isolates FFI-level behavior from live network access.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from pytagmanager import _core
from pytagmanager.recommend.heuristics import recommend_for_graph
from pytagmanager.version_control.diff import diff_snapshots, format_diff_report
from pytagmanager.version_control.snapshot import build_snapshot, load_snapshot, save_snapshot

_OLD_HOME_HTML = """
<html><body>
    <button data-testid="add-to-cart">Add to Cart</button>
    <a href="/contact">Contact Us</a>
    <form id="newsletter-form"></form>
</body></html>
"""

# vs. old: "Contact Us" link removed, add-to-cart button's text changed
# (same data-testid identity), a brand-new "Subscribe" button added, form
# unchanged.
_NEW_HOME_HTML = """
<html><body>
    <button data-testid="add-to-cart">Buy Now</button>
    <button data-testid="subscribe-btn">Subscribe</button>
    <form id="newsletter-form"></form>
</body></html>
"""

_ABOUT_HTML = """
<html><body><p>About us.</p></body></html>
"""


class _FakePage:
    """Duck-types `pytagmanager._core.Page` (url/status/graph) around a
    real `SemanticGraph` from `_core.parse_html`, standing in for the
    network fetch step `crawl_site()` would otherwise perform."""

    def __init__(self, url: str, graph: _core.SemanticGraph, status: int = 200):
        self.url = url
        self.status = status
        self.graph = graph


def _crawl_output(pages_html: dict) -> tuple:
    """Return (pages, recs_by_url) built the same way `pytagmanager crawl`
    builds them: real `_core.parse_html` graphs run through the real
    `recommend_for_graph` heuristics engine."""
    pages = []
    recs_by_url = {}
    for url, html in pages_html.items():
        graph = _core.parse_html(html, url)
        pages.append(_FakePage(url, graph))
        recs_by_url[url] = recommend_for_graph(graph)
    return pages, recs_by_url


def test_snapshot_round_trips_through_disk():
    pages, recs_by_url = _crawl_output({"https://example.com/": _OLD_HOME_HTML})
    snapshot = build_snapshot(pages, recs_by_url, root_url="https://example.com/")

    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "snapshot.json"
        save_snapshot(snapshot, str(path))
        assert path.exists()

        loaded = load_snapshot(str(path))

    assert loaded.root_url == "https://example.com/"
    assert len(loaded.pages) == 1
    page = loaded.pages[0]
    assert page.url == "https://example.com/"
    assert page.status == 200
    assert len(page.nodes) == len(pages[0].graph.nodes)
    node_keys = {n.identity_key for n in page.nodes}
    assert '[data-testid="add-to-cart"]' in node_keys
    assert len(page.recommendations) == len(recs_by_url["https://example.com/"])


def test_diff_detects_added_removed_and_changed_elements_across_real_crawls():
    old_pages, old_recs = _crawl_output(
        {
            "https://example.com/": _OLD_HOME_HTML,
            "https://example.com/about": _ABOUT_HTML,
        }
    )
    new_pages, new_recs = _crawl_output(
        {
            "https://example.com/": _NEW_HOME_HTML,
            "https://example.com/pricing": _ABOUT_HTML,  # new page (about's URL removed, pricing added)
        }
    )

    old_snapshot = build_snapshot(old_pages, old_recs, root_url="https://example.com/")
    new_snapshot = build_snapshot(new_pages, new_recs, root_url="https://example.com/")

    with tempfile.TemporaryDirectory() as tmp:
        old_path = Path(tmp) / "old.json"
        new_path = Path(tmp) / "new.json"
        save_snapshot(old_snapshot, str(old_path))
        save_snapshot(new_snapshot, str(new_path))

        diff = diff_snapshots(load_snapshot(str(old_path)), load_snapshot(str(new_path)))

    # Page-level changes.
    assert diff.added_pages == ["https://example.com/pricing"]
    assert diff.removed_pages == ["https://example.com/about"]
    assert len(diff.changed_pages) == 1  # only the home page is present in both and differs

    home_diff = diff.changed_pages[0]
    assert home_diff.url == "https://example.com/"

    # Element-level changes on the home page.
    added_keys = {n.identity_key for n in home_diff.added_elements}
    assert '[data-testid="subscribe-btn"]' in added_keys

    removed_selectors = {n.css_selector for n in home_diff.removed_elements}
    # The <a href="/contact"> link has no stable attribute, so its identity
    # key is its (positional) css_selector -- it should show up as removed.
    assert any("a" in sel or True for sel in removed_selectors)  # sanity: at least parses
    removed_tags = {n.tag for n in home_diff.removed_elements}
    assert "a" in removed_tags

    # The add-to-cart button kept its identity (data-testid unchanged) but
    # its text changed -> reported as a changed element, not added+removed.
    changed_keys = {c.identity_key for c in home_diff.changed_elements}
    assert '[data-testid="add-to-cart"]' in changed_keys
    add_to_cart_change = next(c for c in home_diff.changed_elements if c.identity_key == '[data-testid="add-to-cart"]')
    text_change = next(fc for fc in add_to_cart_change.field_changes if fc.field == "text")
    assert text_change.old == "Add to Cart"
    assert text_change.new == "Buy Now"

    # Recommendation-level changes follow from the element changes: a new
    # "Subscribe" CTA recommendation should appear as added.
    added_rec_events = {r.event_name for r in home_diff.added_recommendations}
    assert "subscription" in added_rec_events


def test_diff_snapshots_reports_no_changes_for_identical_snapshots():
    pages, recs_by_url = _crawl_output({"https://example.com/": _OLD_HOME_HTML})
    snapshot = build_snapshot(pages, recs_by_url, root_url="https://example.com/")

    diff = diff_snapshots(snapshot, snapshot)

    assert diff.added_pages == []
    assert diff.removed_pages == []
    assert diff.changed_pages == []
    assert diff.unchanged_page_count == 1


def test_format_diff_report_is_human_readable_text():
    old_pages, old_recs = _crawl_output({"https://example.com/": _OLD_HOME_HTML})
    new_pages, new_recs = _crawl_output({"https://example.com/": _NEW_HOME_HTML})
    old_snapshot = build_snapshot(old_pages, old_recs, root_url="https://example.com/")
    new_snapshot = build_snapshot(new_pages, new_recs, root_url="https://example.com/")

    report = format_diff_report(diff_snapshots(old_snapshot, new_snapshot))

    assert "Changed pages (1):" in report
    assert '[data-testid="subscribe-btn"]' in report
