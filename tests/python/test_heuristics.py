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


# ---- Phase 1.8: broadened interactive-element taxonomy ----


def _recs_for_html(html: str):
    graph = parse_html(html, "https://example.com/product")
    return recommend_for_graph(graph)


def test_aria_role_tab_is_detected_even_without_button_or_link_tag():
    # Modern component libraries very often implement tabs/menus as a
    # <div role="..."> rather than a native <button>/<a> -- Phase 1.8
    # broadens detection to ARIA role, not just tag name.
    recs = _recs_for_html('<div role="tab">Open menu</div>')
    assert len(recs) == 1
    assert recs[0].business_objective == "Navigation"


def test_aria_role_menuitem_is_detected():
    recs = _recs_for_html('<li role="menuitem">Filter by price</li>')
    assert len(recs) == 1
    assert recs[0].business_objective == "Content Discovery"


def test_new_keyword_categories_are_classified():
    cases = {
        "Remove from Cart": "Cart Modification",
        "Add to Wishlist": "Wishlist Intent",
        "Filter by Price": "Content Discovery",
        "Sort by Price": "Content Discovery",
        "Next Page": "Pagination",
        "Load More": "Pagination",
        "Play Video": "Video Engagement",
        "Open Menu": "Navigation",
        "Close Modal": "Modal Interaction",
        "Expand": "Content Engagement",
    }
    for text, expected_objective in cases.items():
        recs = _recs_for_html(f"<button>{text}</button>")
        assert len(recs) == 1, f"expected exactly one recommendation for {text!r}, got {recs}"
        assert recs[0].business_objective == expected_objective, f"{text!r} -> {recs[0].business_objective}"


def test_plain_div_without_interactive_role_is_not_classified():
    # Broadening to ARIA roles must not turn every <div> into a candidate --
    # this would explode recommendation volume and defeat the point of a
    # curated interactive-element signal.
    recs = _recs_for_html('<div class="menu-wrapper">Filter options here</div>')
    assert recs == []
