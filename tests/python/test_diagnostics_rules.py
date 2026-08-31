import uuid

from pytagmanager.analytics_api.models import GtmTag, GtmTrigger
from pytagmanager.correlation.journey import TrackingJourney
from pytagmanager.diagnostics.rules import (
    DiagnosticContext,
    diagnose_journey,
    find_duplicate_purchases,
    find_untested_recommendations,
    primary_diagnosis,
)
from pytagmanager.observability.events import TrackingEvent
from pytagmanager.recommend.models import TrackingRecommendation


def _journey(observations, business_event="add_to_cart"):
    return TrackingJourney(
        journey_id=str(uuid.uuid4()),
        business_event=business_event,
        start_time=0.0,
        end_time=1.0,
        observations=observations,
    )


def _event(event_type, source="browser", event_name="", selector=None, payload=None):
    return TrackingEvent.create(source=source, event_type=event_type, event_name=event_name, selector=selector, payload=payload)


def test_gtm_tag_not_executed_when_trigger_matches_but_nothing_downstream():
    trigger = GtmTrigger(trigger_id="1", name="Add To Cart Trigger", type="CUSTOM_EVENT", event_name="add_to_cart")
    tag = GtmTag(tag_id="10", name="GA4 - Add to Cart", type="gaawe", firing_trigger_ids=["1"])
    journey = _journey(
        [
            _event("click", selector="#buy"),
            _event("datalayer_push", source="datalayer", event_name="add_to_cart"),
        ]
    )
    ctx = DiagnosticContext(gtm_triggers=[trigger], gtm_tags=[tag])

    primary = primary_diagnosis(diagnose_journey(journey, ctx))
    assert primary.root_cause == "gtm_tag_not_executed"
    assert "GA4 - Add to Cart" in primary.details["affected_tags"]


def test_consent_blocking_detected():
    journey = _journey(
        [
            _event("click", selector="#buy"),
            _event("datalayer_push", source="datalayer", event_name="add_to_cart"),
            _event("consent_change", source="consent", event_name="update", payload={"analytics_storage": "denied"}),
        ]
    )
    ctx = DiagnosticContext()
    primary = primary_diagnosis(diagnose_journey(journey, ctx))
    assert primary.root_cause == "consent_blocked"


def test_pii_leak_detected_in_datalayer_payload():
    journey = _journey(
        [
            _event("click", selector="#form"),
            _event("datalayer_push", source="datalayer", event_name="generate_lead", payload={"search_term": "contact me at jane@example.com"}),
        ]
    )
    ctx = DiagnosticContext()
    root_causes = {d.root_cause for d in diagnose_journey(journey, ctx)}
    assert "pii_leak_detected" in root_causes


def test_healthy_journey_with_full_gtm_config_produces_no_diagnosis():
    trigger = GtmTrigger(trigger_id="1", name="Add To Cart Trigger", type="CUSTOM_EVENT", event_name="add_to_cart")
    tag = GtmTag(tag_id="10", name="GA4 - Add to Cart", type="gaawe", firing_trigger_ids=["1"])
    journey = _journey(
        [
            _event("click", selector="#buy"),
            _event(
                "datalayer_push",
                source="datalayer",
                event_name="add_to_cart",
                payload={"value": 19.99, "currency": "USD", "items": [{"item_id": "sku123"}]},
            ),
            _event(
                "network_request",
                source="network",
                payload={
                    "url": "https://www.google-analytics.com/g/collect",
                    "params": {"en": "add_to_cart", "ep.value": "19.99", "ep.currency": "USD"},
                },
            ),
        ]
    )
    ctx = DiagnosticContext(gtm_triggers=[trigger], gtm_tags=[tag])
    assert diagnose_journey(journey, ctx) == []


def test_ecommerce_missing_parameters_flags_incomplete_purchase():
    journey = _journey(
        [
            _event("click", selector="#checkout"),
            # Missing transaction_id and currency.
            _event("datalayer_push", source="datalayer", event_name="purchase", payload={"value": 49.99, "items": []}),
        ],
        business_event="purchase",
    )
    ctx = DiagnosticContext()
    diagnosis = next(d for d in diagnose_journey(journey, ctx) if d.root_cause == "ecommerce_missing_parameters")
    assert diagnosis.confidence == "Confirmed"
    assert "transaction_id" in diagnosis.details["missing_parameters"]
    assert "currency" in diagnosis.details["missing_parameters"]


def test_ecommerce_missing_parameters_silent_for_non_ecommerce_events():
    journey = _journey(
        [_event("click", selector="#subscribe"), _event("datalayer_push", source="datalayer", event_name="newsletter_signup")],
        business_event="newsletter_signup",
    )
    ctx = DiagnosticContext()
    assert all(d.root_cause != "ecommerce_missing_parameters" for d in diagnose_journey(journey, ctx))


def test_find_duplicate_purchases_across_journeys():
    complete_payload = {"transaction_id": "T1", "value": 10.0, "currency": "USD", "items": [{"item_id": "x"}]}
    journey_a = _journey(
        [_event("click", selector="#confirm"), _event("datalayer_push", source="datalayer", event_name="purchase", payload=complete_payload)],
        business_event="purchase",
    )
    journey_b = _journey(
        [_event("click", selector="#confirm"), _event("datalayer_push", source="datalayer", event_name="purchase", payload=complete_payload)],
        business_event="purchase",
    )

    findings = find_duplicate_purchases([journey_a, journey_b])
    assert len(findings) == 1
    assert findings[0].root_cause == "duplicate_purchase"
    assert findings[0].details["transaction_id"] == "T1"
    assert findings[0].details["count"] == 2


def test_find_duplicate_purchases_ignores_distinct_transactions():
    journey_a = _journey(
        [_event("datalayer_push", source="datalayer", event_name="purchase", payload={"transaction_id": "T1"})],
    )
    journey_b = _journey(
        [_event("datalayer_push", source="datalayer", event_name="purchase", payload={"transaction_id": "T2"})],
    )
    assert find_duplicate_purchases([journey_a, journey_b]) == []


def test_find_untested_recommendations_filters_by_selector():
    tested = TrackingRecommendation(
        event_name="add_to_cart",
        trigger_type="click",
        selector="#buy",
        selector_fallbacks=["#buy"],
        event_category="ecommerce",
        business_objective="Purchase Intent",
        confidence=0.9,
        rationale="matched",
        page_url="https://example.com",
    )
    untested_rec = TrackingRecommendation(
        event_name="newsletter_signup",
        trigger_type="submit",
        selector="#footer-form",
        selector_fallbacks=["#footer-form"],
        event_category="conversion",
        business_objective="Lead Generation",
        confidence=0.6,
        rationale="matched",
        page_url="https://example.com",
    )
    journey = _journey([_event("click", selector="#buy")])

    result = find_untested_recommendations([tested, untested_rec], [journey])
    assert result == [untested_rec]
