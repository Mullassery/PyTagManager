from __future__ import annotations

import copy

import pytest
from pytagmanager.control.config import ConfigPayload, Tag
from pytagmanager.control.errors import (
    ConflictError,
    NotFoundError,
    SchemaVersionError,
    ValidationError,
)
from pytagmanager.control.service import ControlPlaneService
from pytagmanager.control.store import FileStore


@pytest.fixture
def service(tmp_path):
    return ControlPlaneService(FileStore(tmp_path))


def test_default_scope_is_created_once(service):
    org_id, workspace_id = service.ensure_default_scope()
    assert service.ensure_default_scope() == (org_id, workspace_id)
    assert len(service.list_organizations()) == 1
    assert len(service.list_workspaces(org_id)) == 1


def test_create_container_preserves_user_supplied_gtm_id(service):
    container = service.create_container("GTM-ABC1234", name="Web")
    assert container.container_id == "GTM-ABC1234"
    assert service.get_container("GTM-ABC1234") == container
    assert service.list_containers() == [container]


def test_container_ids_are_unique_case_insensitively_per_organization(service):
    service.create_container("GTM-ABC1234")
    with pytest.raises(ConflictError):
        service.create_container("gtm-abc1234")


def test_same_container_id_can_exist_in_two_organizations(service):
    first_org, _ = service.ensure_default_scope()
    second_org = service.create_organization("Second")
    assert len(service.list_workspaces(second_org.org_id)) == 1

    service.create_container("GTM-ABC1234", org_id=first_org)
    service.create_container("GTM-ABC1234", org_id=second_org.org_id)
    assert len(service.list_containers(org_id=second_org.org_id)) == 1


def test_revision_chain_tracks_parent_and_guards_optimistic_concurrency(service):
    service.create_container("GTM-ABC1234")
    first = service.create_revision("GTM-ABC1234")
    second = service.create_revision("GTM-ABC1234")
    assert first.revision_number == 1
    assert first.parent_config_version is None
    assert second.revision_number == 2
    assert second.parent_config_version == first.config_version

    with pytest.raises(ConflictError):
        service.create_revision("GTM-ABC1234", expected_parent=first.config_version)

    third = service.create_revision("GTM-ABC1234", expected_parent=second.config_version)
    assert third.parent_config_version == second.config_version
    assert [item.revision_number for item in service.list_revisions("GTM-ABC1234")] == [
        1,
        2,
        3,
    ]


def test_validate_reports_latest_revision(service):
    service.create_container("GTM-ABC1234")
    revision = service.create_revision(
        "GTM-ABC1234",
        ConfigPayload(tags=(Tag.create(name="Purchase", type="ga4_event"),)),
    )
    report = service.validate_container("GTM-ABC1234")
    assert report.revision_count == 1
    assert report.latest_config_version == revision.config_version
    assert report.latest_checksum == revision.checksum
    assert report.payload_objects == 1
    assert report.to_dict()["valid"] is True


def test_missing_container_reports_not_found(service):
    with pytest.raises(NotFoundError):
        service.get_container("GTM-MISSING")


def test_export_import_round_trips_into_a_fresh_store(service, tmp_path):
    service.create_container("GTM-ABC1234", name="Web")
    revision = service.create_revision("GTM-ABC1234")
    document = service.export_container("GTM-ABC1234")

    other = ControlPlaneService(FileStore(tmp_path / "other"))
    result = other.import_container(document)
    assert result.created is True
    assert result.container.container_id == "GTM-ABC1234"
    assert other.get_revision("GTM-ABC1234", revision.config_version) == revision

    again = other.import_container(document)
    assert again.created is False
    assert again.revision_count == 1


def test_import_conflicts_when_existing_container_differs(service, tmp_path):
    service.create_container("GTM-ABC1234")
    document = service.export_container("GTM-ABC1234")

    other = ControlPlaneService(FileStore(tmp_path / "other"))
    other.create_container("GTM-ABC1234")
    other.create_revision("GTM-ABC1234")
    with pytest.raises(ConflictError):
        other.import_container(document)


