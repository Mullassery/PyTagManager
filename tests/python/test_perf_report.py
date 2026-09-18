"""Tests for Phase 1.95 item 6's script ranking, report rendering, and
per-template aggregation (docs/VISION.md §16)."""

from __future__ import annotations

from pytagmanager.perf.measure import PerformanceBaseline, PerformanceSnapshot
from pytagmanager.perf.report import (
    build_performance_report_json,
    rank_scripts_by_cost,
    render_performance_report,
    summarize_template_performance,
)
from pytagmanager.perf.tagging_join import TaggingPerformanceTradeoff

_PAGE_URL = "https://shop.example.com/"


def _tradeoff(script_url, tbt_delta_ms=None, vendor=None, category="ads"):
    return TaggingPerformanceTradeoff(
        script_url=script_url,
        vendor=vendor,
        category=category,
        tbt_delta_ms=tbt_delta_ms,
        lcp_delta_ms=None,
        transfer_bytes=100.0,
        graph_node_id=None,
    )


def _baseline(**overrides):
    defaults = dict(
        lcp_ms=1000.0, lcp_url=None, cls=0.05, fcp_ms=500.0, tbt_ms=100.0, inp_ms=80.0,
        dom_content_loaded_ms=900.0, load_event_ms=1200.0, transfer_bytes=5000.0, request_count=5, long_task_count=2,
    )
    defaults.update(overrides)
    return PerformanceBaseline(url=_PAGE_URL, runs=(PerformanceSnapshot(**defaults),))


# ---- ranking ----


def test_ranks_highest_cost_first():
    tradeoffs = [
        _tradeoff("https://a.example.com/a.js", tbt_delta_ms=50.0, vendor="A"),
        _tradeoff("https://b.example.com/b.js", tbt_delta_ms=200.0, vendor="B"),
        _tradeoff("https://c.example.com/c.js", tbt_delta_ms=100.0, vendor="C"),
    ]
    ranked = rank_scripts_by_cost(tradeoffs)
    assert [t.vendor for t in ranked] == ["B", "C", "A"]


def test_untested_scripts_sort_last_not_first():
    tradeoffs = [
        _tradeoff("https://a.example.com/a.js", tbt_delta_ms=None, vendor="Untested"),
        _tradeoff("https://b.example.com/b.js", tbt_delta_ms=10.0, vendor="Tested"),
    ]
    ranked = rank_scripts_by_cost(tradeoffs)
    assert [t.vendor for t in ranked] == ["Tested", "Untested"]


def test_empty_tradeoffs_ranks_to_empty():
    assert rank_scripts_by_cost([]) == []


# ---- template summary ----


def test_summarize_template_performance_picks_top_contributors():
    tradeoffs = [
        _tradeoff("https://a.example.com/a.js", tbt_delta_ms=50.0, vendor="A"),
        _tradeoff("https://b.example.com/b.js", tbt_delta_ms=200.0, vendor="B"),
        _tradeoff("https://c.example.com/c.js", tbt_delta_ms=None, vendor="Untested"),
    ]
    summary = summarize_template_performance("Checkout", _baseline(lcp_ms=3700.0, tbt_ms=300.0), tradeoffs, top_n=2)
    assert summary.template_label == "Checkout"
    assert summary.median_lcp_ms == 3700.0
    assert summary.top_contributors == ("B", "A")


def test_summarize_template_performance_with_no_tradeoffs():
    summary = summarize_template_performance("Homepage", _baseline(), [])
    assert summary.top_contributors == ()


# ---- rendering ----


def test_render_performance_report_includes_url_and_metrics():
    lines = render_performance_report(_baseline(), [])
    joined = "\n".join(lines)
    assert _PAGE_URL in joined
    assert "Median LCP" in joined


def test_render_performance_report_includes_ranked_scripts():
    tradeoffs = [_tradeoff("https://a.example.com/a.js", tbt_delta_ms=150.0, vendor="A", category="ads")]
    lines = render_performance_report(_baseline(), tradeoffs)
    joined = "\n".join(lines)
    assert "A (ads)" in joined
    assert "150.0ms TBT" in joined


def test_build_performance_report_json_structure():
    tradeoffs = [_tradeoff("https://a.example.com/a.js", tbt_delta_ms=150.0, vendor="A")]
    payload = build_performance_report_json(_baseline(), tradeoffs)
    assert payload["url"] == _PAGE_URL
    assert payload["median_lcp_ms"] == 1000.0
    assert len(payload["script_ranking"]) == 1
    assert payload["script_ranking"][0]["vendor"] == "A"

    import json

    json.dumps(payload)  # must be JSON-serializable
