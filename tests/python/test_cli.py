"""Tests for `pytagmanager.cli`'s Click command wiring: option parsing,
`--export gtm` / `-o` output-path behavior, and pass-through of crawl
options to the (mocked) crawler. `crawl_site` is monkeypatched everywhere
here so these tests exercise only the CLI layer, not the Rust crawler or
network -- that's covered separately (Rust integration tests, and
`tests/python/test_core_ffi.py` for the FFI boundary).
"""

from __future__ import annotations

import json

import pytest
from click.testing import CliRunner

from pytagmanager import cli


class FakeNode:
    def __init__(
        self,
        tag,
        text="",
        classes=None,
        attributes=None,
        aria_label=None,
        aria_role=None,
        stable_selector=None,
        css_selector="body > button:nth-child(1)",
        xpath="/html/body/button[1]",
    ):
        self.tag = tag
        self.text = text
        self.classes = classes or []
        self.attributes = attributes or {}
        self.aria_label = aria_label
        self.aria_role = aria_role
        self.stable_selector = stable_selector
        self.css_selector = css_selector
        self.xpath = xpath


class FakeGraph:
    def __init__(self, url, nodes):
        self.url = url
        self.nodes = nodes


class FakePage:
    def __init__(self, url, status, nodes):
        self.url = url
        self.status = status
        self.graph = FakeGraph(url, nodes)


def _page_with_cta(url="https://example.com/"):
    return FakePage(
        url,
        200,
        [FakeNode("button", text="Add to cart", stable_selector='[data-testid="add-to-cart"]')],
    )


def _page_with_no_recommendations(url="https://example.com/"):
    return FakePage(url, 200, [FakeNode("div", text="just some text")])


@pytest.fixture
def runner():
    return CliRunner()


def test_crawl_without_export_prints_recommendation_summary(monkeypatch, runner):
    monkeypatch.setattr(cli, "crawl_site", lambda *a, **k: [_page_with_cta()])

    result = runner.invoke(cli.main, ["crawl", "https://example.com"])

    assert result.exit_code == 0
    assert "Crawled 1 page(s)." in result.output
    assert "Total recommendations: 1" in result.output
    assert "purchase_intent" in result.output


def test_crawl_with_no_recommendations(monkeypatch, runner):
    monkeypatch.setattr(cli, "crawl_site", lambda *a, **k: [_page_with_no_recommendations()])

    result = runner.invoke(cli.main, ["crawl", "https://example.com"])

    assert result.exit_code == 0
    assert "Total recommendations: 0" in result.output


def test_crawl_export_gtm_without_output_prints_json_to_stdout(monkeypatch, runner):
    monkeypatch.setattr(cli, "crawl_site", lambda *a, **k: [_page_with_cta()])

    result = runner.invoke(cli.main, ["crawl", "https://example.com", "--export", "gtm"])

    assert result.exit_code == 0
    assert "Exported GTM container to" not in result.output
    # The JSON payload is the tail of stdout, after the human-readable summary.
    json_start = result.output.index("{")
    payload = json.loads(result.output[json_start:])
    assert payload["exportFormatVersion"] == 2
    assert len(payload["containerVersion"]["tag"]) == 1


def test_crawl_export_gtm_with_output_writes_file(monkeypatch, runner, tmp_path):
    monkeypatch.setattr(cli, "crawl_site", lambda *a, **k: [_page_with_cta()])
    out_path = tmp_path / "gtm.json"

    result = runner.invoke(
        cli.main,
        ["crawl", "https://example.com", "--export", "gtm", "-o", str(out_path)],
    )

    assert result.exit_code == 0
    assert f"Exported GTM container to {out_path}" in result.output
    assert out_path.exists()
    data = json.loads(out_path.read_text())
    assert data["exportFormatVersion"] == 2
    assert data["containerVersion"]["tag"][0]["parameter"]["eventName"] == "purchase_intent"


def test_crawl_output_option_without_export_is_a_no_op(monkeypatch, runner, tmp_path):
    """`-o` only has an effect when paired with `--export`; passing it alone
    should not write a file or error."""
    monkeypatch.setattr(cli, "crawl_site", lambda *a, **k: [_page_with_cta()])
    out_path = tmp_path / "should_not_be_written.json"

    result = runner.invoke(cli.main, ["crawl", "https://example.com", "-o", str(out_path)])

    assert result.exit_code == 0
    assert not out_path.exists()


def test_crawl_passes_options_through_to_crawl_site(monkeypatch, runner):
    captured = {}

    def fake_crawl_site(url, max_pages, concurrency, respect_robots):
        captured["url"] = url
        captured["max_pages"] = max_pages
        captured["concurrency"] = concurrency
        captured["respect_robots"] = respect_robots
        return [_page_with_no_recommendations()]

    monkeypatch.setattr(cli, "crawl_site", fake_crawl_site)

    result = runner.invoke(
        cli.main,
        ["crawl", "https://example.com", "--max-pages", "5", "--concurrency", "2", "--no-robots"],
    )

    assert result.exit_code == 0
    assert captured == {
        "url": "https://example.com",
        "max_pages": 5,
        "concurrency": 2,
        "respect_robots": False,
    }


