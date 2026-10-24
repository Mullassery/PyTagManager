"""Tests for `discovery.crawl.crawl_site_rendered` (Phase 1): the
render-mode crawl that composes `runtime.renderer`/`screenshots`/`sniffer`/
`interactions` on top of URL discovery. The discovery step itself is faked
(`SimpleNamespace(url=...)`) for the same reason every other real-crawl
test in this suite fakes it: the Rust crawler's SSRF guard correctly
refuses to fetch the loopback fixture server. Every render/screenshot/
sniff/interaction step downstream of discovery runs for real.
"""

from __future__ import annotations

from types import SimpleNamespace

from pytagmanager.discovery.crawl import crawl_site_rendered


def test_crawl_site_rendered_builds_graph_from_rendered_html(fixture_server, monkeypatch):
    url = f"{fixture_server}/spa_client_rendered.html"
    monkeypatch.setattr(
        "pytagmanager.discovery.crawl.crawl_site",
        lambda *a, **k: [SimpleNamespace(url=url, status=200)],
    )

    pages = crawl_site_rendered(url)

    assert len(pages) == 1
    page = pages[0]
    assert page.url == url
    assert page.status == 200
    assert page.graph.nodes  # rendered DOM parsed into a real SemanticGraph
    assert page.screenshots is None
    assert page.sniff is None
    assert page.interactions == ()


def test_crawl_site_rendered_with_all_optional_observations_enabled(
    fixture_server, monkeypatch, tmp_path
):
    url = f"{fixture_server}/spa_client_rendered.html"
    monkeypatch.setattr(
        "pytagmanager.discovery.crawl.crawl_site",
        lambda *a, **k: [SimpleNamespace(url=url, status=200)],
    )

    pages = crawl_site_rendered(
        url,
        screenshot_dir=str(tmp_path),
        sniff_analytics=True,
        simulate_interactions=True,
        interaction_top_n=2,
    )

    assert len(pages) == 1
    page = pages[0]
    assert page.screenshots is not None
    assert page.screenshots.desktop_full_page.exists()
    assert page.sniff is not None
    assert page.sniff.data_layer_present is True
    assert len(page.interactions) >= 1
    assert all(obs.action == "click" for obs in page.interactions)
