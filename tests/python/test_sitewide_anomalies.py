import uuid

from pytagmanager.correlation.journey import TrackingJourney
from pytagmanager.observability.events import TrackingEvent
from pytagmanager.sitewide.anomalies import detect_template_anomalies
from pytagmanager.sitewide.templates import PageTemplate


def _journey(business_event, page_url, network_params=None):
    observations = [TrackingEvent.create(source="browser", event_type="click", page_url=page_url)]
    if network_params is not None:
        observations.append(
            TrackingEvent.create(
                source="network",
                event_type="network_request",
                page_url=page_url,
                payload={"url": "https://www.googletagmanager.com/gtm.js" if "id" in network_params else "https://www.google-analytics.com/g/collect", "params": network_params},
            )
        )
    return TrackingJourney(
        journey_id=str(uuid.uuid4()),
        business_event=business_event,
        start_time=0.0,
        end_time=1.0,
        observations=observations,
    )


def test_detects_unusual_event_repetition():
    pages = [f"https://example.com/products/{i}" for i in range(5)]
    template = PageTemplate(template_id="t1", label="Products", page_urls=pages)

    journeys_by_page = {url: [_journey("page_view", url)] for url in pages}
    # One page fires page_view 6 times -- way beyond the template's average of 1.
    journeys_by_page[pages[0]] = [_journey("page_view", pages[0]) for _ in range(6)]

    anomalies = detect_template_anomalies(template, journeys_by_page)
    repetition = [a for a in anomalies if a.kind == "unusual_event_repetition"]
    assert len(repetition) == 1
    assert repetition[0].page_url == pages[0]
    assert repetition[0].details["count"] == 6


def test_no_repetition_anomaly_with_uniform_counts():
    pages = [f"https://example.com/products/{i}" for i in range(5)]
    template = PageTemplate(template_id="t1", label="Products", page_urls=pages)
    journeys_by_page = {url: [_journey("page_view", url)] for url in pages}

    anomalies = detect_template_anomalies(template, journeys_by_page)
    assert not [a for a in anomalies if a.kind == "unusual_event_repetition"]


def test_detects_ga4_measurement_id_drift():
    pages = ["https://example.com/a", "https://example.com/b", "https://example.com/c"]
    template = PageTemplate(template_id="t1", label="Cart", page_urls=pages)
    journeys_by_page = {
        "https://example.com/a": [_journey("purchase", pages[0], network_params={"tid": "G-AAAA"})],
        "https://example.com/b": [_journey("purchase", pages[1], network_params={"tid": "G-AAAA"})],
        "https://example.com/c": [_journey("purchase", pages[2], network_params={"tid": "G-BBBB"})],
    }

    anomalies = detect_template_anomalies(template, journeys_by_page)
    drift = [a for a in anomalies if a.kind == "config_drift" and a.details["label"] == "GA4 measurement ID"]
    assert len(drift) == 1
    assert drift[0].page_url == "https://example.com/c"
    assert drift[0].details["expected"] == "G-AAAA"


def test_detects_gtm_container_drift():
    pages = ["https://example.com/a", "https://example.com/b", "https://example.com/c"]
    template = PageTemplate(template_id="t1", label="Cart", page_urls=pages)
    journeys_by_page = {
        "https://example.com/a": [_journey("purchase", pages[0], network_params={"id": "GTM-AAAA"})],
        "https://example.com/b": [_journey("purchase", pages[1], network_params={"id": "GTM-AAAA"})],
        "https://example.com/c": [_journey("purchase", pages[2], network_params={"id": "GTM-ZZZZ"})],
    }

    anomalies = detect_template_anomalies(template, journeys_by_page)
    drift = [a for a in anomalies if a.kind == "config_drift" and a.details["label"] == "GTM container"]
    assert len(drift) == 1
    assert drift[0].page_url == "https://example.com/c"


def test_no_config_drift_when_all_pages_agree():
    pages = ["https://example.com/a", "https://example.com/b"]
    template = PageTemplate(template_id="t1", label="Cart", page_urls=pages)
    journeys_by_page = {
        "https://example.com/a": [_journey("purchase", pages[0], network_params={"tid": "G-AAAA"})],
        "https://example.com/b": [_journey("purchase", pages[1], network_params={"tid": "G-AAAA"})],
    }

    assert detect_template_anomalies(template, journeys_by_page) == []
