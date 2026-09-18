"""Unit tests for Phase 1.95 item 4's isolation-experiment logic
(docs/VISION.md §16): grouping, blocked-set closure, and result deltas --
no browser needed."""

from __future__ import annotations

from pytagmanager.perf.dependency_graph import build_dependency_graph
from pytagmanager.perf.experiments import (
    GROUP_TAG_MANAGEMENT,
    IsolationExperimentResult,
    _closure,
    _script_group,
    available_groups,
)
from pytagmanager.perf.measure import PerformanceBaseline, PerformanceSnapshot
from pytagmanager.perf.scripts import ScriptEntry, ScriptInventory

_PAGE_URL = "https://shop.example.com/"


def _script(url, category=None, initiator_type="parser", initiator_url=None):
    return ScriptEntry(
        url=url,
        domain="example.com",
        is_first_party=False,
        resource_type="Script",
        initiator_type=initiator_type,
        initiator_url=initiator_url,
        load_mechanism="async",
        transfer_bytes=100.0,
        load_duration_ms=10.0,
        vendor=category,
        category=category,
    )


def _snapshot(**overrides):
    defaults = dict(
        lcp_ms=1000.0, lcp_url=None, cls=0.05, fcp_ms=500.0, tbt_ms=100.0, inp_ms=80.0,
        dom_content_loaded_ms=900.0, load_event_ms=1200.0, transfer_bytes=5000.0, request_count=5, long_task_count=2,
    )
    defaults.update(overrides)
    return PerformanceSnapshot(**defaults)


# ---- grouping ----


def test_script_group_matches_gtm_loader_url():
    script = _script("https://www.googletagmanager.com/gtm.js?id=GTM-XXX", category=None)
    assert _script_group(script) == GROUP_TAG_MANAGEMENT


def test_script_group_falls_back_to_vendor_category():
    script = _script("https://connect.facebook.net/en_US/fbevents.js", category="ads")
    assert _script_group(script) == "ads"


def test_script_group_none_for_unclassified_first_party_script():
    script = _script("https://shop.example.com/app.js", category=None)
    assert _script_group(script) is None


def test_available_groups_reflects_only_whats_present():
    inventory = ScriptInventory(
        page_url=_PAGE_URL,
        scripts=(
            _script("https://shop.example.com/app.js", category=None),
            _script("https://connect.facebook.net/fbevents.js", category="ads"),
            _script("https://www.googletagmanager.com/gtm.js", category=None),
        ),
    )
    assert available_groups(inventory) == ("ads", GROUP_TAG_MANAGEMENT)


def test_available_groups_empty_when_nothing_classifiable():
    inventory = ScriptInventory(
        page_url=_PAGE_URL, scripts=(_script("https://shop.example.com/app.js", category=None),)
    )
    assert available_groups(inventory) == ()


# ---- closure ----


def test_closure_includes_downstream_scripts():
    inventory = ScriptInventory(
        page_url=_PAGE_URL,
        scripts=(
            _script("https://shop.example.com/gtm.js"),
            _script(
                "https://ga4.example.com/a.js", initiator_type="script", initiator_url="https://shop.example.com/gtm.js"
            ),
        ),
    )
    graph = build_dependency_graph(inventory)
    blocked = _closure(["https://shop.example.com/gtm.js"], graph)
    assert blocked == {"https://shop.example.com/gtm.js", "https://ga4.example.com/a.js"}


def test_closure_of_multiple_seed_urls_unions_their_downstream_sets():
    inventory = ScriptInventory(
        page_url=_PAGE_URL,
        scripts=(
            _script("https://a.example.com/a.js"),
            _script("https://b.example.com/b.js"),
            _script("https://c.example.com/c.js", initiator_type="script", initiator_url="https://a.example.com/a.js"),
        ),
    )
    graph = build_dependency_graph(inventory)
    blocked = _closure(["https://a.example.com/a.js", "https://b.example.com/b.js"], graph)
    assert blocked == {"https://a.example.com/a.js", "https://b.example.com/b.js", "https://c.example.com/c.js"}


# ---- IsolationExperimentResult ----


def test_deltas_computed_as_baseline_minus_experiment():
    result = IsolationExperimentResult(
        target_description="script X",
        blocked_urls=("https://x.example.com/x.js",),
        baseline=PerformanceBaseline(url=_PAGE_URL, runs=(_snapshot(tbt_ms=150.0, lcp_ms=1200.0),)),
        experiment=PerformanceBaseline(url=_PAGE_URL, runs=(_snapshot(tbt_ms=50.0, lcp_ms=1100.0),)),
    )
    assert result.tbt_delta_ms == 100.0  # improved (lower TBT after blocking)
    assert result.lcp_delta_ms == 100.0


def test_delta_is_none_when_baseline_or_experiment_missing():
    result = IsolationExperimentResult(target_description="script X")
    assert result.tbt_delta_ms is None
    assert result.lcp_delta_ms is None


def test_message_reports_observed_impact_not_causal_claim():
    result = IsolationExperimentResult(
        target_description="script https://x.example.com/x.js",
        blocked_urls=("https://x.example.com/x.js",),
        baseline=PerformanceBaseline(url=_PAGE_URL, runs=(_snapshot(tbt_ms=150.0),)),
        experiment=PerformanceBaseline(url=_PAGE_URL, runs=(_snapshot(tbt_ms=50.0),)),
    )
    message = result.message
    assert "observed" in message.lower()
    assert "TBT improved by 100.0ms" in message
    assert "not a general claim" in message


def test_message_handles_no_measurable_change():
    result = IsolationExperimentResult(
        target_description="script X",
        blocked_urls=("https://x.example.com/x.js",),
        baseline=PerformanceBaseline(url=_PAGE_URL, runs=(_snapshot(tbt_ms=50.0, lcp_ms=1000.0, cls=0.0, inp_ms=None),)),
        experiment=PerformanceBaseline(url=_PAGE_URL, runs=(_snapshot(tbt_ms=50.0, lcp_ms=1000.0, cls=0.0, inp_ms=None),)),
    )
    assert "no measurable change" in result.message
