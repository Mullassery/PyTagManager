"""Schema-correctness unit tests for the non-GTM exporters
(python/pytagmanager/export/{ga4,segment,snowplow,tealium,rudderstack,adobe_tags}.py),
following the same pattern as test_gtm_export.py: build a config from
realistic `TrackingRecommendation`s and assert the output matches each
platform's real, documented schema shape.
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

from pytagmanager.export.adobe_tags import build_adobe_launch_rules, export_adobe_tags_json
from pytagmanager.export.base import EXPORTERS
from pytagmanager.export.ga4 import build_ga4_config, export_ga4_json
from pytagmanager.export.rudderstack import build_rudderstack_tracking_plan, export_rudderstack_json
from pytagmanager.export.segment import build_segment_tracking_plan, export_segment_json
from pytagmanager.export.snowplow import build_snowplow_schemas, export_snowplow_json
from pytagmanager.export.tealium import build_tealium_profile, export_tealium_json
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


# -- GA4 ------------------------------------------------------------------


def test_ga4_config_uses_recommended_event_names_and_params():
    config = build_ga4_config(_sample_recs())

    assert config["measurementProtocolVersion"] == "2"
    events = config["events"]
    assert len(events) == 2

    add_to_cart = events[0]
    assert add_to_cart["name"] == "add_to_cart"  # GA4 recommended event name
    assert "currency" in add_to_cart["params"]
    assert "value" in add_to_cart["params"]
    assert "items" in add_to_cart["params"]
    assert add_to_cart["_pytagmanager"]["selector"] == '[data-testid="add-to-cart"]'
    assert add_to_cart["_pytagmanager"]["businessObjective"] == "Purchase Intent"

    lead = events[1]
    assert lead["name"] == "generate_lead"


def test_ga4_config_empty_input():
    config = build_ga4_config([])
    assert config["events"] == []


def test_ga4_unknown_business_objective_falls_back_to_default_event():
    rec = TrackingRecommendation(
        event_name="custom",
        trigger_type="click",
        selector="#x",
        selector_fallbacks=["#x"],
        event_category="misc",
        business_objective="Totally Unmapped Objective",
        confidence=0.4,
        rationale="test",
        page_url="https://example.com",
    )
    config = build_ga4_config([rec])
    assert config["events"][0]["name"] == "select_content"


def test_export_ga4_json_writes_valid_json_file():
    with tempfile.TemporaryDirectory() as tmp:
        out_path = Path(tmp) / "ga4.json"
        export_ga4_json(_sample_recs(), str(out_path))
        data = json.loads(out_path.read_text())
        assert len(data["events"]) == 2


# -- Segment ----------------------------------------------------------------


def test_segment_tracking_plan_shape_and_ecommerce_spec_name():
    plan = build_segment_tracking_plan(_sample_recs())

    assert plan["display_name"] == "PyTagManager Tracking Plan"
    events = plan["rules"]["events"]
    assert len(events) == 2

    product_added = events[0]
    assert product_added["name"] == "Product Added"  # Segment Ecommerce v2 spec name
    props = product_added["rules"]["properties"]["properties"]
    assert props["type"] == "object"
    assert "product_id" in props["properties"]
    assert "product_id" in props["required"]
    assert product_added["rules"]["labels"]["pytagmanager_selector"] == '[data-testid="add-to-cart"]'

    lead = events[1]
    assert lead["name"] == "Lead Generated"


def test_export_segment_json_writes_valid_json_file():
    with tempfile.TemporaryDirectory() as tmp:
        out_path = Path(tmp) / "segment.json"
        export_segment_json(_sample_recs(), str(out_path))
        data = json.loads(out_path.read_text())
        assert len(data["rules"]["events"]) == 2


# -- Snowplow -----------------------------------------------------------------


def test_snowplow_schemas_are_valid_iglu_self_describing_documents():
    doc = build_snowplow_schemas(_sample_recs())

    schemas = doc["schemas"]
    assert "add_to_cart" in schemas
    assert "generate_lead" in schemas

    schema = schemas["add_to_cart"]
    assert schema["self"]["vendor"] == "com.pytagmanager"
    assert schema["self"]["name"] == "add_to_cart"
    assert schema["self"]["format"] == "jsonschema"
    assert schema["self"]["version"] == "1-0-0"
    assert schema["type"] == "object"
    assert "properties" in schema
    assert schema["additionalProperties"] is False

    events = doc["events"]
    assert len(events) == 2
    unstruct = events[0]
    assert unstruct["schema"] == "iglu:com.snowplowanalytics.snowplow/unstruct_event/jsonschema/1-0-0"
    assert unstruct["data"]["schema"] == "iglu:com.pytagmanager/add_to_cart/jsonschema/1-0-0"
    assert unstruct["data"]["data"]["selector"] == '[data-testid="add-to-cart"]'


def test_snowplow_schemas_deduplicated_per_canonical_event():
    recs = _sample_recs() + [_sample_recs()[0]]  # duplicate add_to_cart-shaped rec
    doc = build_snowplow_schemas(recs)
    assert len(doc["schemas"]) == 2  # add_to_cart + generate_lead, not 3
    assert len(doc["events"]) == 3  # one event instance per recommendation, though


def test_export_snowplow_json_writes_valid_json_file():
    with tempfile.TemporaryDirectory() as tmp:
        out_path = Path(tmp) / "snowplow.json"
        export_snowplow_json(_sample_recs(), str(out_path))
        data = json.loads(out_path.read_text())
        assert len(data["events"]) == 2


# -- Tealium ------------------------------------------------------------------


def test_tealium_profile_udo_events_and_load_rules():
    profile = build_tealium_profile(_sample_recs())

    udo_events = profile["udo_events"]
    assert len(udo_events) == 2
    assert udo_events[0]["call_type"] == "link"
    assert udo_events[0]["tealium_event"] == "add_to_cart"
    assert udo_events[0]["udo"]["dom_selector"] == '[data-testid="add-to-cart"]'

    load_rules = profile["load_rules"]
    assert len(load_rules) == 2
    condition = load_rules[0]["conditions"][0]
    assert condition == {"variable": "tealium_event", "operator": "equals", "value": "add_to_cart"}


def test_export_tealium_json_writes_valid_json_file():
    with tempfile.TemporaryDirectory() as tmp:
        out_path = Path(tmp) / "tealium.json"
        export_tealium_json(_sample_recs(), str(out_path))
        data = json.loads(out_path.read_text())
        assert len(data["udo_events"]) == 2


# -- RudderStack --------------------------------------------------------------


def test_rudderstack_tracking_plan_shape():
    plan = build_rudderstack_tracking_plan(_sample_recs())

    assert plan["name"] == "PyTagManager Tracking Plan"
    events = plan["rules"]["events"]
    assert len(events) == 2

    product_added = events[0]
    assert product_added["name"] == "Product Added"
    assert product_added["eventType"] == "track"
    assert product_added["creationType"] == "AUTO"
    props = product_added["rules"]["properties"]["properties"]
    assert "product_id" in props["properties"]
    assert product_added["metadata"]["selector"] == '[data-testid="add-to-cart"]'


def test_export_rudderstack_json_writes_valid_json_file():
    with tempfile.TemporaryDirectory() as tmp:
        out_path = Path(tmp) / "rudderstack.json"
        export_rudderstack_json(_sample_recs(), str(out_path))
        data = json.loads(out_path.read_text())
        assert len(data["rules"]["events"]) == 2


# -- Adobe Tags (Launch) --------------------------------------------------


def test_adobe_launch_rules_use_real_core_extension_module_paths():
    doc = build_adobe_launch_rules(_sample_recs())

    rules = doc["rules"]
    assert len(rules) == 2

    click_rule = rules[0]
    assert click_rule["events"][0]["modulePath"] == "core/src/lib/events/click.js"
    assert click_rule["events"][0]["settings"]["elementSelector"] == '[data-testid="add-to-cart"]'
    assert click_rule["actions"][0]["modulePath"] == "core/src/lib/actions/customCode.js"
    assert "_satellite.track" in click_rule["actions"][0]["settings"]["source"]
    assert click_rule["conditions"] == []

    submit_rule = rules[1]
    assert submit_rule["events"][0]["modulePath"] == "core/src/lib/events/formSubmit.js"


def test_export_adobe_tags_json_writes_valid_json_file():
    with tempfile.TemporaryDirectory() as tmp:
        out_path = Path(tmp) / "adobe_tags.json"
        export_adobe_tags_json(_sample_recs(), str(out_path))
        data = json.loads(out_path.read_text())
        assert len(data["rules"]) == 2


# -- Registry / extension seam ---------------------------------------------


def test_all_exporters_registered_and_handle_empty_input():
    assert set(EXPORTERS) == {"gtm", "ga4", "segment", "snowplow", "tealium", "rudderstack", "adobe_tags"}
    for name, spec in EXPORTERS.items():
        result = spec.build([])
        assert isinstance(result, dict), f"{name} builder must return a dict"
