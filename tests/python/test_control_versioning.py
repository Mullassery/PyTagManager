from __future__ import annotations

import json
from dataclasses import replace

import pytest
from click.testing import CliRunner

from pytagmanager import cli
from pytagmanager.control import ConfigPayload, Destination, Tag, Trigger
from pytagmanager.control.diff import diff_payloads
from pytagmanager.control.errors import ConflictError, ValidationError
from pytagmanager.control.models import Environment
from pytagmanager.control.service import ControlPlaneService
from pytagmanager.control.store import FileStore


@pytest.fixture
def service(tmp_path):
    instance = ControlPlaneService(FileStore(tmp_path))
    instance.create_container("GTM-ABC1234")
    return instance


def _valid_payload() -> ConfigPayload:
    destination = Destination.create(
        name="GA4",
        kind="ga4",
        config={"measurement_id": "G-123"},
        secret_refs={"api_secret": "env:GA4_SECRET"},
    )
    trigger = Trigger.create(
        name="Cart",
        type="custom_event",
        conditions={"op": "equals", "path": "event.name", "value": "add_to_cart"},
    )
    tag = Tag.create(
        name="Add to cart",
        type="ga4_event",
        parameters={"event_name": "add_to_cart"},
        trigger_ids=(trigger.trigger_id,),
        destination_ids=(destination.destination_id,),
        consent_purpose="analytics",
    )
    return ConfigPayload(tags=(tag,), triggers=(trigger,), destinations=(destination,))


def test_diff_reports_added_removed_and_changed_objects():
    tag = Tag.create(name="Purchase", type="ga4_event")
    trigger = Trigger.create(name="Event", type="custom_event")
    base = ConfigPayload(tags=(tag,), triggers=(trigger,))
    changed_tag = replace(tag, name="Purchase v2")
    changed = ConfigPayload(tags=(changed_tag,))
    changes = diff_payloads(base, changed)
    assert [(item.object_type, item.change) for item in changes] == [
        ("tag", "changed"),
        ("trigger", "removed"),
    ]
    assert changes[0].fields == ("name",)
    assert changes[0].before["name"] == "Purchase"
    assert changes[0].after["name"] == "Purchase v2"

    added = diff_payloads(ConfigPayload(), ConfigPayload(tags=(tag,), triggers=(trigger,)))
    assert [item.change for item in added] == ["added", "added"]


def test_service_diff_defaults_to_parent_and_latest(service):
    first = service.create_revision("GTM-ABC1234")
    second = service.create_revision("GTM-ABC1234", _valid_payload())
    diff = service.diff_revisions("GTM-ABC1234")
    assert diff.from_config_version == first.config_version
    assert diff.to_config_version == second.config_version
    assert diff.summary["added"] == 3
    assert diff.identical is False
    assert diff.to_dict()["to"]["revision_number"] == 2


def test_diff_requires_explicit_base_for_root_revision(service):
    service.create_revision("GTM-ABC1234")
    with pytest.raises(ValidationError):
        service.diff_revisions("GTM-ABC1234")


def test_environment_activation_validation_and_protected_guard(service):
    invalid = service.create_revision(
        "GTM-ABC1234", ConfigPayload(tags=(Tag.create(name="Bad", type="ga4_event"),))
    )
    env = service.create_environment("GTM-ABC1234", "Production", protected=True)
    with pytest.raises(ValidationError, match="protected"):
        service.activate_environment(
            "GTM-ABC1234", "Production", config_version=invalid.config_version
        )
    assert service.get_environment("GTM-ABC1234", "Production").current_config_version is None

    valid = service.create_revision("GTM-ABC1234", _valid_payload())
    with pytest.raises(ValidationError, match="failed validation"):
        service.activate_environment(
            "GTM-ABC1234",
            "Production",
            config_version=invalid.config_version,
            allow_protected=True,
        )
    result = service.activate_environment(
        "GTM-ABC1234",
        "Production",
        config_version=valid.config_version,
        allow_protected=True,
        activated_by="alice",
    )
    assert result.changed
    assert result.environment.current_config_version == valid.config_version
    assert result.environment.previous_config_version is None
    assert result.environment.updated_by == "alice"
    assert env.environment_id == result.environment.environment_id


def test_activation_is_idempotent_and_guards_stale_state(service):
    first = service.create_revision("GTM-ABC1234")
    second = service.create_revision("GTM-ABC1234", _valid_payload())
    service.create_environment("GTM-ABC1234", "Staging")
    activated = service.activate_environment(
        "GTM-ABC1234", "staging", config_version=first.config_version, expected_current=None
    )
    assert activated.changed
    noop = service.activate_environment(
        "GTM-ABC1234", "Staging", config_version=first.config_version
    )
    assert noop.changed is False
    service.activate_environment(
        "GTM-ABC1234",
        "Staging",
        config_version=second.config_version,
        expected_current=first.config_version,
    )
    with pytest.raises(ConflictError):
        service.activate_environment(
            "GTM-ABC1234",
            "Staging",
            config_version=first.config_version,
            expected_current=first.config_version,
        )


