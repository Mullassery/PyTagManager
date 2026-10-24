from __future__ import annotations

import importlib.util
import json

import pytest
from click.testing import CliRunner
from pytagmanager import cli
from pytagmanager.control import (
    ConfigPayload,
    Destination,
    Tag,
    Trigger,
    project_to_pytagshield,
    validate_with_pytagshield,
)
from pytagmanager.control.service import ControlPlaneService
from pytagmanager.control.store import FileStore


def _payload(*, purposes=("analytics",), kind="ga4", trigger_condition=None, tag_count=1):
    destination = Destination.create(
        name="GA4",
        kind=kind,
        config={"measurement_id": "G-123"},
        secret_refs={"api_secret": "env:GA4_SECRET"},
    )
    trigger = Trigger.create(
        name="Cart event",
        type="custom_event",
        conditions=trigger_condition
        or {"op": "equals", "path": "event.name", "value": "add_to_cart"},
    )
    tags = []
    for index in range(tag_count):
        tags.append(
            Tag.create(
                name=f"Add to cart {index}",
                type="ga4_event",
                parameters={"event_name": "add_to_cart"},
                trigger_ids=(trigger.trigger_id,),
                destination_ids=(destination.destination_id,),
                consent_purpose=purposes[index % len(purposes)],
            )
        )
    return ConfigPayload(
        tags=tuple(tags),
        triggers=(trigger,),
        destinations=(destination,),
    )


def test_projection_maps_ga4_route_and_consent_alias():
    payload = _payload()
    result = project_to_pytagshield(
        payload,
        pseudonymize_salt="x" * 24,
        secret_resolver=lambda ref: "resolved-secret",
    )
    assert result.exportable
    assert result.errors == ()
    config = result.config
    assert config["minimization"]["pseudonymize_ids"] is True
    assert config["minimization"]["pseudonymize_salt"] == "x" * 24
    assert config["consent"] == {
        "purposes": ["analytics"],
        "default_policy": "deny",
    }
    destination = config["destinations"][0]
    assert destination["name"] == "GA4 (analytics)"
    assert destination["purpose"] == "analytics"
    assert destination["type"] == "ga4"
    assert destination["ga4"] == {
        "measurement_id": "G-123",
        "api_secret": "resolved-secret",
    }
    route = config["routes"][0]
    assert route["destinations"] == ["GA4 (analytics)"]
    assert route["match"] == {"events": ["add_to_cart"]}
    assert route["enabled"] is True
    assert {issue.code for issue in result.warnings} == {"parameters_not_projected"}


def test_same_destination_gets_purpose_specific_aliases():
    payload = _payload(purposes=("analytics", "advertising"), tag_count=2)
    result = project_to_pytagshield(
        payload,
        pseudonymize_salt="x" * 24,
        secret_resolver=lambda ref: "resolved-secret",
    )
    assert result.exportable
    assert result.config["consent"]["purposes"] == ["advertising", "analytics"]
    assert [item["name"] for item in result.config["destinations"]] == [
        "GA4 (analytics)",
        "GA4 (advertising)",
    ]
    assert result.config["routes"][0]["destinations"] == ["GA4 (analytics)"]
    assert result.config["routes"][1]["destinations"] == ["GA4 (advertising)"]


def test_duplicate_destination_names_are_disambiguated():
    first = Destination.create(
        name="GA4",
        kind="ga4",
        config={"measurement_id": "G-1"},
        secret_refs={"api_secret": "env:S"},
    )
    second = Destination.create(
        name="GA4",
        kind="ga4",
        config={"measurement_id": "G-2"},
        secret_refs={"api_secret": "env:S"},
    )
    trigger = Trigger.create(
        name="event",
        type="custom_event",
        conditions={"op": "equals", "path": "event.name", "value": "purchase"},
    )
    tag = Tag.create(
        name="Purchase",
        type="ga4_event",
        trigger_ids=(trigger.trigger_id,),
        destination_ids=(first.destination_id, second.destination_id),
        consent_purpose="analytics",
    )
    result = project_to_pytagshield(
        ConfigPayload(destinations=(first, second), triggers=(trigger,), tags=(tag,)),
        pseudonymize_salt="x" * 24,
        secret_resolver=lambda ref: "s",
    )
    assert result.exportable
    names = [item["name"] for item in result.config["destinations"]]
    assert len(set(names)) == 2
    assert result.config["routes"][0]["destinations"] == names


