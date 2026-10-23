from __future__ import annotations

import json
from datetime import datetime, timezone

from click.testing import CliRunner

from pytagmanager.cli import main
from pytagmanager.correlation.journey import TrackingJourney
from pytagmanager.observability.events import TrackingEvent
from pytagmanager.sdr import (
    SdrEvent,
    SdrFormatError,
    SdrParameter,
    SdrSchema,
    load_sdr,
    render_sdr_report,
    validate_sdr,
)


def _event(event_type, *, event_name="", payload=None, page_url="https://example.com/cart", selector=None):
    return TrackingEvent.create(
        source="datalayer" if event_type == "datalayer_push" else "browser",
        event_type=event_type,
        event_name=event_name,
        payload=payload,
        page_url=page_url,
        selector=selector,
        timestamp=1.0,
    )


def _journey(*, payload=None, duplicate=False, page_url="https://example.com/cart", selector="#buy"):
    payload = payload or {"value": 19.99, "currency": "USD", "items": [{"item_id": "sku1"}]}
    observations = [
        _event("click", page_url=page_url, selector=selector),
        _event("datalayer_push", event_name="add_to_cart", payload=payload, page_url=page_url),
        _event("network_request", page_url=page_url),
    ]
    if duplicate:
        observations.insert(2, _event("datalayer_push", event_name="add_to_cart", payload=payload, page_url=page_url))
    return TrackingJourney(
        journey_id="journey-1",
        business_event="add_to_cart",
        start_time=1.0,
        end_time=2.0,
        observations=observations,
    )


def _schema(**event_overrides):
    event = {
        "event_name": "add_to_cart",
        "parameters": (
            SdrParameter(name="value", types=("number",), required=True),
            SdrParameter(name="currency", types=("string",), required=True, allowed=("USD", "EUR")),
            SdrParameter(name="items", types=("array",), required=True),
            SdrParameter(name="coupon", types=("string",), required=False),
        ),
        "page_contains": "/cart",
        "selector": "#buy",
        "require_network": True,
    }
    event.update(event_overrides)
    return SdrSchema(name="Cart SDR", events=(SdrEvent(**event),))


def test_aligned_sdr_reports_full_score():
    validation = validate_sdr(_schema(), [_journey()])
    assert validation.alignment_score == 1.0
    assert validation.is_aligned is True
    assert validation.events[0].status == "aligned"
    assert validation.checks_failed == 0
    assert validation.events[0].network_observed is True
    assert "items" not in [issue.parameter for issue in validation.issues]


def test_missing_event_is_critical_and_scores_zero():
    validation = validate_sdr(_schema(), [])
    assert validation.alignment_score == 0.0
    assert validation.events[0].status == "missing"
    assert {issue.code for issue in validation.issues} >= {"missing_event", "no_runtime_evidence"}
    assert any("Verify the interaction handler" in item for item in validation.recommendations)


def test_missing_required_parameter_wrong_type_and_allowed_value_are_reported():
    validation = validate_sdr(
        _schema(),
        [_journey(payload={"value": "19.99", "currency": "GBP"})],
    )
    codes = {issue.code for issue in validation.issues}
    assert "missing_parameter" in codes
    assert "wrong_type" in codes
    assert "value_not_allowed" in codes
    assert validation.alignment_score < 1.0
    assert validation.events[0].status == "partial"


def test_page_and_selector_conditions_are_enforced():
    validation = validate_sdr(
        _schema(),
        [_journey(page_url="https://example.com/home", selector="#other")],
    )
    codes = {issue.code for issue in validation.issues}
    assert "page_condition_mismatch" in codes
    assert "selector_condition_mismatch" in codes
    assert validation.events[0].pages == ("https://example.com/home",)


def test_required_network_and_duplicate_firing_are_penalized():
    validation = validate_sdr(_schema(), [_journey(duplicate=True)])
    assert "duplicate_event" in {issue.code for issue in validation.issues}
    assert validation.checks_failed >= 1
    assert validation.events[0].status == "partial"


def test_network_requirement_is_explicit_when_no_request_was_observed():
    journey = _journey()
    journey = TrackingJourney(
        journey_id=journey.journey_id,
        business_event=journey.business_event,
        start_time=journey.start_time,
        end_time=journey.end_time,
        observations=[item for item in journey.observations if item.event_type != "network_request"],
    )
    validation = validate_sdr(_schema(), [journey])
    assert "network_missing" in {issue.code for issue in validation.issues}
    assert validation.events[0].network_observed is False


def test_parameter_values_are_never_serialized():
    validation = validate_sdr(
        _schema(parameters=(SdrParameter(name="customer_email", types=("string",), allowed=("allowed@example.com",)),)),
        [_journey(payload={"customer_email": "jane@example.com"})],
    )
    payload = json.dumps(validation.to_dict())
    assert "jane@example.com" not in payload
    assert "allowed@example.com" not in payload
    assert "value_not_allowed" in {issue.code for issue in validation.issues}


