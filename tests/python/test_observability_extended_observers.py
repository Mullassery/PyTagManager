"""True end-to-end tests for the Phase 1.5 observer extensions: fetch/XHR
observation, console.error capture, IntersectionObserver-based visibility,
and the api_call_without_tracking_event rule they enable.
"""

from __future__ import annotations

from pytagmanager.correlation.journey import correlate_events
from pytagmanager.diagnostics.rules import DiagnosticContext, diagnose_journey, primary_diagnosis
from pytagmanager.observability.events import redact_payload
from pytagmanager.observability.scenario import ActionStep, Expectation, Scenario
from pytagmanager.observability.session import ObservationSession

_PAGE = "api_and_console.html"


def test_fetch_call_observed_and_tracking_gap_detected(fixture_server):
    scenario = Scenario(
        name="cart gap",
        steps=[ActionStep(action="click", selector='[data-testid="cart-without-tracking"]')],
        expectations=[Expectation(kind="datalayer_event", value="add_to_cart")],
    )
    with ObservationSession(headless=True) as session:
        session.load(f"{fixture_server}/{_PAGE}")
        session.run_scenario(scenario)
        session.wait(1.0)
        events = session.events

    api_calls = [e for e in events if e.event_type == "api_call"]
    assert any("/api/cart" in e.payload.get("url", "") for e in api_calls)

    journeys = correlate_events(events, window_seconds=5.0)
    ctx = DiagnosticContext(
        expectations_by_selector={'[data-testid="cart-without-tracking"]': scenario.expectations}
    )
    root_causes = {d.root_cause for d in diagnose_journey(journeys[0], ctx)}
    assert "api_call_without_tracking_event" in root_causes
    assert "missing_datalayer_event" in root_causes


def test_fetch_call_with_tracking_produces_no_api_gap_diagnosis(fixture_server):
    scenario = Scenario(
        name="cart healthy",
        steps=[ActionStep(action="click", selector='[data-testid="cart-with-tracking"]')],
        expectations=[Expectation(kind="datalayer_event", value="add_to_cart")],
    )
    with ObservationSession(headless=True) as session:
        session.load(f"{fixture_server}/{_PAGE}")
        session.run_scenario(scenario)
        session.wait(1.0)
        events = session.events

    journeys = correlate_events(events, window_seconds=5.0)
    assert journeys[0].stage_present("application")
    assert journeys[0].stage_present("datalayer")

    ctx = DiagnosticContext(
        expectations_by_selector={'[data-testid="cart-with-tracking"]': scenario.expectations}
    )
    root_causes = {d.root_cause for d in diagnose_journey(journeys[0], ctx)}
    assert "api_call_without_tracking_event" not in root_causes
    assert "missing_datalayer_event" not in root_causes


def test_console_error_observed_as_js_error(fixture_server):
    scenario = Scenario(name="console", steps=[ActionStep(action="click", selector='[data-testid="throw-console-error"]')])
    with ObservationSession(headless=True) as session:
        session.load(f"{fixture_server}/{_PAGE}")
        session.run_scenario(scenario)
        session.wait(0.5)
        events = session.events

    console_errors = [e for e in events if e.event_type == "js_error" and e.event_name == "console"]
    assert len(console_errors) == 1
    assert "checkout" in console_errors[0].payload["message"]


def test_visibility_observed_when_element_scrolled_into_view(fixture_server):
    selector = '[data-testid="impression-target"]'
    with ObservationSession(headless=True, visibility_selectors=[selector]) as session:
        session.load(f"{fixture_server}/{_PAGE}")
        session.scroll_into_view(selector)
        session.wait(0.5)
        events = session.events

    visibility_events = [e for e in events if e.event_type == "visibility"]
    assert len(visibility_events) == 1
    assert visibility_events[0].selector == selector


def test_redact_payload_still_masks_sensitive_keys_in_api_call_payloads():
    # api_call payloads carry raw request URLs/params -- confirm the
    # existing key-based redaction (used by TrackingEvent.create) still
    # applies to this new event type, not just datalayer/network ones.
    payload = redact_payload({"url": "/api/cart", "auth_token": "secret-value"})
    assert payload["auth_token"] == "[REDACTED]"
    assert payload["url"] == "/api/cart"


def test_scroll_depth_milestones_observed_when_scrolled_to_bottom(fixture_server):
    with ObservationSession(headless=True, track_scroll_depth=True) as session:
        session.load(f"{fixture_server}/{_PAGE}")
        session.scroll_into_view('[data-testid="impression-target"]')
        session.wait(0.5)
        events = session.events

    scroll_events = [e for e in events if e.event_type == "scroll_depth"]
    milestones = {e.event_name for e in scroll_events}
    assert "25" in milestones
    assert "100" in milestones
    # Deduped: each milestone emitted at most once per session.
    assert len(scroll_events) == len(milestones)


def test_scroll_depth_becomes_a_journey_anchor(fixture_server):
    with ObservationSession(headless=True, track_scroll_depth=True) as session:
        session.load(f"{fixture_server}/{_PAGE}")
        session.scroll_into_view('[data-testid="impression-target"]')
        session.wait(0.5)
        events = session.events

    journeys = correlate_events(events, window_seconds=5.0)
    scroll_journeys = [j for j in journeys if j.business_event.startswith("scroll_depth:")]
    assert scroll_journeys
    assert scroll_journeys[0].stage_present("interaction")


def test_scroll_depth_not_tracked_when_disabled(fixture_server):
    with ObservationSession(headless=True) as session:
        session.load(f"{fixture_server}/{_PAGE}")
        session.scroll_into_view('[data-testid="impression-target"]')
        session.wait(0.5)
        events = session.events

    assert not [e for e in events if e.event_type == "scroll_depth"]


def test_mutation_dedup_resets_after_spa_route_change(fixture_server):
    scenario = Scenario(
        name="add node, navigate, add node again",
        steps=[
            ActionStep(action="click", selector='[data-testid="add-node"]'),
            ActionStep(action="click", selector='[data-testid="navigate"]'),
            ActionStep(action="click", selector='[data-testid="add-node"]'),
        ],
    )
    with ObservationSession(headless=True) as session:
        session.load(f"{fixture_server}/spa_dedup_reset.html")
        session.run_scenario(scenario)
        session.wait(0.5)
        events = session.events

    dynamic_button_insertions = [
        e for e in events if e.event_type == "dom_insert" and e.selector == '[data-testid="dynamic-button"]'
    ]
    # Without the SPA-navigation dedup reset, the second insertion (after
    # the route change) would be silently suppressed as "already seen".
    assert len(dynamic_button_insertions) == 2

    route_changes = [e for e in events if e.event_type == "route_change"]
    assert len(route_changes) == 1
