from __future__ import annotations

import json
import os

import pytest

from pytagmanager.control.errors import (
    ConflictError,
    CorruptStoreError,
    NotFoundError,
    SchemaVersionError,
)
from pytagmanager.control.models import (
    ConfigRevision,
    Container,
    Organization,
    Workspace,
)
from pytagmanager.control.store import FileStore


def _entities(store: FileStore):
    organization = Organization.create("Acme")
    workspace = Workspace.create(organization.org_id, "Web")
    container = Container.create(
        container_id="GTM-ABC1234",
        org_id=organization.org_id,
        workspace_id=workspace.workspace_id,
    )
    return organization, workspace, container


def test_initialize_creates_private_metadata_and_is_idempotent(tmp_path):
    store = FileStore(tmp_path)
    first = store.initialize()
    second = store.initialize()
    assert first == second
    assert (tmp_path / "store.json").exists()
    payload = json.loads((tmp_path / "store.json").read_text(encoding="utf-8"))
    assert payload["kind"] == "store"
    assert payload["schema_version"] == "1.0"
    if os.name == "posix":
        assert (tmp_path / "store.json").stat().st_mode & 0o777 == 0o600
        assert (tmp_path / "orgs").stat().st_mode & 0o777 == 0o700


def test_entities_round_trip_and_container_path_does_not_use_raw_id(tmp_path):
    store = FileStore(tmp_path)
    store.initialize()
    organization, workspace, container = _entities(store)
    store.save_organization(organization)
    store.save_workspace(workspace)
    store.save_container(container)

    assert store.get_organization(organization.org_id) == organization
    assert store.get_workspace(organization.org_id, workspace.workspace_id) == workspace
    assert store.get_container(organization.org_id, container.container_id) == container
    assert store.container_exists(organization.org_id, "gtm-abc1234")
    assert store.list_organizations() == [organization]
    assert store.list_workspaces(organization.org_id) == [workspace]
    assert store.list_containers(organization.org_id) == [container]

    path = store.container_dir(organization.org_id, container.container_id)
    assert "GTM-ABC1234" not in str(path)
    assert "gtm-abc1234" in path.name


def test_revisions_are_immutable(tmp_path):
    store = FileStore(tmp_path)
    store.initialize()
    organization, workspace, container = _entities(store)
    store.save_organization(organization)
    store.save_workspace(workspace)
    store.save_container(container)

    revision = ConfigRevision.create(
        container_id=container.container_id,
        revision_number=1,
        parent_config_version=None,
    )
    store.save_revision(container, revision)
    assert store.get_revision(container, revision.config_version) == revision
    assert store.latest_revision(container) == revision

    with pytest.raises(ConflictError):
        store.save_revision(container, revision)

    tampered = ConfigRevision.from_dict(revision.to_dict())
    assert tampered.checksum == revision.checksum


def test_missing_and_corrupt_documents_are_reported(tmp_path):
    store = FileStore(tmp_path)
    store.initialize()
    with pytest.raises(NotFoundError):
        store.get_organization("00000000-0000-4000-8000-000000000000")

    organization = Organization.create("Acme")
    store.save_organization(organization)
    path = tmp_path / "orgs" / organization.org_id / "organization.json"
    path.write_text("{not json", encoding="utf-8")
    with pytest.raises(CorruptStoreError):
        store.get_organization(organization.org_id)


def test_unsupported_schema_is_rejected(tmp_path):
    store = FileStore(tmp_path)
    store.initialize()
    organization = Organization.create("Acme")
    store.save_organization(organization)
    path = tmp_path / "orgs" / organization.org_id / "organization.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["schema_version"] = "2.0"
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(SchemaVersionError):
        store.get_organization(organization.org_id)


def test_remove_container_tree_is_scoped(tmp_path):
    store = FileStore(tmp_path)
    store.initialize()
    organization, workspace, container = _entities(store)
    store.save_organization(organization)
    store.save_workspace(workspace)
    store.save_container(container)
    other = Container.create(
        container_id="GTM-OTHER",
        org_id=organization.org_id,
        workspace_id=workspace.workspace_id,
    )
    store.save_container(other)

    store.remove_container_tree(organization.org_id, container.container_id)
    assert not store.container_exists(organization.org_id, container.container_id)
    assert store.container_exists(organization.org_id, other.container_id)