def test_page_view_trigger_projects_without_name_condition():
    destination = Destination.create(name="log", kind="log")
    trigger = Trigger.create(name="Page view", type="page_view")
    tag = Tag.create(
        name="Page view",
        type="ga4_event",
        trigger_ids=(trigger.trigger_id,),
        destination_ids=(destination.destination_id,),
        consent_purpose="analytics",
    )
    result = project_to_pytagshield(
        ConfigPayload(tags=(tag,), triggers=(trigger,), destinations=(destination,)),
        pseudonymize_salt="x" * 24,
    )
    assert result.exportable
    assert result.config["routes"][0]["match"] == {"events": ["page_view"]}
    assert result.config["destinations"][0]["type"] == "log"


@pytest.mark.parametrize(
    "condition",
    [
        {"op": "equals", "path": "data_layer.plan", "value": "pro"},
        {
            "op": "not",
            "conditions": [{"op": "equals", "path": "event.name", "value": "x"}],
        },
        {"op": "exists", "path": "event.name"},
    ],
)
def test_unsupported_trigger_fails_closed(condition):
    payload = _payload(trigger_condition=condition)
    result = project_to_pytagshield(
        payload,
        pseudonymize_salt="x" * 24,
        secret_resolver=lambda ref: "s",
    )
    assert not result.exportable
    assert any(issue.code == "trigger_not_projectable" for issue in result.errors)
    assert result.config["routes"] == []


def test_missing_secret_resolver_is_an_error():
    result = project_to_pytagshield(_payload(), pseudonymize_salt="x" * 24)
    assert not result.exportable
    assert any(issue.code == "secret_resolver_required" for issue in result.errors)


def test_unsupported_destination_kind_is_an_error():
    payload = _payload(kind="segment")
    result = project_to_pytagshield(
        payload,
        pseudonymize_salt="x" * 24,
        secret_resolver=lambda ref: "s",
    )
    assert not result.exportable
    assert any(issue.code == "destination_kind_unsupported" for issue in result.errors)


def test_webhook_requires_post():
    destination = Destination.create(
        name="hook",
        kind="http_webhook",
        config={"url": "https://example.com", "method": "PUT"},
    )
    trigger = Trigger.create(
        name="event",
        type="custom_event",
        conditions={"op": "equals", "path": "event.name", "value": "purchase"},
    )
    tag = Tag.create(
        name="Purchase",
        type="http_webhook",
        trigger_ids=(trigger.trigger_id,),
        destination_ids=(destination.destination_id,),
        consent_purpose="analytics",
    )
    result = project_to_pytagshield(
        ConfigPayload(tags=(tag,), triggers=(trigger,), destinations=(destination,)),
        pseudonymize_salt="x" * 24,
    )
    assert not result.exportable
    assert any(issue.code == "webhook_method_unsupported" for issue in result.errors)


def test_generated_config_is_accepted_by_pytagshield_when_available():
    result = project_to_pytagshield(
        _payload(), pseudonymize_salt="x" * 24, secret_resolver=lambda ref: "s"
    )
    valid, messages = validate_with_pytagshield(result.config)
    if valid is None:
        pytest.skip("pytagshield is not installed in this environment")
    assert valid, messages


def test_projected_config_routes_through_pytagshield_when_available():
    if importlib.util.find_spec("pytagshield") is None:
        pytest.skip("pytagshield is not installed in this environment")
    import pytagshield

    result = project_to_pytagshield(
        _payload(), pseudonymize_salt="x" * 24, secret_resolver=lambda ref: "s"
    )
    pipeline = pytagshield.Pipeline(pytagshield.Config.from_yaml(json.dumps(result.config)))
    allowed = pipeline.process(
        {
            "event": "add_to_cart",
            "distinct_id": "customer-1",
            "properties": {},
            "consent": {"analytics": True},
        }
    )
    denied = pipeline.process(
        {
            "event": "add_to_cart",
            "distinct_id": "customer-1",
            "properties": {},
            "consent": {"analytics": False},
        }
    )
    assert allowed["routing"]["destinations"] == ["GA4 (analytics)"]
    assert allowed["event"]["distinct_id"].startswith("sha256:")
    assert denied["routing"]["destinations"] == []
    assert denied["routing"]["skipped"][0]["reason"] == "consent_denied:analytics"


def test_cli_exports_private_file_with_resolved_secret(tmp_path):
    service = ControlPlaneService(FileStore(tmp_path))
    service.create_container("GTM-ABC1234")
    service.create_revision("GTM-ABC1234", _payload())
    output = tmp_path / "pytagshield.yaml"
    runner = CliRunner()
    result = runner.invoke(
        cli.main,
        [
            "config",
            "pytagshield-export",
            "GTM-ABC1234",
            "--pseudonymize-salt",
            "x" * 24,
            "--home",
            str(tmp_path),
            "--output",
            str(output),
            "--no-validate",
        ],
        env={"GA4_SECRET": "top-secret"},
    )
    assert result.exit_code == 0, result.output
    assert output.exists()
    assert oct(output.stat().st_mode & 0o777) == "0o600"
    document = json.loads(output.read_text(encoding="utf-8"))
    assert document["destinations"][0]["ga4"]["api_secret"] == "top-secret"
    assert "contains resolved credentials" in result.output