def test_text_report_contains_score_and_recommendations():
    validation = validate_sdr(_schema(), [])
    report = render_sdr_report(validation)
    assert "SDR Alignment" in report
    assert "Alignment score: 0.0%" in report
    assert "Prioritized recommendations" in report


def test_json_and_csv_loaders_support_aliases_and_merge_rows(tmp_path):
    json_path = tmp_path / "sdr.json"
    json_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "name": "Cart",
                "events": [
                    {
                        "event": "add_to_cart",
                        "page": "/cart",
                        "params": [
                            {"parameter": "value", "data_type": "float", "required": True},
                            {"name": "coupon", "type": "str", "required": False},
                        ],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    schema = load_sdr(json_path)
    assert schema.name == "Cart"
    assert schema.events[0].event_name == "add_to_cart"
    assert schema.events[0].parameters[0].types == ("number",)
    assert schema.events[0].parameters[1].required is False

    csv_path = tmp_path / "sdr.csv"
    csv_path.write_text(
        "event_name,parameter_name,type,required,allowed_values,page_contains,selector,require_network\n"
        "purchase,transaction_id,string,true,,/checkout,,true\n"
        "purchase,currency,string,true,USD|EUR,/checkout,\n",
        encoding="utf-8",
    )
    schema = load_sdr(csv_path)
    assert len(schema.events) == 1
    assert [parameter.name for parameter in schema.events[0].parameters] == ["transaction_id", "currency"]
    assert schema.events[0].parameters[1].allowed == ("USD", "EUR")
    assert schema.events[0].require_network is True


def test_loader_rejects_unsupported_types_and_empty_files(tmp_path):
    path = tmp_path / "bad.json"
    path.write_text(json.dumps({"events": [{"event_name": "x", "parameters": [{"name": "v", "type": "date"}]}]}))
    try:
        load_sdr(path)
    except SdrFormatError as exc:
        assert "unsupported SDR parameter type" in str(exc)
    else:
        raise AssertionError("expected SdrFormatError")

    empty = tmp_path / "empty.json"
    empty.write_text(json.dumps({"events": []}))
    try:
        load_sdr(empty)
    except SdrFormatError as exc:
        assert "no events" in str(exc)
    else:
        raise AssertionError("expected SdrFormatError")


def _write_cli_sdr(tmp_path):
    path = tmp_path / "cart.json"
    path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "name": "Cart SDR",
                "events": [
                    {
                        "event_name": "add_to_cart",
                        "page_contains": "/healthy_tracking.html",
                        "selector": "[data-testid='add-to-cart']",
                        "require_network": True,
                        "parameters": [
                            {"name": "value", "type": "number"},
                            {"name": "currency", "type": "string", "allowed": ["USD"]},
                            {"name": "items", "type": "array"},
                        ],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    return path


def test_diagnose_sdr_json_is_aligned_on_healthy_fixture(fixture_server, tmp_path):
    sdr_path = _write_cli_sdr(tmp_path)
    scenario_path = tmp_path / "cart.yml"
    scenario_path.write_text(
        "journey:\n"
        "  name: Add To Cart\n"
        "  steps:\n"
        "    - action: click\n"
        "      selector: \"[data-testid='add-to-cart']\"\n"
    )
    result = CliRunner().invoke(
        main,
        [
            "diagnose",
            f"{fixture_server}/healthy_tracking.html",
            "--scenario",
            str(scenario_path),
            "--sdr",
            str(sdr_path),
            "--format",
            "json",
        ],
    )
    assert result.exit_code == 0, result.output
    report = json.loads(result.output)
    alignment = report["sdr_alignment"]
    assert alignment["alignment_score"] == 1.0
    assert alignment["checks"]["failed"] == 0
    assert alignment["events"][0]["status"] == "aligned"


def test_diagnose_sdr_mismatch_can_fail_the_command(fixture_server, tmp_path):
    sdr_path = _write_cli_sdr(tmp_path)
    scenario_path = tmp_path / "cart.yml"
    scenario_path.write_text(
        "journey:\n"
        "  name: Add To Cart\n"
        "  steps:\n"
        "    - action: click\n"
        "      selector: \"[data-testid='add-to-cart']\"\n"
    )
    result = CliRunner().invoke(
        main,
        [
            "diagnose",
            f"{fixture_server}/missing_datalayer.html",
            "--scenario",
            str(scenario_path),
            "--sdr",
            str(sdr_path),
            "--format",
            "json",
            "--fail-on-sdr-mismatch",
        ],
    )
    assert result.exit_code == 1, result.output
    report = json.loads(result.output)
    assert report["sdr_alignment"]["alignment_score"] == 0.0
    assert report["sdr_alignment"]["events"][0]["status"] == "missing"


def test_fail_on_sdr_mismatch_requires_sdr(fixture_server):
    result = CliRunner().invoke(
        main,
        ["diagnose", f"{fixture_server}/healthy_tracking.html", "--fail-on-sdr-mismatch"],
    )
    assert result.exit_code == 2
    assert "--fail-on-sdr-mismatch requires --sdr" in result.output
