"""Tests for Phase 1.8's formalized Interaction Trace (docs/VISION.md §14):
Finding -> Interaction -> Element -> Timestamp -> JS/dataLayer/GTM/network
events -> storage change, built from an already-diagnosed TrackingJourney."""

from __future__ import annotations

import uuid

from pytagmanager.correlation.journey import TrackingJourney
from pytagmanager.diagnostics.models import Diagnosis
from pytagmanager.diagnostics.trace import (
    build_interaction_trace,
    build_interaction_trace_json,
    build_interaction_traces,
    render_interaction_trace,
)
from pytagmanager.observability.events import TrackingEvent
from pytagmanager.observability.state import StateDiff


def _event(
    event_type,
    timestamp,
    source="browser",
    event_name="",
    selector=None,
    page_url="https://example.com/",
):
    return TrackingEvent.create(
        source=source,
        event_type=event_type,
        event_name=event_name,
        selector=selector,
        page_url=page_url,
        timestamp=timestamp,
    )


def _journey(observations, diagnosis=None):
    journey = TrackingJourney(
        journey_id=str(uuid.uuid4()),
        business_event="add_to_cart",
        start_time=observations[0].timestamp if observations else 0.0,
        end_time=observations[-1].timestamp if observations else 0.0,
        observations=observations,
    )
    if diagnosis is not None:
        journey = journey.with_diagnosis(diagnosis)
    return journey


def test_trace_orders_steps_by_timestamp_and_labels_stages():
    journey = _journey(
        [
            _event(
                "datalayer_push",
                2.0,
                source="datalayer",
                event_name="add_to_cart",
                selector="#buy",
            ),
            _event("click", 1.0, selector="#buy"),
            _event("network_request", 3.0, source="network"),
        ]
    )

    trace = build_interaction_trace(journey)

    assert [s.timestamp for s in trace.steps] == [1.0, 2.0, 3.0]
    assert trace.steps[0].stage == "interaction"
    assert trace.steps[1].stage == "datalayer"
    assert trace.steps[2].stage == "network"
    assert trace.element_selector == "#buy"
    assert trace.page_url == "https://example.com/"


def test_trace_carries_finding_and_confidence_from_diagnosis():
    diagnosis = Diagnosis(
        severity="critical",
        root_cause="missing_datalayer_event",
        message="No dataLayer event fired.",
        rule_name="missing_datalayer_event",
        details={},
        confidence="Confirmed",
    )
    journey = _journey([_event("click", 1.0, selector="#buy")], diagnosis=diagnosis)

    trace = build_interaction_trace(journey)

    assert trace.finding == "No dataLayer event fired."
    assert trace.confidence == "Confirmed"
    assert trace.status == "critical"


def test_trace_with_no_diagnosis_has_no_finding():
    journey = _journey([_event("click", 1.0, selector="#buy")])
    trace = build_interaction_trace(journey)
    assert trace.finding is None
    assert trace.confidence is None


def test_trace_includes_storage_changes_from_correlated_state_diff():
    journey = _journey([_event("click", 1.0, selector="#buy")])
    diff = StateDiff(
        before_label="before",
        after_label="after",
        selector="#buy",
        cookies_added=["session_id"],
        local_storage_modified=["cart_id"],
        new_data_layer_events=["add_to_cart"],
    )

    trace = build_interaction_trace(journey, state_diff=diff)

    categories_and_keys = {(c.category, c.key, c.change) for c in trace.storage_changes}
    assert ("cookie", "session_id", "added") in categories_and_keys
    assert ("local_storage", "cart_id", "modified") in categories_and_keys
    assert trace.new_data_layer_events == ("add_to_cart",)


def test_trace_without_state_diff_has_no_storage_changes():
    journey = _journey([_event("click", 1.0, selector="#buy")])
    trace = build_interaction_trace(journey)
    assert trace.storage_changes == ()
    assert trace.new_data_layer_events == ()


def test_render_interaction_trace_is_human_readable():
    journey = _journey(
        [
            _event("click", 1.0, selector="#buy"),
            _event("datalayer_push", 1.1, source="datalayer", event_name="add_to_cart"),
        ]
    )
    trace = build_interaction_trace(journey)
    rendered = render_interaction_trace(trace)
    assert "add_to_cart" in rendered
    assert "#buy" in rendered
    assert "interaction:" in rendered
    assert "datalayer:" in rendered


def test_build_interaction_trace_json_is_serializable():
    journey = _journey([_event("click", 1.0, selector="#buy")])
    diff = StateDiff(
        before_label="before", after_label="after", selector="#buy", cookies_added=["x"]
    )
    trace = build_interaction_trace(journey, state_diff=diff)

    payload = build_interaction_trace_json(trace)

    import json

    serialized = json.dumps(payload)  # must not raise
    assert '"cookie"' in serialized
    assert payload["journey_id"] == trace.journey_id


def test_build_interaction_traces_joins_by_journey_id():
    journey_a = _journey([_event("click", 1.0, selector="#a")])
    journey_b = _journey([_event("click", 2.0, selector="#b")])
    diff_a = StateDiff(
        before_label="before", after_label="after", selector="#a", cookies_added=["x"]
    )

    traces = build_interaction_traces([journey_a, journey_b], {journey_a.journey_id: diff_a})

    by_id = {t.journey_id: t for t in traces}
    assert len(by_id[journey_a.journey_id].storage_changes) == 1
    assert by_id[journey_b.journey_id].storage_changes == ()
