"""Tests for Phase 1.95 item 8's performance regression detection
(docs/VISION.md §16): same append-and-diff pattern as sitewide/history.py,
adapted to raw performance metrics."""

from __future__ import annotations

from pytagmanager.perf.history import (
    PerformanceHistoryEntry,
    append_performance_history_entry,
    detect_performance_regression,
    load_performance_history,
)
from pytagmanager.perf.measure import PerformanceBaseline, PerformanceSnapshot

_URL = "https://shop.example.com/"


def _entry(**overrides):
    defaults = {
        "timestamp": "2026-01-01T00:00:00+00:00",
        "url": _URL,
        "median_lcp_ms": 1000.0,
        "median_tbt_ms": 100.0,
        "median_cls": 0.05,
        "median_inp_ms": 80.0,
        "script_urls": ("https://a.example.com/a.js",),
    }
    defaults.update(overrides)
    return PerformanceHistoryEntry(**defaults)


def _baseline(**overrides):
    defaults = {
        "lcp_ms": 1000.0,
        "lcp_url": None,
        "cls": 0.05,
        "fcp_ms": 500.0,
        "tbt_ms": 100.0,
        "inp_ms": 80.0,
        "dom_content_loaded_ms": 900.0,
        "load_event_ms": 1200.0,
        "transfer_bytes": 5000.0,
        "request_count": 5,
        "long_task_count": 2,
    }
    defaults.update(overrides)
    return PerformanceBaseline(url=_URL, runs=(PerformanceSnapshot(**defaults),))


def test_from_baseline_captures_medians_and_scripts():
    baseline = _baseline(lcp_ms=1200.0, tbt_ms=150.0)
    entry = PerformanceHistoryEntry.from_baseline(
        baseline, script_urls=["https://b.example.com/b.js"]
    )
    assert entry.url == _URL
    assert entry.median_lcp_ms == 1200.0
    assert entry.median_tbt_ms == 150.0
    assert entry.script_urls == ("https://b.example.com/b.js",)


def test_no_history_produces_no_alerts():
    assert detect_performance_regression([], _entry()) == []


def test_lcp_regression_above_threshold_is_detected():
    previous = _entry(median_lcp_ms=1000.0)
    latest = _entry(median_lcp_ms=1800.0)  # +800ms, above the 500ms default threshold
    alerts = detect_performance_regression([previous], latest)
    assert len(alerts) == 1
    assert alerts[0].metric == "median_lcp_ms"
    assert alerts[0].previous_value == 1000.0
    assert alerts[0].current_value == 1800.0


def test_small_change_below_threshold_is_not_a_regression():
    previous = _entry(median_lcp_ms=1000.0, median_tbt_ms=100.0)
    latest = _entry(median_lcp_ms=1050.0, median_tbt_ms=110.0)
    assert detect_performance_regression([previous], latest) == []


def test_improvement_is_not_a_regression():
    previous = _entry(median_lcp_ms=2000.0)
    latest = _entry(median_lcp_ms=1000.0)
    assert detect_performance_regression([previous], latest) == []


def test_newly_introduced_script_is_correlated_in_the_message():
    previous = _entry(median_tbt_ms=100.0, script_urls=("https://a.example.com/a.js",))
    latest = _entry(
        median_tbt_ms=300.0,
        script_urls=(
            "https://a.example.com/a.js",
            "https://new-vendor.example.com/tag.js",
        ),
    )
    alerts = detect_performance_regression([previous], latest)
    assert len(alerts) == 1
    assert "new-vendor.example.com" in alerts[0].message
    assert "not proven causal" in alerts[0].message
    assert alerts[0].new_scripts == ("https://new-vendor.example.com/tag.js",)


def test_history_round_trips_through_disk(tmp_path):
    path = str(tmp_path / "perf_history.json")
    assert load_performance_history(path) == []

    entry = _entry()
    append_performance_history_entry(path, entry)
    reloaded = load_performance_history(path)
    assert len(reloaded) == 1
    assert reloaded[0].url == _URL
    assert reloaded[0].median_lcp_ms == 1000.0
    assert reloaded[0].script_urls == ("https://a.example.com/a.js",)
