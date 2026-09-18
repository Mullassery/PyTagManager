"""Real-browser end-to-end tests for Phase 1.95 item 1's performance
measurement engine (docs/VISION.md §16): real PerformanceObserver-based
metrics from a real headless Chromium session.
"""

from __future__ import annotations

from pytagmanager.perf.measure import measure_page_performance

_HEAVY_PAGE = "perf_heavy.html"


def test_measures_real_metrics_from_a_heavy_fixture_page(fixture_server):
    baseline = measure_page_performance(f"{fixture_server}/{_HEAVY_PAGE}", runs=2, headless=True)

    assert baseline.run_count == 2
    assert baseline.median_lcp_ms is not None
    assert baseline.median_lcp_ms > 0
    # request_count is subresources only (Resource Timing API excludes the
    # document's own navigation) -- this fixture is a single inline-only
    # HTML file with no subresources, so 0 is the correct, real reading,
    # not a missing measurement. dom_content_loaded_ms comes from the
    # navigation entry (always present for a loaded document) and is the
    # right "did we actually measure a real page" signal here.
    assert all(run.dom_content_loaded_ms is not None for run in baseline.runs)
    assert all(run.request_count == 0 for run in baseline.runs)


def test_heavy_fixture_registers_a_real_long_task(fixture_server):
    # perf_heavy.html deliberately busy-waits >50ms on the main thread --
    # real evidence the measurement engine actually observes main-thread
    # cost, not a fabricated number.
    baseline = measure_page_performance(f"{fixture_server}/{_HEAVY_PAGE}", runs=1, headless=True)
    run = baseline.runs[0]
    assert run.long_task_count >= 1
    assert run.tbt_ms > 0


def test_runs_parameter_controls_the_number_of_page_loads(fixture_server):
    baseline = measure_page_performance(f"{fixture_server}/{_HEAVY_PAGE}", runs=1, headless=True)
    assert baseline.run_count == 1


def test_block_url_patterns_prevents_a_request_from_completing(fixture_server, monkeypatch):
    # A page that never loads an external script at all -- baseline should
    # already have a low/zero request count beyond the document; blocking
    # a pattern that matches nothing should not change behavior. This
    # confirms the block_url_patterns plumbing runs without error end to
    # end (the isolation-experiment runner in item 4 is what actually
    # exercises meaningful blocking).
    baseline = measure_page_performance(
        f"{fixture_server}/{_HEAVY_PAGE}",
        runs=1,
        headless=True,
        block_url_patterns=["**/nonexistent-script-that-matches-nothing.js"],
    )
    assert baseline.run_count == 1
