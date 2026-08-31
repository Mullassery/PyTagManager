"""End-to-end smoke test for `pytagmanager diagnose --site-wide`: real
browser observation, real template detection + aggregation, both text and
JSON output. The crawl-discovery step itself is substituted with real
SemanticGraphs built via `_core.parse_html()` from the actual fixture HTML
(rather than the real Rust HTTP crawler) because the crawler's SSRF guard
correctly refuses to fetch loopback addresses -- exactly what our local
test HTTP server is -- and that guard is a real security feature, not
something to work around in production code.
"""

import json
from pathlib import Path
from types import SimpleNamespace

from click.testing import CliRunner

from pytagmanager import _core
from pytagmanager.cli import main

_FIXTURES_DIR = Path(__file__).parent / "fixtures" / "observability"


def _fake_page(fixture_server: str, filename: str):
    url = f"{fixture_server}/{filename}"
    html = (_FIXTURES_DIR / filename).read_text()
    graph = _core.parse_html(html, url)
    return SimpleNamespace(url=url, status=200, graph=graph)


def test_diagnose_site_wide_text(fixture_server, monkeypatch):
    pages = [_fake_page(fixture_server, "healthy_tracking.html")]
    monkeypatch.setattr("pytagmanager.cli.crawl_site", lambda *a, **k: pages)

    result = CliRunner().invoke(main, ["diagnose", pages[0].url, "--site-wide", "--format", "text"])

    assert result.exit_code == 0, result.output
    assert "PyTagManager Site Health" in result.output
    assert "1 pages scanned" in result.output
    assert "Site-Wide Tracking Matrix" in result.output


def test_diagnose_site_wide_json(fixture_server, monkeypatch):
    pages = [_fake_page(fixture_server, "healthy_tracking.html")]
    monkeypatch.setattr("pytagmanager.cli.crawl_site", lambda *a, **k: pages)

    result = CliRunner(mix_stderr=False).invoke(main, ["diagnose", pages[0].url, "--site-wide", "--format", "json"])

    assert result.exit_code == 0, result.output
    report = json.loads(result.output)
    assert report["schema_version"] == 1
    assert report["pages_scanned"] == 1
    assert len(report["templates"]) == 1


def test_diagnose_site_wide_semantic_labels(fixture_server, monkeypatch):
    pages = [_fake_page(fixture_server, "healthy_tracking.html")]
    monkeypatch.setattr("pytagmanager.cli.crawl_site", lambda *a, **k: pages)
    # Force the deterministic fallback path -- the real Ollama endpoint's
    # availability/behavior in CI/test environments is not something this
    # test should depend on to be fast and deterministic.
    monkeypatch.setattr(
        "pytagmanager.sitewide.page_type.OllamaPageTypeClassifier.is_available", lambda self: False
    )

    result = CliRunner().invoke(main, ["diagnose", pages[0].url, "--site-wide", "--semantic-labels", "--format", "text"])

    assert result.exit_code == 0, result.output
    assert "PyTagManager Site Health" in result.output


def test_diagnose_site_wide_history_records_first_run(fixture_server, monkeypatch, tmp_path):
    pages = [_fake_page(fixture_server, "healthy_tracking.html")]
    monkeypatch.setattr("pytagmanager.cli.crawl_site", lambda *a, **k: pages)
    history_path = tmp_path / "history.json"

    result = CliRunner().invoke(main, ["diagnose", pages[0].url, "--site-wide", "--history", str(history_path)])

    assert result.exit_code == 0, result.output
    assert "Regression detected" not in result.output  # nothing to compare against on the first run
    from pytagmanager.sitewide.history import load_history

    entries = load_history(str(history_path))
    assert len(entries) == 1


def test_diagnose_site_wide_history_detects_regression_and_alerts(
    fixture_server, monkeypatch, tmp_path, capturing_webhook_server
):
    webhook_url, received = capturing_webhook_server
    history_path = tmp_path / "history.json"
    healthy_page = _fake_page(fixture_server, "healthy_tracking.html")
    broken_page = _fake_page(fixture_server, "missing_datalayer.html")

    # Run 1: healthy page -> a good score recorded as the baseline.
    monkeypatch.setattr("pytagmanager.cli.crawl_site", lambda *a, **k: [healthy_page])
    first = CliRunner().invoke(main, ["diagnose", healthy_page.url, "--site-wide", "--history", str(history_path)])
    assert first.exit_code == 0, first.output

    # Run 2: same URL, but the crawl now only turns up a broken page --
    # simulates the site's tracking regressing between two scheduled runs.
    monkeypatch.setattr("pytagmanager.cli.crawl_site", lambda *a, **k: [broken_page])
    second = CliRunner().invoke(
        main,
        [
            "diagnose",
            healthy_page.url,
            "--site-wide",
            "--history",
            str(history_path),
            "--alert-webhook",
            webhook_url,
            "--alert-threshold",
            "1",
        ],
    )

    assert second.exit_code == 0, second.output
    assert "Regression detected" in second.output
    assert "REGRESSION:" in second.output

    from pytagmanager.sitewide.history import load_history

    assert len(load_history(str(history_path))) == 2
    assert len(received) == 1
    assert "regression" in received[0]["text"].lower()


def test_diagnose_rejects_history_without_site_wide(fixture_server):
    url = f"{fixture_server}/healthy_tracking.html"
    result = CliRunner().invoke(main, ["diagnose", url, "--history", "history.json"])
    assert result.exit_code != 0
    assert "--history requires --site-wide" in result.output


def test_diagnose_rejects_alert_webhook_without_history(fixture_server):
    url = f"{fixture_server}/healthy_tracking.html"
    result = CliRunner().invoke(main, ["diagnose", url, "--site-wide", "--alert-webhook", "https://example.com/hook"])
    assert result.exit_code != 0
    assert "--alert-webhook requires --history" in result.output


def test_diagnose_site_wide_rejects_scenario_combo(fixture_server, tmp_path):
    scenario_path = tmp_path / "s.yml"
    scenario_path.write_text(
        'journey:\n  name: x\n  steps:\n    - action: click\n      selector: "#x"\n'
    )
    url = f"{fixture_server}/healthy_tracking.html"
    result = CliRunner().invoke(
        main, ["diagnose", url, "--site-wide", "--scenario", str(scenario_path)]
    )

    assert result.exit_code != 0
    assert "cannot be combined with --scenario" in result.output
