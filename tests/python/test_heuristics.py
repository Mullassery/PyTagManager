from pathlib import Path

from pytagmanager._core import parse_html
from pytagmanager.recommend.heuristics import recommend_for_graph

FIXTURE = Path(__file__).parent / "fixtures" / "sample_page.html"


def _recommendations():
    html = FIXTURE.read_text()
    graph = parse_html(html, "https://example.com/product")
    return recommend_for_graph(graph)


def _by_event(recs, event_name):
    matches = [r for r in recs if r.event_name == event_name]
    assert matches, f"expected a recommendation for event '{event_name}', got {[r.event_name for r in recs]}"
    return matches[0]


def test_finds_expected_recommendation_count():
    recs = _recommendations()
    # add-to-cart, buy-now, contact link, download link, subscribe button, newsletter form
    assert len(recs) == 6


def test_add_to_cart_uses_stable_selector():
    recs = _recommendations()
    stable = [r for r in recs if r.event_name == "purchase_intent" and "data-testid" in r.selector]
    assert stable, "expected the add-to-cart button to use its data-testid as the primary selector"
    assert stable[0].selector == '[data-testid="add-to-cart"]'
    assert stable[0].selector_fallbacks[0] == stable[0].selector


def test_contact_link_classified_as_lead_generation():
    rec = _by_event(_recommendations(), "lead_generation")
    assert rec.business_objective == "Lead Generation"
    assert 0.0 < rec.confidence <= 1.0
    assert "contact us" in rec.rationale.lower()


def test_download_link_classified_as_content_engagement():
    rec = _by_event(_recommendations(), "content_engagement")
    assert rec.business_objective == "Content Engagement"
    assert rec.trigger_type == "click"


def test_subscribe_button_classified_as_subscription():
    rec = _by_event(_recommendations(), "subscription")
    assert rec.business_objective == "Subscription"


def test_form_element_produces_form_submission_recommendation():
    recs = _recommendations()
    form_recs = [r for r in recs if r.event_name == "form_submission"]
    assert len(form_recs) == 1
    assert form_recs[0].trigger_type == "submit"
    assert form_recs[0].selector == "#newsletter-form"


def test_unrelated_elements_produce_no_recommendation():
    recs = _recommendations()
    assert not any("home" in r.rationale.lower() for r in recs)
