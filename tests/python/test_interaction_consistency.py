"""Tests for Phase 1.8's cross-implementation business-action consistency
check (`sitewide/interaction_consistency.py`): unit tests against
hand-built `TrackingRecommendation`/`TrackingJourney` objects, plus a real
end-to-end `diagnose --site-wide` run proving it against two real fixture
pages that implement "Add to Cart" with two different event names.
"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from click.testing import CliRunner

from pytagmanager import _core
from pytagmanager.cli import main
from pytagmanager.correlation.journey import TrackingJourney
from pytagmanager.observability.events import TrackingEvent
from pytagmanager.recommend.models import TrackingRecommendation
from pytagmanager.sitewide.interaction_consistency import analyze_business_action_consistency

_FIXTURES_DIR = Path(__file__).parent / "fixtures" / "observability"


def _rec(page_url: str, selector: str, business_objective: str = "Purchase Intent") -> TrackingRecommendation:
    return TrackingRecommendation(
        event_name="purchase_intent",
        trigger_type="click",
        selector=selector,
        selector_fallbacks=[selector],
        event_category="ecommerce",
        business_objective=business_objective,
        confidence=0.8,
        rationale="text contains 'add to cart'",
        page_url=page_url,
    )


def _fired_journey(page_url: str, selector: str, event_name: str) -> TrackingJourney:
    click = TrackingEvent.create(source="browser", event_type="click", page_url=page_url, selector=selector, timestamp=0.0)
    push = TrackingEvent.create(
        source="datalayer", event_type="datalayer_push", event_name=event_name, page_url=page_url, timestamp=0.1
    )
    return TrackingJourney(
        journey_id="j1", business_event=event_name, start_time=0.0, end_time=0.1, observations=[click, push]
    )


def _silent_journey(page_url: str, selector: str) -> TrackingJourney:
    click = TrackingEvent.create(source="browser", event_type="click", page_url=page_url, selector=selector, timestamp=0.0)
    return TrackingJourney(
        journey_id="j2", business_event="click:x", start_time=0.0, end_time=0.0, observations=[click]
    )


def test_same_event_name_across_pages_is_consistent():
    recs_by_page = {
        "https://example.com/a": [_rec("https://example.com/a", "#cta")],
        "https://example.com/b": [_rec("https://example.com/b", "#cta")],
    }
    journeys = [
        _fired_journey("https://example.com/a", "#cta", "add_to_cart"),
        _fired_journey("https://example.com/b", "#cta", "add_to_cart"),
    ]

    reports = analyze_business_action_consistency(recs_by_page, journeys)

    assert len(reports) == 1
    assert reports[0].is_consistent
    assert reports[0].distinct_event_names == ["add_to_cart"]


def test_different_event_names_across_pages_is_inconsistent():
    recs_by_page = {
        "https://example.com/a": [_rec("https://example.com/a", "#cta")],
        "https://example.com/b": [_rec("https://example.com/b", "#cta")],
    }
    journeys = [
        _fired_journey("https://example.com/a", "#cta", "add_to_cart"),
        _fired_journey("https://example.com/b", "#cta", "addToCart"),
    ]

    reports = analyze_business_action_consistency(recs_by_page, journeys)

    assert len(reports) == 1
    assert not reports[0].is_consistent
    assert reports[0].distinct_event_names == ["addToCart", "add_to_cart"]


def test_silent_implementation_does_not_count_against_naming_consistency():
    # A page where the action never fired at all is a different, already
    # existing kind of finding (find_untested_recommendations) -- this
    # report's job is naming/shape drift among what DID fire.
    recs_by_page = {
        "https://example.com/a": [_rec("https://example.com/a", "#cta")],
        "https://example.com/b": [_rec("https://example.com/b", "#cta")],
    }
    journeys = [
        _fired_journey("https://example.com/a", "#cta", "add_to_cart"),
        _silent_journey("https://example.com/b", "#cta"),
    ]

    reports = analyze_business_action_consistency(recs_by_page, journeys)

    assert reports[0].is_consistent
    assert reports[0].fired_count == 1
    assert reports[0].untested_or_silent_count == 1


def test_single_implementation_is_not_reported_at_all():
    recs_by_page = {"https://example.com/a": [_rec("https://example.com/a", "#cta")]}
    journeys = [_fired_journey("https://example.com/a", "#cta", "add_to_cart")]

    reports = analyze_business_action_consistency(recs_by_page, journeys)

    assert reports == []


def test_different_business_objectives_are_not_compared_to_each_other():
    recs_by_page = {
        "https://example.com/a": [_rec("https://example.com/a", "#cta", "Purchase Intent")],
        "https://example.com/b": [_rec("https://example.com/b", "#login", "Authentication")],
    }
    journeys = [
        _fired_journey("https://example.com/a", "#cta", "add_to_cart"),
        _fired_journey("https://example.com/b", "#login", "login"),
    ]

    reports = analyze_business_action_consistency(recs_by_page, journeys)

    # Each business_objective only has one implementation -- nothing to compare.
    assert reports == []


# ---- End-to-end: real crawl-discovery-substitution + real Chromium ----


def _fake_page(fixture_server: str, filename: str):
    url = f"{fixture_server}/{filename}"
    html = (_FIXTURES_DIR / filename).read_text()
    graph = _core.parse_html(html, url)
    return SimpleNamespace(url=url, status=200, graph=graph)


def test_diagnose_site_wide_detects_add_to_cart_naming_inconsistency(fixture_server, monkeypatch):
    pages = [
        _fake_page(fixture_server, "healthy_tracking.html"),  # fires "add_to_cart"
        _fake_page(fixture_server, "add_to_cart_variant_naming.html"),  # fires "addToCart"
    ]
    monkeypatch.setattr("pytagmanager.cli.crawl_site", lambda *a, **k: pages)

    result = CliRunner(mix_stderr=False).invoke(main, ["diagnose", pages[0].url, "--site-wide", "--format", "json"])

    assert result.exit_code == 0, result.output
    data = json.loads(result.output)
    reports = data["business_action_consistency"]
    assert len(reports) == 1
    report = reports[0]
    assert report["is_consistent"] is False
    assert set(report["distinct_event_names"]) == {"add_to_cart", "addToCart"}


def test_diagnose_site_wide_text_shows_inconsistency_section(fixture_server, monkeypatch):
    pages = [
        _fake_page(fixture_server, "healthy_tracking.html"),
        _fake_page(fixture_server, "add_to_cart_variant_naming.html"),
    ]
    monkeypatch.setattr("pytagmanager.cli.crawl_site", lambda *a, **k: pages)

    result = CliRunner().invoke(main, ["diagnose", pages[0].url, "--site-wide", "--format", "text"])

    assert result.exit_code == 0, result.output
    assert "Cross-Implementation Consistency" in result.output
    assert "Purchase Intent" in result.output
