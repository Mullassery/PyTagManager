"""Tests for `runtime.interactions.simulate_interactions` (Phase 1 item 4):
real DOM-mutation and network-request observation around a real click, plus
graceful per-candidate error handling for a selector that can't be found."""

from __future__ import annotations

from pytagmanager.runtime.interactions import simulate_interactions


def test_simulate_interactions_observes_click_mutation_and_network_request(
    fixture_server,
):
    url = f"{fixture_server}/spa_client_rendered.html"

    observations = simulate_interactions(url, ["#cta"])

    assert len(observations) == 1
    obs = observations[0]
    assert obs.selector == "#cta"
    assert obs.action == "click"
    assert obs.error is None
    assert obs.mutation_count > 0
    assert any("google-analytics.com/g/collect" in req for req in obs.network_requests_fired)


def test_simulate_interactions_reports_error_for_missing_selector_without_aborting(
    fixture_server,
):
    url = f"{fixture_server}/spa_client_rendered.html"

    observations = simulate_interactions(url, ["#does-not-exist", "#cta"], timeout_ms=1000)

    by_selector = {obs.selector: obs for obs in observations}
    assert len(observations) == 2
    assert by_selector["#does-not-exist"].error is not None
    assert by_selector["#cta"].error is None


def test_simulate_interactions_bounds_to_top_n_deduplicated_selectors(fixture_server):
    url = f"{fixture_server}/spa_client_rendered.html"

    observations = simulate_interactions(url, ["#cta", "#cta", "#cta"], top_n=1)

    assert len(observations) == 1
