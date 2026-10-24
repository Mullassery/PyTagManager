"""End-to-end test for `pytagmanager crawl --render`: real rendering
through the CLI, with the crawl-discovery step faked for the same
loopback-SSRF-guard reason as every other real-crawl CLI test in this
suite (see test_discovery_crawl_rendered.py)."""

from __future__ import annotations

from types import SimpleNamespace

from click.testing import CliRunner
from pytagmanager.cli import main


def test_crawl_render_flag_finds_recommendation_static_crawl_would_miss(
    fixture_server, monkeypatch
):
    url = f"{fixture_server}/spa_client_rendered.html"
    monkeypatch.setattr(
        "pytagmanager.discovery.crawl.crawl_site",
        lambda *a, **k: [SimpleNamespace(url=url, status=200)],
    )

    result = CliRunner().invoke(main, ["crawl", url, "--render"])

    assert result.exit_code == 0, result.output
    assert "render mode" in result.output
    assert "Crawled 1 page(s)." in result.output
    assert "Purchase Intent" in result.output


def test_crawl_render_flag_with_sniff_and_interactions(fixture_server, monkeypatch, tmp_path):
    url = f"{fixture_server}/spa_client_rendered.html"
    monkeypatch.setattr(
        "pytagmanager.discovery.crawl.crawl_site",
        lambda *a, **k: [SimpleNamespace(url=url, status=200)],
    )

    result = CliRunner().invoke(
        main,
        [
            "crawl",
            url,
            "--render",
            "--sniff-analytics",
            "--simulate-interactions",
            "--screenshots-dir",
            str(tmp_path),
        ],
    )

    assert result.exit_code == 0, result.output
    assert "vendors observed firing" in result.output
    assert "dataLayer present = True" in result.output
    assert "screenshots saved under" in result.output
    assert "click" in result.output
