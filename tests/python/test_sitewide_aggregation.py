import uuid

from pytagmanager.correlation.journey import TrackingJourney
from pytagmanager.observability.events import TrackingEvent
from pytagmanager.sitewide.aggregation import analyze_template_consistency, compute_site_health, compute_template_health
from pytagmanager.sitewide.report import build_site_health_json, render_site_health_report
from pytagmanager.sitewide.templates import PageTemplate


def _journey(business_event, status, page_url, event_types=()):
    observations = [
        TrackingEvent.create(source="browser", event_type=t, event_name="", page_url=page_url) for t in event_types
    ]
    return TrackingJourney(
        journey_id=str(uuid.uuid4()),
        business_event=business_event,
        start_time=0.0,
        end_time=1.0,
        observations=observations,
        status=status,
    )


def test_analyze_template_consistency_flags_minority_regression():
    # 342 product pages: 338 healthy add_to_cart, 4 failing -- the exact
    # numbers from the spec's own worked example.
    pages = [f"https://example.com/products/{i}" for i in range(342)]
    template = PageTemplate(template_id="t1", label="Products", page_urls=pages)

    journeys_by_page = {}
    for i, url in enumerate(pages):
        status = "healthy" if i < 338 else "critical"
        journeys_by_page[url] = [_journey("add_to_cart", status, url)]

    report = analyze_template_consistency(template, journeys_by_page)

    stat = next(s for s in report.event_stats if s.event_name == "add_to_cart")
    assert stat.pass_count == 338
    assert stat.fail_count == 4
    assert any("4 of 342" in r and "add_to_cart" in r for r in report.regressions)


def test_analyze_template_consistency_ignores_one_off_events():
    pages = [f"https://example.com/products/{i}" for i in range(10)]
    template = PageTemplate(template_id="t1", label="Products", page_urls=pages)

    journeys_by_page = {url: [_journey("add_to_cart", "healthy", url)] for url in pages}
    # One page has an unrelated one-off event that shouldn't be treated as
    # a template-wide expectation just because it shares a template.
    journeys_by_page[pages[0]].append(_journey("newsletter_signup", "healthy", pages[0]))

    report = analyze_template_consistency(template, journeys_by_page)
    event_names = {s.event_name for s in report.event_stats}
    assert "add_to_cart" in event_names
    assert "newsletter_signup" not in event_names


def test_compute_template_health_score_weighting():
    pages = ["https://example.com/a", "https://example.com/b"]
    template = PageTemplate(template_id="t1", label="Cart", page_urls=pages)
    journeys_by_page = {
        "https://example.com/a": [_journey("add_to_cart", "healthy", "https://example.com/a")],
        "https://example.com/b": [_journey("add_to_cart", "warning", "https://example.com/b")],
    }

    health = compute_template_health(template, journeys_by_page)
    assert health.journeys_total == 2
    assert health.score == 75  # (1 healthy + 0.5 warning) / 2 = 0.75


def test_compute_site_health_reports_none_for_unmeasured_metrics():
    template = PageTemplate(template_id="t1", label="Cart", page_urls=["https://example.com/cart"])
    journeys_by_page = {"https://example.com/cart": [_journey("add_to_cart", "healthy", "https://example.com/cart")]}

    site_health = compute_site_health([template], journeys_by_page)
    # No consent_change events were ever observed anywhere in this crawl --
    # must report None (unmeasured), not a fabricated 100%.
    assert site_health.consent_ok_rate is None
    assert site_health.pages_scanned == 1


def test_render_and_json_report_smoke():
    template = PageTemplate(template_id="t1", label="Cart", page_urls=["https://example.com/cart"])
    journeys_by_page = {"https://example.com/cart": [_journey("add_to_cart", "healthy", "https://example.com/cart")]}
    site_health = compute_site_health([template], journeys_by_page)
    consistency = [analyze_template_consistency(template, journeys_by_page)]

    text = render_site_health_report(site_health, consistency)
    assert "PyTagManager Site Health" in text
    assert "Cart Template" in text

    payload = build_site_health_json(site_health, consistency)
    assert payload["schema_version"] == 1
    assert payload["templates"][0]["label"] == "Cart"
