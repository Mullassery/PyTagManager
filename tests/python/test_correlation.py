from pytagmanager.correlation.journey import correlate_events
from pytagmanager.observability.events import TrackingEvent


def _event(t, source, event_type, event_name="", selector=None, payload=None):
    return TrackingEvent.create(
        timestamp=t, source=source, event_type=event_type, event_name=event_name, selector=selector, payload=payload
    )


def test_correlate_events_groups_by_interaction_anchor():
    events = [
        _event(0.0, "browser", "click", selector="#buy"),
        _event(0.1, "datalayer", "datalayer_push", event_name="add_to_cart"),
        _event(0.2, "network", "network_request", event_name="add_to_cart"),
    ]
    journeys = correlate_events(events, window_seconds=5.0)

    assert len(journeys) == 1
    assert journeys[0].business_event == "add_to_cart"
    assert journeys[0].anchor_selector == "#buy"
    assert journeys[0].stage_present("interaction")
    assert journeys[0].stage_present("datalayer")
    assert journeys[0].stage_present("network")


def test_correlate_events_does_not_merge_across_next_interaction():
    events = [
        _event(0.0, "browser", "click", selector="#a"),
        _event(0.1, "datalayer", "datalayer_push", event_name="event_a"),
        _event(1.0, "browser", "click", selector="#b"),
        _event(1.1, "datalayer", "datalayer_push", event_name="event_b"),
    ]
    journeys = correlate_events(events, window_seconds=5.0)

    assert len(journeys) == 2
    assert journeys[0].business_event == "event_a"
    assert journeys[1].business_event == "event_b"
    # event_b's push must not leak into journey #1's observations.
    assert all(e.event_name != "event_b" for e in journeys[0].observations)


def test_correlate_events_respects_window_boundary():
    events = [
        _event(0.0, "browser", "click", selector="#a"),
        _event(10.0, "datalayer", "datalayer_push", event_name="too_late"),
    ]
    journeys = correlate_events(events, window_seconds=5.0)

    assert len(journeys) == 1
    assert not journeys[0].stage_present("datalayer")


def test_correlate_events_no_interactions_yields_no_journeys():
    events = [_event(0.0, "gtm", "gtm_event", event_name="gtm.js")]
    assert correlate_events(events) == []