def test_crawl_defaults_respect_robots_true(monkeypatch, runner):
    captured = {}
    monkeypatch.setattr(
        cli,
        "crawl_site",
        lambda url, max_pages, concurrency, respect_robots: captured.update(respect_robots=respect_robots)
        or [],
    )

    result = runner.invoke(cli.main, ["crawl", "https://example.com"])

    assert result.exit_code == 0
    assert captured["respect_robots"] is True


def test_crawl_rejects_unsupported_export_format(monkeypatch, runner):
    """GA4, Segment, Snowplow, Tealium, RudderStack, and Adobe Tags are all
    real, implemented exporters now (see pytagmanager.export.base.EXPORTERS);
    XDM-native event modeling is a deliberately deferred, different feature
    (see docs/ARCHITECTURE.md) and has no exporter, so it's still a good
    stand-in for asserting Click's Choice constraint rejects unknown
    `--export` values at the CLI layer with a usage error rather than
    reaching crawl_site at all."""
    called = False

    def fake_crawl_site(*a, **k):
        nonlocal called
        called = True
        return []

    monkeypatch.setattr(cli, "crawl_site", fake_crawl_site)

    result = runner.invoke(cli.main, ["crawl", "https://example.com", "--export", "xdm"])

    assert result.exit_code == 2
    assert not called
    assert "Invalid value" in result.output


@pytest.mark.parametrize(
    "export_format,expected_label",
    [
        ("gtm", "GTM container"),
        ("ga4", "GA4 event config"),
        ("segment", "Segment tracking plan"),
        ("snowplow", "Snowplow schemas"),
        ("tealium", "Tealium iQ profile"),
        ("rudderstack", "RudderStack tracking plan"),
        ("adobe_tags", "Adobe Tags (Launch) rules"),
    ],
)
def test_crawl_export_writes_file_for_every_supported_format(monkeypatch, runner, tmp_path, export_format, expected_label):
    """Every format registered in EXPORTERS is reachable and writable from
    the CLI, not just GTM."""
    monkeypatch.setattr(cli, "crawl_site", lambda *a, **k: [_page_with_cta()])
    out_path = tmp_path / f"{export_format}.json"

    result = runner.invoke(
        cli.main,
        ["crawl", "https://example.com", "--export", export_format, "-o", str(out_path)],
    )

    assert result.exit_code == 0
    assert f"Exported {expected_label} to {out_path}" in result.output
    assert out_path.exists()
    data = json.loads(out_path.read_text())
    assert isinstance(data, dict)
    assert data  # non-empty for a page that generated a recommendation


def test_crawl_save_snapshot_writes_loadable_snapshot_file(monkeypatch, runner, tmp_path):
    monkeypatch.setattr(cli, "crawl_site", lambda *a, **k: [_page_with_cta()])
    snapshot_path = tmp_path / "snapshot.json"

    result = runner.invoke(
        cli.main,
        ["crawl", "https://example.com", "--save-snapshot", str(snapshot_path)],
    )

    assert result.exit_code == 0
    assert f"Saved crawl snapshot to {snapshot_path}" in result.output
    assert snapshot_path.exists()

    from pytagmanager.version_control.snapshot import load_snapshot

    snapshot = load_snapshot(str(snapshot_path))
    assert snapshot.root_url == "https://example.com"
    assert len(snapshot.pages) == 1
    assert snapshot.pages[0].recommendations[0].event_name == "purchase_intent"


def test_diff_command_reports_added_page(monkeypatch, runner, tmp_path):
    old_snapshot_path = tmp_path / "old.json"
    new_snapshot_path = tmp_path / "new.json"

    monkeypatch.setattr(cli, "crawl_site", lambda *a, **k: [_page_with_no_recommendations("https://example.com/")])
    runner.invoke(cli.main, ["crawl", "https://example.com", "--save-snapshot", str(old_snapshot_path)])

    monkeypatch.setattr(
        cli,
        "crawl_site",
        lambda *a, **k: [
            _page_with_no_recommendations("https://example.com/"),
            _page_with_cta("https://example.com/new-page"),
        ],
    )
    runner.invoke(cli.main, ["crawl", "https://example.com", "--save-snapshot", str(new_snapshot_path)])

    result = runner.invoke(cli.main, ["diff", str(old_snapshot_path), str(new_snapshot_path)])

    assert result.exit_code == 0
    assert "Added pages (1):" in result.output
    assert "https://example.com/new-page" in result.output


def test_crawl_truncates_recommendation_list_beyond_twenty(monkeypatch, runner):
    nodes = [
        FakeNode("button", text="add to cart", stable_selector=f'[data-testid="cta-{i}"]') for i in range(25)
    ]
    monkeypatch.setattr(cli, "crawl_site", lambda *a, **k: [FakePage("https://example.com/", 200, nodes)])

    result = runner.invoke(cli.main, ["crawl", "https://example.com"])

    assert result.exit_code == 0
    assert "Total recommendations: 25" in result.output
    assert "... and 5 more" in result.output


def test_main_group_shows_help():
    runner = CliRunner()
    result = runner.invoke(cli.main, ["--help"])
    assert result.exit_code == 0
    assert "crawl" in result.output