def test_cli_fails_closed_when_secret_is_missing(tmp_path):
    service = ControlPlaneService(FileStore(tmp_path))
    service.create_container("GTM-ABC1234")
    service.create_revision("GTM-ABC1234", _payload())
    output = tmp_path / "pytagshield.yaml"
    runner = CliRunner()
    result = runner.invoke(
        cli.main,
        [
            "config",
            "pytagshield-export",
            "GTM-ABC1234",
            "--pseudonymize-salt",
            "x" * 24,
            "--home",
            str(tmp_path),
            "--output",
            str(output),
        ],
        env={"GA4_SECRET": ""},
    )
    assert result.exit_code != 0
    assert "secret" in result.output.lower()
    assert not output.exists()


@pytest.mark.parametrize(
    ("kind", "config", "secret_refs", "expected_type", "expected_block"),
    [
        (
            "posthog",
            {"host": "https://us.i.posthog.com"},
            {"api_key": "env:PH_KEY"},
            "posthog",
            {"api_key": "ph-secret", "host": "https://us.i.posthog.com"},
        ),
        (
            "meta",
            {"pixel_id": "123", "api_version": "v21.0"},
            {"access_token": "env:META_TOKEN"},
            "meta",
            {"pixel_id": "123", "api_version": "v21.0", "access_token": "meta-secret"},
        ),
        (
            "sgtm",
            {"url": "https://sgtm.example.com/g/collect", "query": {"a": "b"}},
            {},
            "sgtm",
            {"url": "https://sgtm.example.com/g/collect", "query": {"a": "b"}},
        ),
        (
            "http_webhook",
            {"url": "https://example.com/hook", "headers": {"X-Env": "prod"}},
            {},
            "webhook",
            {"url": "https://example.com/hook", "headers": {"X-Env": "prod"}},
        ),
    ],
)
def test_destination_settings_projection(kind, config, secret_refs, expected_type, expected_block):
    destination = Destination.create(name="dest", kind=kind, config=config, secret_refs=secret_refs)
    trigger = Trigger.create(
        name="event",
        type="custom_event",
        conditions={"op": "equals", "path": "event.name", "value": "purchase"},
    )
    tag = Tag.create(
        name="Purchase",
        type=kind,
        trigger_ids=(trigger.trigger_id,),
        destination_ids=(destination.destination_id,),
        consent_purpose="analytics",
    )
    result = project_to_pytagshield(
        ConfigPayload(tags=(tag,), triggers=(trigger,), destinations=(destination,)),
        pseudonymize_salt="x" * 24,
        secret_resolver=lambda ref: {
            "env:PH_KEY": "ph-secret",
            "env:META_TOKEN": "meta-secret",
        }[ref],
    )
    assert result.exportable, result.errors
    projected = result.config["destinations"][0]
    assert projected["type"] == expected_type
    assert projected[expected_type] == expected_block


def test_literal_credentials_warn_but_are_not_dropped():
    destination = Destination.create(
        name="GA4",
        kind="ga4",
        config={"measurement_id": "G-123", "api_secret": "literal-secret"},
    )
    trigger = Trigger.create(
        name="event",
        type="custom_event",
        conditions={"op": "equals", "path": "event.name", "value": "purchase"},
    )
    tag = Tag.create(
        name="Purchase",
        type="ga4_event",
        trigger_ids=(trigger.trigger_id,),
        destination_ids=(destination.destination_id,),
        consent_purpose="analytics",
    )
    result = project_to_pytagshield(
        ConfigPayload(tags=(tag,), triggers=(trigger,), destinations=(destination,)),
        pseudonymize_salt="x" * 24,
    )
    assert result.exportable
    assert result.config["destinations"][0]["ga4"]["api_secret"] == "literal-secret"
    assert any(issue.code == "literal_credential" for issue in result.warnings)


def test_cli_uses_native_validation_when_available(tmp_path):
    if importlib.util.find_spec("pytagshield") is None:
        pytest.skip("pytagshield is not installed in this environment")
    service = ControlPlaneService(FileStore(tmp_path))
    service.create_container("GTM-ABC1234")
    service.create_revision("GTM-ABC1234", _payload())
    runner = CliRunner()
    result = runner.invoke(
        cli.main,
        [
            "config",
            "pytagshield-export",
            "GTM-ABC1234",
            "--pseudonymize-salt",
            "x" * 24,
            "--home",
            str(tmp_path),
        ],
        env={"GA4_SECRET": "top-secret"},
    )
    assert result.exit_code == 0, result.output
    assert "PyTagShield validated" in result.output
