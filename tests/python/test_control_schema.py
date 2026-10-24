from __future__ import annotations

from dataclasses import replace

import pytest
from pytagmanager.control.checksums import canonical_json, checksum, verify_checksum
from pytagmanager.control.config import Tag
from pytagmanager.control.errors import SchemaVersionError, ValidationError
from pytagmanager.control.models import (
    ConfigPayload,
    ConfigRevision,
    Container,
    Organization,
)
from pytagmanager.control.schema import (
    CURRENT_SCHEMA_VERSION,
    migrate_document,
    unwrap_document,
    wrap_document,
)


def test_canonical_json_is_order_independent_and_rejects_nan():
    assert canonical_json({"b": 1, "a": [2, 3]}) == '{"a":[2,3],"b":1}'
    assert checksum({"b": 1, "a": 2}) == checksum({"a": 2, "b": 1})
    assert verify_checksum({"a": 1}, checksum({"a": 1}))
    with pytest.raises(ValidationError):
        canonical_json({"value": float("nan")})
    with pytest.raises(ValidationError):
        canonical_json({1: "non-string-key"})


def test_document_envelope_round_trips_and_fails_closed():
    document = wrap_document("container", {"x": 1})
    assert document["schema_version"] == CURRENT_SCHEMA_VERSION
    assert unwrap_document(document, expected_kind="container") == {"x": 1}
    assert migrate_document(document) == document

    with pytest.raises(ValidationError):
        unwrap_document(document, expected_kind="workspace")

    with pytest.raises(ValidationError):
        unwrap_document({"schema_version": "1.0", "kind": "container"})

    with pytest.raises(ValidationError):
        wrap_document("unknown", {})

    unsupported = dict(document, schema_version="2.0")
    with pytest.raises(SchemaVersionError):
        unwrap_document(unsupported)


def test_config_payload_requires_known_collections_and_unique_ids():
    tag = Tag.create(name="Purchase", type="ga4_event").to_dict()
    payload = ConfigPayload.from_dict(
        {"tags": [tag], "triggers": [], "variables": [], "destinations": []}
    )
    assert payload.object_count() == 1
    assert payload.to_dict()["tags"] == [tag]

    with pytest.raises(ValidationError):
        ConfigPayload.from_dict({"tags": [], "unknown": []})
    with pytest.raises(ValidationError):
        ConfigPayload.from_dict({"tags": [tag, tag]})
    with pytest.raises(ValidationError):
        ConfigPayload.from_dict({"tags": [{"tag_id": tag["tag_id"], "name": "x"}]})


def test_revision_checksum_detects_tampering():
    revision = ConfigRevision.create(
        container_id="GTM-ABC1234",
        revision_number=1,
        parent_config_version=None,
        payload=ConfigPayload(tags=(Tag.create(name="Purchase", type="ga4_event"),)),
    )
    revision.verify()

    tampered = replace(
        revision,
        payload=ConfigPayload(tags=(Tag.create(name="Changed", type="ga4_event"),)),
    )
    with pytest.raises(ValidationError):
        tampered.verify()

    with pytest.raises(ValidationError):
        ConfigRevision.from_dict(revision.to_dict() | {"checksum": "sha256:bad"})
    with pytest.raises(ValidationError):
        ConfigRevision.from_dict(revision.to_dict() | {"revision_number": 0})


def test_container_and_organization_round_trip():
    organization = Organization.create("Acme")
    assert Organization.from_dict(organization.to_dict()) == organization

    container = Container.create(
        container_id="GTM-ABC1234",
        org_id=organization.org_id,
        workspace_id=organization.org_id,
        name="Web",
        site_urls=["https://example.com"],
        external_refs=[{"system": "gtm", "id": "GTM-ABC1234"}],
    )
    assert Container.from_dict(container.to_dict()) == container
    with pytest.raises(ValidationError):
        Container.from_dict(
            container.to_dict() | {"external_refs": [{"system": "gtm", "id": "GTM-ABC1234"}] * 2}
        )
