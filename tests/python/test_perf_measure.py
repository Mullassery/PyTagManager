"""Unit tests for Phase 1.95 item 1's performance measurement engine
(docs/VISION.md §16): pure-Python aggregation logic (no browser)."""

from __future__ import annotations

from pytagmanager.perf.measure import PerformanceBaseline, PerformanceSnapshot


def _snapshot(**overrides):
    defaults = {
        "lcp_ms": 1000.0,
        "lcp_url": "https://example.com/hero.jpg",
        "cls": 0.05,
        "fcp_ms": 500.0,
        "tbt_ms": 100.0,
        "inp_ms": 80.0,
        "dom_content_loaded_ms": 900.0,
        "load_event_ms": 1200.0,
        "transfer_bytes": 50000.0,
        "request_count": 20,
        "long_task_count": 2,
    }
    defaults.update(overrides)
    return PerformanceSnapshot(**defaults)


def test_from_raw_maps_camel_case_js_fields():
    raw = {
        "lcpMs": 1200.5,
        "lcpUrl": "https://example.com/img.jpg",
        "cls": 0.1,
        "fcpMs": 400.0,
        "tbtMs": 250.0,
        "inpMs": 90.0,
        "domContentLoadedMs": 800.0,
        "loadEventMs": 1500.0,
        "transferBytes": 123456.0,
        "requestCount": 15,
        "longTaskCount": 3,
    }
    snapshot = PerformanceSnapshot.from_raw(raw)
    assert snapshot.lcp_ms == 1200.5
    assert snapshot.lcp_url == "https://example.com/img.jpg"
    assert snapshot.cls == 0.1
    assert snapshot.request_count == 15
    assert snapshot.long_task_count == 3


def test_from_raw_handles_missing_fields_with_safe_defaults():
    snapshot = PerformanceSnapshot.from_raw({})
    assert snapshot.lcp_ms is None
    assert snapshot.lcp_url is None
    assert snapshot.cls == 0.0
    assert snapshot.tbt_ms == 0.0
    assert snapshot.inp_ms is None
    assert snapshot.request_count == 0
    assert snapshot.long_task_count == 0


def test_median_across_three_runs():
    baseline = PerformanceBaseline(
        url="https://example.com/",
        runs=(
            _snapshot(lcp_ms=1000.0, tbt_ms=50.0),
            _snapshot(lcp_ms=1500.0, tbt_ms=100.0),
            _snapshot(lcp_ms=2000.0, tbt_ms=150.0),
        ),
    )
    assert baseline.run_count == 3
    assert baseline.median_lcp_ms == 1500.0
    assert baseline.median_tbt_ms == 100.0


def test_median_ignores_none_values():
    baseline = PerformanceBaseline(
        url="https://example.com/",
        runs=(
            _snapshot(inp_ms=None),
            _snapshot(inp_ms=80.0),
            _snapshot(inp_ms=120.0),
        ),
    )
    # Only the two non-None INP values should be considered.
    assert baseline.median_inp_ms == 100.0


def test_empty_baseline_medians_are_none():
    baseline = PerformanceBaseline(url="https://example.com/", runs=())
    assert baseline.run_count == 0
    assert baseline.median_lcp_ms is None
    assert baseline.median_tbt_ms is None
    assert baseline.median_cls is None
    assert baseline.median_request_count is None


def test_all_none_lcp_across_runs_produces_none_median():
    baseline = PerformanceBaseline(
        url="https://example.com/",
        runs=(_snapshot(lcp_ms=None), _snapshot(lcp_ms=None)),
    )
    assert baseline.median_lcp_ms is None
