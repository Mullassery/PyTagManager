import json
import tempfile
from pathlib import Path

from pytagmanager.export.gtm import build_gtm_container, export_gtm_json
from pytagmanager.recommend.models import TrackingRecommendation


def _sample_recs():
    return [
        TrackingRecommendation(
            event_name="purchase_intent",
            trigger_type="click",
            selector='[data-testid="add-to-cart"]',
            selector_fallbacks=['[data-testid="add-to-cart"]', "button:nth-child(1)", "/html/body/button[1]"],
            event_category="ecommerce",
            business_objective="Purchase Intent",
            confidence=0.95,
            rationale="Matched CTA keyword 'add to cart' on <button>; signals: text contains 'add to cart'",
            page_url="https://example.com/product",
        ),
        TrackingRecommendation(
            event_name="form_submission",
            trigger_type="submit",
            selector="#newsletter-form",
            selector_fallbacks=["#newsletter-form", "/html/body/form[1]"],
            event_category="form",
            business_objective="Lead Generation",
            confidence=0.6,
            rationale="Element is a <form>; form submissions are a default trackable business event.",
            page_url="https://example.com/product",
        ),
    ]


def test_build_gtm_container_shape():
    container = build_gtm_container(_sample_recs())

    assert container["exportFormatVersion"] == 2
    version = container["containerVersion"]
    assert len(version["tag"]) == 2
    assert len(version["trigger"]) == 2

    tag = version["tag"][0]
    assert tag["name"] == "purchase_intent"
    assert tag["type"] == "gaawe"
    assert tag["parameter"]["eventName"] == "purchase_intent"
    assert tag["metadata"]["businessObjective"] == "Purchase Intent"
    assert tag["firingTriggerId"] == [version["trigger"][0]["triggerId"]]

    trigger = version["trigger"][0]
    assert trigger["type"] == "CLICK"
    assert trigger["filter"]["selector"] == '[data-testid="add-to-cart"]'

    submit_trigger = version["trigger"][1]
    assert submit_trigger["type"] == "FORM_SUBMISSION"


def test_build_gtm_container_empty_input():
    container = build_gtm_container([])
    assert container["containerVersion"]["tag"] == []
    assert container["containerVersion"]["trigger"] == []


def test_export_gtm_json_writes_valid_json_file():
    with tempfile.TemporaryDirectory() as tmp:
        out_path = Path(tmp) / "out.json"
        export_gtm_json(_sample_recs(), str(out_path))

        assert out_path.exists()
        data = json.loads(out_path.read_text())
        assert len(data["containerVersion"]["tag"]) == 2