def test_import_as_remaps_identity_and_clears_external_refs(service, tmp_path):
    service.create_container(
        "GTM-ABC1234",
        name="Web",
        external_refs=[{"system": "gtm", "id": "GTM-ABC1234"}],
    )
    first = service.create_revision("GTM-ABC1234")
    second = service.create_revision("GTM-ABC1234")
    document = service.export_container("GTM-ABC1234")

    other = ControlPlaneService(FileStore(tmp_path / "other"))
    result = other.import_container(document, as_container_id="GTM-COPY123")
    assert result.created is True
    assert result.container.container_id == "GTM-COPY123"
    assert result.container.external_refs == ()

    revisions = other.list_revisions("GTM-COPY123")
    assert [item.revision_number for item in revisions] == [1, 2]
    assert revisions[0].config_version != first.config_version
    assert revisions[1].parent_config_version == revisions[0].config_version
    assert revisions[0].payload == first.payload
    assert revisions[0].checksum != first.checksum
    assert revisions[0].status == "draft"

    assert service.list_revisions("GTM-ABC1234") == [first, second]


def test_clone_uses_new_id_and_does_not_touch_source(service):
    service.create_container("GTM-ABC1234")
    service.create_revision("GTM-ABC1234")
    result = service.clone_container("GTM-ABC1234", "GTM-CLONE99")
    assert result.container.container_id == "GTM-CLONE99"
    assert result.renamed_from == "GTM-ABC1234"
    assert len(service.list_revisions("GTM-CLONE99")) == 1
    assert service.get_container("GTM-ABC1234").container_id == "GTM-ABC1234"


def test_import_rejects_tampered_checksums_and_unknown_schema(service, tmp_path):
    service.create_container("GTM-ABC1234")
    service.create_revision("GTM-ABC1234")
    document = service.export_container("GTM-ABC1234")

    tampered = copy.deepcopy(document)
    tampered["data"]["revisions"][0]["checksum"] = "sha256:bad"
    other = ControlPlaneService(FileStore(tmp_path / "other"))
    with pytest.raises(ValidationError):
        other.import_container(tampered)

    unsupported = copy.deepcopy(document)
    unsupported["schema_version"] = "2.0"
    with pytest.raises(SchemaVersionError):
        other.import_container(unsupported)


def test_import_rejects_missing_parent_and_duplicate_numbers(service, tmp_path):
    service.create_container("GTM-ABC1234")
    service.create_revision("GTM-ABC1234")
    service.create_revision("GTM-ABC1234")
    document = service.export_container("GTM-ABC1234")

    missing_parent = copy.deepcopy(document)
    missing_parent["data"]["revisions"][1]["parent_config_version"] = (
        "00000000-0000-4000-8000-000000000000"
    )
    other = ControlPlaneService(FileStore(tmp_path / "other"))
    with pytest.raises(ValidationError):
        other.import_container(missing_parent)

    duplicate = copy.deepcopy(document)
    duplicate["data"]["revisions"][1]["revision_number"] = 1
    with pytest.raises(ValidationError):
        other.import_container(duplicate)


def test_environments_are_exported_and_remapped_on_import_as(service, tmp_path):
    service.create_container("GTM-ABC1234")
    revision = service.create_revision("GTM-ABC1234")
    environment = service.create_environment("GTM-ABC1234", "Development")
    assert service.list_environments("GTM-ABC1234") == [environment]

    document = service.export_container("GTM-ABC1234")
    other = ControlPlaneService(FileStore(tmp_path / "other"))
    other.import_container(document, as_container_id="GTM-COPY123")

    imported = other.list_environments("GTM-COPY123")
    assert len(imported) == 1
    assert imported[0].environment_id != environment.environment_id
    mapped = other.validate_container("GTM-COPY123")
    assert mapped.latest_config_version != revision.config_version


def test_import_cleans_up_when_a_write_fails(service, tmp_path, monkeypatch):
    service.create_container("GTM-ABC1234")
    service.create_revision("GTM-ABC1234")
    document = service.export_container("GTM-ABC1234")

    other = ControlPlaneService(FileStore(tmp_path / "other"))
    original = other.store.save_revision

    def failing(container, revision):
        raise RuntimeError("disk full")

    monkeypatch.setattr(other.store, "save_revision", failing)
    with pytest.raises(RuntimeError):
        other.import_container(document)
    assert other.list_containers() == []
    monkeypatch.setattr(other.store, "save_revision", original)
