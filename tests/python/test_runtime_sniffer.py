"""Tests for `runtime.sniffer.sniff_page` (Phase 1 item 5) -- real network
classification (reusing `tagexec.static_scan.classify_vendor_url`) plus a
real `window.dataLayer` read."""

from __future__ import annotations

from pytagmanager.runtime.sniffer import sniff_page


def test_sniff_page_detects_vendor_and_datalayer(fixture_server):
    url = f"{fixture_server}/spa_client_rendered.html"

    result = sniff_page(url)

    assert "GA4" in result.vendors
    assert result.data_layer_present is True
    assert {"event": "app_init"} in result.data_layer


def test_sniff_page_reports_absent_datalayer_for_page_without_one(fixture_server):
    result = sniff_page(f"{fixture_server}/missing_datalayer.html")

    assert result.data_layer_present is False
    assert result.data_layer is None
