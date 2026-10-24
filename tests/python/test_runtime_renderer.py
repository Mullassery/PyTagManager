"""Tests for `runtime.renderer.render_page` (Phase 1 item 1) and the
phase's first exit criterion: a client-rendered SPA fixture that a static
crawl produces zero recommendations for gets real recommendations once
rendered through a browser first.
"""

from __future__ import annotations

from pathlib import Path

from pytagmanager import _core
from pytagmanager.recommend.heuristics import recommend_for_graph
from pytagmanager.runtime.renderer import render_page

_FIXTURES_DIR = Path(__file__).parent / "fixtures" / "observability"


def test_render_page_returns_post_js_html_console_and_network(fixture_server):
    url = f"{fixture_server}/spa_client_rendered.html"

    result = render_page(url)

    assert result.status == 200
    assert result.url == url
    # The injected button only exists after the fixture's inline script
    # runs -- its presence in `result.html` proves this is the live DOM,
    # not the raw HTTP response body (which only has the empty `#app` div).
    assert '<button id="cta">Add to Cart</button>' in result.html
    assert any(
        req.url.startswith("https://www.googletagmanager.com/gtag/js")
        for req in result.network_requests
    )


def test_static_crawl_finds_nothing_but_rendered_crawl_finds_the_cta(fixture_server):
    url = f"{fixture_server}/spa_client_rendered.html"
    raw_html = (_FIXTURES_DIR / "spa_client_rendered.html").read_text()

    static_graph = _core.parse_html(raw_html, url)
    static_recs = recommend_for_graph(static_graph)
    assert static_recs == [], (
        "raw pre-render HTML has no CTA text; a static parse should recommend nothing"
    )

    rendered = render_page(url)
    rendered_graph = _core.parse_html(rendered.html, rendered.url)
    rendered_recs = recommend_for_graph(rendered_graph)

    assert len(rendered_recs) >= 1
    assert any(rec.business_objective == "Purchase Intent" for rec in rendered_recs)