def test_rollback_uses_previous_revision_and_can_toggle(service):
    first = service.create_revision("GTM-ABC1234")
    second = service.create_revision("GTM-ABC1234", _valid_payload())
    service.create_environment("GTM-ABC1234", "Production", protected=True)
    with pytest.raises(ValidationError, match="no previous revision"):
        service.rollback_environment("GTM-ABC1234", "Production", allow_protected=True)

    service.activate_environment(
        "GTM-ABC1234", "Production", config_version=first.config_version, allow_protected=True
    )
    service.activate_environment(
        "GTM-ABC1234", "Production", config_version=second.config_version, allow_protected=True
    )
    rolled = service.rollback_environment(
        "GTM-ABC1234", "Production", allow_protected=True, rolled_back_by="bob"
    )
    assert rolled.environment.current_config_version == first.config_version
    assert rolled.environment.previous_config_version == second.config_version
    assert rolled.environment.updated_by == "bob"
    with pytest.raises(ValidationError, match="protected"):
        service.rollback_environment("GTM-ABC1234", "Production")


def test_audit_is_ordered_and_contains_no_config_payload(service):
    revision = service.create_revision("GTM-ABC1234", _valid_payload())
    service.create_environment("GTM-ABC1234", "Production", protected=True)
    service.activate_environment(
        "GTM-ABC1234",
        "Production",
        config_version=revision.config_version,
        allow_protected=True,
        activated_by="alice",
    )
    events = service.list_audit_events("GTM-ABC1234")
    assert [event.sequence for event in events] == list(range(len(events), 0, -1))
    assert {event.action for event in events} == {
        "revision.created",
        "environment.created",
        "environment.activated",
    }
    assert all(event.result == "success" for event in events)
    serialized = json.dumps([event.to_dict() for event in events])
    assert "secret_refs" not in serialized
    assert "env:GA4_SECRET" not in serialized
    assert '"payload"' not in serialized


def test_failed_activation_is_audited(service):
    first = service.create_revision("GTM-ABC1234")
    service.create_environment("GTM-ABC1234", "Production", protected=True)
    with pytest.raises(ValidationError):
        service.activate_environment(
            "GTM-ABC1234",
            "Production",
            config_version=first.config_version,
        )
    events = service.list_audit_events("GTM-ABC1234")
    failed = [event for event in events if event.result == "failed"]
    assert len(failed) == 1
    assert failed[0].details == {"reason": "protected_environment"}


def test_environment_model_accepts_legacy_records():
    legacy = {
        "environment_id": "00000000-0000-4000-8000-000000000001",
        "org_id": "00000000-0000-4000-8000-000000000002",
        "container_id": "GTM-ABC1234",
        "name": "Legacy",
        "protected": False,
        "current_config_version": None,
        "created_at": "2026-01-01T00:00:00.000Z",
        "created_by": "local",
    }
    environment = Environment.from_dict(legacy)
    assert environment.previous_config_version is None
    assert environment.updated_at is None
    assert environment.updated_by is None


def test_export_import_remaps_active_and_previous_revisions(service, tmp_path):
    first = service.create_revision("GTM-ABC1234")
    second = service.create_revision("GTM-ABC1234", _valid_payload())
    service.create_environment("GTM-ABC1234", "Production", protected=True)
    service.activate_environment(
        "GTM-ABC1234", "Production", config_version=first.config_version, allow_protected=True
    )
    service.activate_environment(
        "GTM-ABC1234", "Production", config_version=second.config_version, allow_protected=True
    )
    document = service.export_container("GTM-ABC1234")
    other = ControlPlaneService(FileStore(tmp_path / "other"))
    other.import_container(document, as_container_id="GTM-COPY123")
    imported = other.get_environment("GTM-COPY123", "Production")
    assert imported.current_config_version not in {first.config_version, second.config_version}
    assert imported.previous_config_version not in {first.config_version, second.config_version}
    assert other.get_revision("GTM-COPY123", imported.current_config_version)
    assert other.get_revision("GTM-COPY123", imported.previous_config_version)


def test_cli_environment_lifecycle_diff_and_audit(tmp_path):
    service = ControlPlaneService(FileStore(tmp_path))
    service.create_container("GTM-ABC1234")
    first = service.create_revision("GTM-ABC1234")
    second = service.create_revision("GTM-ABC1234", _valid_payload())
    runner = CliRunner()
    base = ["--home", str(tmp_path)]

    created = runner.invoke(
        cli.main,
        ["environment", "create", "GTM-ABC1234", "--name", "Production", "--protected", *base],
    )
    assert created.exit_code == 0, created.output

    listed = runner.invoke(cli.main, ["environment", "list", "GTM-ABC1234", *base])
    assert listed.exit_code == 0
    assert "Production" in listed.output

    blocked = runner.invoke(
        cli.main,
        [
            "environment",
            "activate",
            "GTM-ABC1234",
            "Production",
            "--config-version",
            first.config_version,
            *base,
        ],
    )
    assert blocked.exit_code != 0
    assert "protected" in blocked.output

    activated = runner.invoke(
        cli.main,
        [
            "environment",
            "activate",
            "GTM-ABC1234",
            "Production",
            "--config-version",
            second.config_version,
            "--allow-protected",
            "--actor",
            "alice",
            "--json",
            *base,
        ],
    )
    assert activated.exit_code == 0, activated.output
    payload = json.loads(activated.output)
    assert payload["changed"] is True
    assert payload["environment"]["current_config_version"] == second.config_version

    diffed = runner.invoke(
        cli.main,
        [
            "config",
            "diff",
            "GTM-ABC1234",
            "--from",
            first.config_version,
            "--to",
            second.config_version,
            "--json",
            *base,
        ],
    )
    assert diffed.exit_code == 0, diffed.output
    assert json.loads(diffed.output)["summary"]["added"] == 3

    audited = runner.invoke(
        cli.main, ["container", "audit", "--id", "GTM-ABC1234", "--json", *base]
    )
    assert audited.exit_code == 0, audited.output
    actions = {event["action"] for event in json.loads(audited.output)}
    assert "environment.activated" in actions
