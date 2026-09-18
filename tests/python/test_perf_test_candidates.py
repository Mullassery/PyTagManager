"""Tests for Phase 1.95 item 9's performance Test Candidate integration
(docs/VISION.md §16): reuses Phase 1.9's TestCandidate model."""

from __future__ import annotations

from pytagmanager.perf.experiments import IsolationExperimentResult
from pytagmanager.perf.history import PerformanceRegressionAlert
from pytagmanager.perf.measure import PerformanceBaseline, PerformanceSnapshot
from pytagmanager.perf.test_candidates import (
    generate_performance_budget_candidates,
    generate_performance_regression_candidates,
)
from pytagmanager.testintel.candidates import CATEGORY_REGRESSION, CATEGORY_TIMING, SEVERITY_CONFIRMED_DEFECT

_URL = "https://shop.example.com/"


def _snap(**overrides):
    defaults = dict(
        lcp_ms=1000.0, lcp_url=None, cls=0.0, fcp_ms=500.0, tbt_ms=100.0, inp_ms=None,
        dom_content_loaded_ms=900.0, load_event_ms=1200.0, transfer_bytes=0.0, request_count=0, long_task_count=0,
    )
    defaults.update(overrides)
    return PerformanceSnapshot(**defaults)


def _result(tbt_delta_ms):
    baseline = PerformanceBaseline(url=_URL, runs=(_snap(tbt_ms=200.0),))
    experiment = PerformanceBaseline(url=_URL, runs=(_snap(tbt_ms=200.0 - tbt_delta_ms),))
    return IsolationExperimentResult(
        target_description="script https://vendor.example.com/tag.js",
        blocked_urls=("https://vendor.example.com/tag.js",),
        baseline=baseline,
        experiment=experiment,
    )


# ---- performance budget candidates ----


def test_result_exceeding_budget_produces_a_candidate():
    candidates = generate_performance_budget_candidates([_result(250.0)], tbt_budget_ms=200.0)
    assert len(candidates) == 1
    assert candidates[0].category == CATEGORY_TIMING
    assert "vendor.example.com" in candidates[0].observed_problem
    assert candidates[0].evidence_pages == (_URL,)


def test_result_within_budget_produces_no_candidate():
    candidates = generate_performance_budget_candidates([_result(50.0)], tbt_budget_ms=200.0)
    assert candidates == []


def test_result_with_no_delta_produces_no_candidate():
    result = IsolationExperimentResult(target_description="script X", blocked_urls=(), baseline=None, experiment=None)
    assert generate_performance_budget_candidates([result]) == []


def test_severity_never_confirmed_defect():
    candidates = generate_performance_budget_candidates([_result(250.0)], tbt_budget_ms=200.0)
    assert candidates[0].severity != SEVERITY_CONFIRMED_DEFECT


# ---- performance regression candidates ----


def test_regression_alert_produces_a_candidate():
    alert = PerformanceRegressionAlert(
        message="median_lcp_ms regressed by 800.0 vs. the previous run (1000.0 -> 1800.0).",
        metric="median_lcp_ms",
        previous_value=1000.0,
        current_value=1800.0,
        new_scripts=("https://new.example.com/tag.js",),
    )
    candidates = generate_performance_regression_candidates([alert])
    assert len(candidates) == 1
    assert candidates[0].category == CATEGORY_REGRESSION
    assert candidates[0].severity != SEVERITY_CONFIRMED_DEFECT
    assert "median_lcp_ms" in candidates[0].name
    assert candidates[0].observed_problem == alert.message


def test_no_alerts_produces_no_candidates():
    assert generate_performance_regression_candidates([]) == []
