from __future__ import annotations

import json
from pathlib import Path

import pytest
from click.testing import CliRunner

from pytagmanager import cli
from pytagmanager.control import (
    ConfigPayload,
    ControlPlaneService,
    Destination,
    FileStore,
    Tag,
    Trigger,
)
from pytagmanager.control.errors import ConflictError, ValidationError
from pytagmanager.distribution import (
    FilesystemCDN,
    build_published_config,
    verify_published_config,
)


def _payload() -> ConfigPayload:
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


@pytest.fixture
def active_container(tmp_path):
    service = ControlPlaneService(FileStore(tmp_path / "state"))
    service.create_container("GTM-ABC1234")
    first = service.create_revision("GTM-ABC1234")
    second = service.create_revision("GTM-ABC1234", _payload())
    service.create_environment("GTM-ABC1234", "Production")
    service.activate_environment(
        "GTM-ABC1234", "Production", config_version=first.config_version
    )
    service.activate_environment(
        "GTM-ABC1234", "Production", config_version=second.config_version
    )
    return service, first, second, tmp_path / "cdn"


def test_public_config_contains_no_destination_secrets(active_container):
    service, _, second, _ = active_container
    config = build_published_config(service, "GTM-ABC1234", "Production")
    assert config["container_id"] == "GTM-ABC1234"
    assert config["config_version"] == second.config_version
    assert config["features"]["client_side_execution"] is False
    assert config["events"][0]["name"] == "add_to_cart"
    assert config["events"][0]["purposes"] == ["analytics"]
    assert config["destinations"][0]["kind"] == "ga4"
    serialized = json.dumps(config)
    assert "secret_refs" not in serialized
    assert "GA4_SECRET" not in serialized
    assert "measurement_id" not in serialized
    verify_published_config(config)


def test_tampered_public_config_fails_integrity(active_container):
    service, _, _, _ = active_container
    config = build_published_config(service, "GTM-ABC1234", "Production")
    config["events"][0]["name"] = "tampered"
    with pytest.raises(ValidationError, match="integrity"):
        verify_published_config(config)


def test_publish_writes_immutable_assets_and_pointer(active_container):
    service, _, second, root = active_container
    publisher = FilesystemCDN(root, sdk_version="0.1.0")
    result = publisher.publish_environment(
        service, "GTM-ABC1234", "Production", default_consent={"analytics": False}
    )
    config_file = root / result.config_path
    assert config_file.is_file()
    assert (root / f"{result.config_path}.sha256").is_file()
    assert (root / result.latest_path).is_file()
    assert (root / result.sdk_path).is_file()
    assert (root / "_headers.json").is_file()
    assert (root / "index.json").is_file()
    config = json.loads(config_file.read_text())
    assert config["config_version"] == second.config_version
    assert config["consent_defaults"] == {"analytics": False}
    pointer = json.loads((root / result.latest_path).read_text())
    assert pointer["config_version"] == second.config_version
    assert pointer["config_url"] == f"/{result.config_path}"
    assert pointer["sdk"]["web"]["version"] == "0.1.0"
    headers = json.loads((root / "_headers.json").read_text())
    assert "immutable" in headers[f"/{result.config_path}"]["Cache-Control"]
    assert "no-cache" in headers[f"/{result.latest_path}"]["Cache-Control"]
    assert publisher.verify() == []


def test_republish_is_idempotent_for_the_same_revision(active_container):
    service, _, _, root = active_container
    publisher = FilesystemCDN(root)
    first = publisher.publish_environment(service, "GTM-ABC1234", "Production")
    second = publisher.publish_environment(service, "GTM-ABC1234", "Production")
    assert second.config_version == first.config_version
    assert second.file_sha256 == first.file_sha256
    assert second.integrity_digest == first.integrity_digest
    assert json.loads((root / second.latest_path).read_text())["published_at"] == first.published_at
    assert publisher.verify() == []


def test_publish_protected_environment_requires_explicit_approval(active_container):
    service, _, second, root = active_container
    service.create_environment("GTM-ABC1234", "Protected Prod", protected=True)
    service.activate_environment(
        "GTM-ABC1234",
        "Protected Prod",
        config_version=second.config_version,
        allow_protected=True,
    )
    publisher = FilesystemCDN(root)
    with pytest.raises(ValidationError, match="protected"):
        publisher.publish_environment(service, "GTM-ABC1234", "Protected Prod")
    result = publisher.publish_environment(
        service, "GTM-ABC1234", "Protected Prod", allow_protected=True
    )
    assert result.config_version == second.config_version


def test_verify_detects_tampered_files(active_container):
    service, _, _, root = active_container
    publisher = FilesystemCDN(root)
    result = publisher.publish_environment(service, "GTM-ABC1234", "Production")
    (root / result.config_path).write_text("{}\n", encoding="utf-8")
    issues = publisher.verify()
    assert issues
    assert any("checksum" in issue["message"] for issue in issues)


def test_publish_requires_active_revision(tmp_path):
    service = ControlPlaneService(FileStore(tmp_path / "state"))
    service.create_container("GTM-NOACTIVE")
    service.create_environment("GTM-NOACTIVE", "Production")
    with pytest.raises(ValidationError, match="no active configuration"):
        FilesystemCDN(tmp_path / "cdn").publish_environment(
            service, "GTM-NOACTIVE", "Production"
        )


def test_cli_publish_verify_status_and_rollback(active_container):
    service, first, second, root = active_container
    home = str(service.store.root)
    runner = CliRunner()

    published = runner.invoke(
        cli.main,
        [
            "cdn",
            "publish",
            "GTM-ABC1234",
            "Production",
            "--home",
            home,
            "--root",
            str(root),
            "--json",
        ],
    )
    assert published.exit_code == 0, published.output
    result = json.loads(published.output)
    assert result["config_version"] == second.config_version

    verified = runner.invoke(
        cli.main, ["cdn", "verify", "--root", str(root), "--json"]
    )
    assert verified.exit_code == 0, verified.output
    assert json.loads(verified.output)["valid"] is True

    status = runner.invoke(
        cli.main,
        ["cdn", "status", "GTM-ABC1234", "Production", "--home", home, "--root", str(root), "--json"],
    )
    assert status.exit_code == 0, status.output
    assert json.loads(status.output)["current_config_version"] == second.config_version

    rolled = runner.invoke(
        cli.main,
        [
            "cdn",
            "rollback",
            "GTM-ABC1234",
            "Production",
            "--home",
            home,
            "--root",
            str(root),
            "--json",
        ],
    )
    assert rolled.exit_code == 0, rolled.output
    payload = json.loads(rolled.output)
    assert payload["publication"]["config_version"] == first.config_version
    pointer = json.loads((root / payload["publication"]["latest_path"]).read_text())
    assert pointer["config_version"] == first.config_version
