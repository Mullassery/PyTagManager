"""Tests for Phase 1.7's Website Data Dictionary: aggregation logic (unit,
no browser) and the `pytagmanager dictionary` CLI end-to-end against a real
crawl + browser session."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from click.testing import CliRunner

from pytagmanager import _core, cli
from pytagmanager.dictionary.build import build_data_dictionary
from pytagmanager.dictionary.report import build_dictionary_json, render_dictionary_report
from pytagmanager.observability.state import RuntimeStateSnapshot, StorageEntry

_FIXTURES_DIR = Path(__file__).parent / "fixtures" / "observability"


def _fake_page(fixture_server: str, filename: str):
    # The real Rust crawler's SSRF guard correctly refuses loopback
    # addresses -- exactly what the local fixture server is -- so crawl
    # discovery is substituted with a real SemanticGraph built directly
    # from the fixture HTML, the same pattern test_diagnose_site_wide_cli.py
    # uses. Only the discovery step is faked; ObservationSession still runs
    # a real Chromium against the real fixture_server.
    url = f"{fixture_server}/{filename}"
    html = (_FIXTURES_DIR / filename).read_text()
    graph = _core.parse_html(html, url)
    return SimpleNamespace(url=url, status=200, graph=graph)


def _snapshot(page_url: str, timestamp: float, **overrides) -> RuntimeStateSnapshot:
    defaults = dict(page_url=page_url, timestamp=timestamp, label="page_load")
    defaults.update(overrides)
    return RuntimeStateSnapshot(**defaults)


def test_aggregates_cookies_across_pages_with_presence_ratio():
    entry = StorageEntry(key="visitor_id", value_type="string", length=4)
    snapshots = [
        _snapshot("https://example.com/a", 1.0, cookies={"visitor_id": entry}),
        _snapshot("https://example.com/b", 2.0, cookies={"visitor_id": entry}),
        _snapshot("https://example.com/c", 3.0, cookies={}),
    ]

    result = build_data_dictionary(snapshots)

    assert result.pages_total == 3
    cookies = result.by_source("cookie")
    assert len(cookies) == 1
    assert cookies[0].path == "visitor_id"
    assert cookies[0].observed_count == 2
    assert cookies[0].presence_ratio == 2 / 3


def test_multiple_snapshots_of_the_same_page_do_not_inflate_pages_total():
    entry = StorageEntry(key="cart_id", value_type="string", length=2)
    snapshots = [
        _snapshot("https://example.com/a", 1.0, label="page_load", local_storage={"cart_id": entry}),
        _snapshot("https://example.com/a", 2.0, label="before:step_0", local_storage={"cart_id": entry}),
        _snapshot("https://example.com/a", 3.0, label="after:step_0", local_storage={"cart_id": entry}),
    ]

    result = build_data_dictionary(snapshots)

    assert result.pages_total == 1
    assert result.by_source("local_storage")[0].observed_count == 1


def test_datalayer_events_and_fields_are_tracked_separately():
    snapshots = [
        _snapshot(
            "https://example.com/product",
            1.0,
            data_layer=[{"event": "add_to_cart", "product_id": "p1", "price": 9.99}],
        )
    ]

    result = build_data_dictionary(snapshots)

    events = {v.path: v for v in result.by_source("datalayer_event")}
    fields = {v.path: v for v in result.by_source("datalayer_field")}

    assert "add_to_cart" in events
    assert events["add_to_cart"].value_types == ("event",)
    assert "add_to_cart.product_id" in fields
    assert fields["add_to_cart.product_id"].value_types == ("string",)
    assert "add_to_cart.price" in fields
    assert fields["add_to_cart.price"].value_types == ("number",)


def test_value_type_changing_across_pages_is_recorded_as_multiple_types():
    snapshots = [
        _snapshot("https://example.com/a", 1.0, data_layer=[{"event": "purchase", "transaction_id": "T1"}]),
        _snapshot("https://example.com/b", 2.0, data_layer=[{"event": "purchase", "transaction_id": 123}]),
    ]

    result = build_data_dictionary(snapshots)

    field = next(v for v in result.by_source("datalayer_field") if v.path == "purchase.transaction_id")
    assert field.value_types == ("number", "string")


def test_empty_snapshot_list_produces_empty_dictionary():
    result = build_data_dictionary([])
    assert result.pages_total == 0
    assert result.variables == ()


def test_report_and_json_rendering_do_not_crash_on_empty_dictionary():
    result = build_data_dictionary([])
    assert "No pages" in render_dictionary_report(result)
    assert build_dictionary_json(result) == {"schema_version": 1, "pages_total": 0, "variables": []}


def test_report_rendering_includes_observed_variable():
    snapshots = [_snapshot("https://example.com/a", 1.0, data_layer=[{"event": "page_view"}])]
    result = build_data_dictionary(snapshots)
    rendered = render_dictionary_report(result)
    assert "page_view" in rendered
    assert "1/1 pages" in rendered


# ---- CLI end-to-end (real crawl + real Chromium via fixture_server) ----


def test_dictionary_cli_end_to_end_json(fixture_server, monkeypatch, tmp_path):
    pages = [_fake_page(fixture_server, "runtime_state.html")]
    monkeypatch.setattr("pytagmanager.cli.crawl_site", lambda *a, **k: pages)

    runner = CliRunner()
    out_path = tmp_path / "dictionary.json"

    result = runner.invoke(
        cli.main,
        ["dictionary", pages[0].url, "--format", "json", "-o", str(out_path)],
    )

    assert result.exit_code == 0, result.output
    data = json.loads(out_path.read_text())
    assert data["pages_total"] == 1
    paths = {v["path"] for v in data["variables"]}
    assert "visitor_id" in paths
    assert "cart_id" in paths
