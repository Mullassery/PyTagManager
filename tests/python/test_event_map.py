"""Tests for Phase 1.8's Runtime Event Map (docs/VISION.md §14): a
site-wide interaction x {JS, dataLayer, Network, GTM} coverage matrix."""

from __future__ import annotations

import uuid

from pytagmanager.correlation.journey import TrackingJourney
from pytagmanager.observability.events import TrackingEvent
from pytagmanager.sitewide.event_map import build_runtime_event_map


def _journey(business_event, observations):
    return TrackingJourney(
        journey_id=str(uuid.uuid4()),
        business_event=business_event,
        start_time=0.0,
        end_time=1.0,
        observations=observations,
    )


def _event(event_type, source="browser", event_name=""):
    return TrackingEvent.create(source=source, event_type=event_type, event_name=event_name)


def test_full_chain_journey_has_full_coverage():
    journey = _journey(
        "add_to_cart",
        [
            _event("click"),
            _event("dom_insert", source="mutation_observer"),
            _event("datalayer_push", source="datalayer", event_name="add_to_cart"),
            _event("gtm_event", source="gtm", event_name="add_to_cart"),
            _event("network_request", source="network"),
        ],
    )

    rows = build_runtime_event_map([journey])

    assert len(rows) == 1
    row = rows[0]
    assert row.business_event == "add_to_cart"
    assert row.journeys_total == 1
    assert row.js_coverage == 1.0
    assert row.datalayer_coverage == 1.0
    assert row.network_coverage == 1.0
    assert row.gtm_coverage == 1.0


def test_partial_chain_journey_has_partial_coverage():
    journey = _journey(
        "add_to_cart", [_event("click"), _event("datalayer_push", source="datalayer")]
    )

    row = build_runtime_event_map([journey])[0]

    assert row.datalayer_coverage == 1.0
    assert row.js_coverage == 0.0
    assert row.network_coverage == 0.0
    assert row.gtm_coverage == 0.0


def test_groups_by_business_event_across_multiple_journeys():
    healthy = _journey(
        "add_to_cart",
        [
            _event("click"),
            _event("datalayer_push", source="datalayer"),
            _event("network_request", source="network"),
        ],
    )
    silent = _journey("add_to_cart", [_event("click")])

    rows = build_runtime_event_map([healthy, silent])

    assert len(rows) == 1
    row = rows[0]
    assert row.journeys_total == 2
    assert row.datalayer_coverage == 0.5
    assert row.network_coverage == 0.5


def test_distinct_business_events_produce_separate_rows():
    a = _journey("add_to_cart", [_event("click"), _event("datalayer_push", source="datalayer")])
    b = _journey("newsletter_signup", [_event("submit")])

    rows = build_runtime_event_map([a, b])

    names = {row.business_event for row in rows}
    assert names == {"add_to_cart", "newsletter_signup"}


def test_stage_coverage_property_matches_fields():
    journey = _journey("purchase", [_event("click"), _event("gtm_event", source="gtm")])
    row = build_runtime_event_map([journey])[0]
    assert row.stage_coverage == {
        "js": row.js_coverage,
        "datalayer": row.datalayer_coverage,
        "network": row.network_coverage,
        "gtm": row.gtm_coverage,
    }


def test_empty_journeys_produces_empty_map():
    assert build_runtime_event_map([]) == []
