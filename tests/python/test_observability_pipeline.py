"""True end-to-end tests: real headless Chromium (via Playwright), real
agent.js injection, real correlation + rule engine -- against the fixture
pages in fixtures/observability/. The only thing faked is the GA4 network
endpoint itself (intercepted locally so tests never hit the real internet);
everything else is the actual production code path `pytagmanager diagnose`
uses.
"""

from __future__ import annotations

from typing import List

from pytagmanager.correlation.journey import TrackingJourney, correlate_events
from pytagmanager.diagnostics.rules import DiagnosticContext, diagnose_journey, primary_diagnosis
from pytagmanager.observability.scenario import ActionStep, Expectation, Scenario
from pytagmanager.observability.session import ObservationSession

_ADD_TO_CART_SELECTOR = '[data-testid="add-to-cart"]'


def _run(fixture_server: str, page_name: str, scenario: Scenario, wait: float = 1.0) -> List[TrackingJourney]:
    with ObservationSession(headless=True) as session:
        # Fulfill locally instead of hitting the real internet -- request
        # events still fire for `_on_network_request` regardless of how the
        # request is fulfilled.
        session.add_route("https://www.google-analytics.com/**", lambda route: route.fulfill(status=204))
        session.load(f"{fixture_server}/{page_name}")
        session.run_scenario(scenario)
        session.wait(wait)
        events = session.events
    return correlate_events(events, window_seconds=5.0)


def test_healthy_tracking_produces_no_diagnosis(fixture_server):
    scenario = Scenario(
        name="add to cart",
        steps=[ActionStep(action="click", selector=_ADD_TO_CART_SELECTOR)],
        expectations=[Expectation(kind="datalayer_event", value="add_to_cart")],
    )
    journeys = _run(fixture_server, "healthy_tracking.html", scenario)

    assert len(journeys) == 1
    journey = journeys[0]
    assert journey.stage_present("interaction")
    assert journey.stage_present("datalayer")
    assert journey.stage_present("network")

    ctx = DiagnosticContext(expectations_by_selector={_ADD_TO_CART_SELECTOR: scenario.expectations})
    assert diagnose_journey(journey, ctx) == []


def test_event_name_mismatch_detected(fixture_server):
    # healthy_tracking.html actually pushes 'add_to_cart'; declaring a
    # different expectation exercises the mismatch path.
    scenario = Scenario(
        name="add to cart (wrong expectation)",
        steps=[ActionStep(action="click", selector=_ADD_TO_CART_SELECTOR)],
        expectations=[Expectation(kind="datalayer_event", value="add_cart")],
    )
    journeys = _run(fixture_server, "healthy_tracking.html", scenario)
    ctx = DiagnosticContext(expectations_by_selector={_ADD_TO_CART_SELECTOR: scenario.expectations})
    primary = primary_diagnosis(diagnose_journey(journeys[0], ctx))

    assert primary.root_cause == "event_name_mismatch"
    assert primary.details["runtime_event"] == "add_to_cart"
    assert primary.details["expected_event"] == "add_cart"


def test_missing_datalayer_event_detected(fixture_server):
    scenario = Scenario(
        name="broken handler",
        steps=[ActionStep(action="click", selector=_ADD_TO_CART_SELECTOR)],
        expectations=[Expectation(kind="datalayer_event", value="add_to_cart")],
    )
    journeys = _run(fixture_server, "missing_datalayer.html", scenario)
    ctx = DiagnosticContext(expectations_by_selector={_ADD_TO_CART_SELECTOR: scenario.expectations})
    primary = primary_diagnosis(diagnose_journey(journeys[0], ctx))

    assert primary.root_cause == "missing_datalayer_event"


def test_duplicate_tracking_detected(fixture_server):
    scenario = Scenario(name="dup", steps=[ActionStep(action="click", selector=_ADD_TO_CART_SELECTOR)])
    journeys = _run(fixture_server, "duplicate_tracking.html", scenario)
    ctx = DiagnosticContext()
    root_causes = {d.root_cause for d in diagnose_journey(journeys[0], ctx)}

    assert "duplicate_datalayer_event" in root_causes
    assert "duplicate_analytics_request" in root_causes


def test_missing_ga4_request_detected(fixture_server):
    scenario = Scenario(name="no network", steps=[ActionStep(action="click", selector=_ADD_TO_CART_SELECTOR)])
    journeys = _run(fixture_server, "missing_ga4_request.html", scenario)
    ctx = DiagnosticContext()
    primary = primary_diagnosis(diagnose_journey(journeys[0], ctx))

    assert primary.root_cause == "missing_ga4_request"


def test_spa_navigation_missing_pageview_detected(fixture_server):
    scenario = Scenario(name="spa nav", steps=[ActionStep(action="click", selector='[data-testid="nav-products"]')])
    journeys = _run(fixture_server, "spa_tracking.html", scenario)
    ctx = DiagnosticContext()
    primary = primary_diagnosis(diagnose_journey(journeys[0], ctx))

    assert primary.root_cause == "spa_navigation_missing_pageview"
