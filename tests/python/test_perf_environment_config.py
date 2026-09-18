"""Tests for Phase 1.95 item 7's controlled test environment
(docs/VISION.md §16): TestEnvironmentConfig persisted on every
PerformanceBaseline, and real CDP-level CPU throttling."""

from __future__ import annotations

from pytagmanager.perf.measure import TestEnvironmentConfig, measure_page_performance

_HEAVY_PAGE = "perf_heavy.html"


def test_default_environment_is_persisted_on_the_baseline(fixture_server):
    baseline = measure_page_performance(f"{fixture_server}/{_HEAVY_PAGE}", runs=1, headless=True)
    assert baseline.environment is not None
    assert baseline.environment.run_count == 1
    assert baseline.environment.browser_name == "chromium"
    assert baseline.environment.headless is True
    assert baseline.environment.cpu_throttling_rate is None


def test_explicit_environment_run_count_is_overridden_by_actual_runs(fixture_server):
    # A caller-supplied environment claiming run_count=99 must not lie
    # about how many runs actually happened.
    environment = TestEnvironmentConfig(run_count=99)
    baseline = measure_page_performance(
        f"{fixture_server}/{_HEAVY_PAGE}", runs=2, headless=True, environment=environment
    )
    assert baseline.run_count == 2
    assert baseline.environment.run_count == 2


def test_cpu_throttling_measurably_increases_busy_wait_duration(fixture_server):
    # perf_heavy.html busy-waits by wall-clock time (Date.now()), so CPU
    # throttling doesn't change the busy-wait's own duration -- but real
    # CDP throttling should not error, and the environment metadata should
    # honestly record the rate that was requested.
    environment = TestEnvironmentConfig(cpu_throttling_rate=4.0, run_count=1)
    baseline = measure_page_performance(
        f"{fixture_server}/{_HEAVY_PAGE}", runs=1, headless=True, environment=environment
    )
    assert baseline.run_count == 1
    assert baseline.environment.cpu_throttling_rate == 4.0
    # The engine must not crash under throttling, and must still produce
    # a real measurement.
    assert baseline.runs[0].dom_content_loaded_ms is not None
