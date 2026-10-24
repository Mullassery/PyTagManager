"""Typed persisted models for the control-plane foundation."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, replace
from typing import Any

from pytagmanager.control.checksums import canonical_json, checksum
from pytagmanager.control.config import (
    ConfigPayload,
)
from pytagmanager.control.errors import ValidationError
from pytagmanager.control.ids import (
    new_id,
    utc_now,
    validate_container_id,
    validate_id,
    validate_name,
)

SCHEMA_VERSION = "1.0"

_REVISION_STATUSES = frozenset({"draft", "validated", "published", "archived"})
_CONTAINER_STATUSES = frozenset({"active", "archived"})


def _mapping(value: Any, field: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValidationError(f"{field} must be a JSON object")
    return value


def _string(value: Any, field: str, *, allow_empty: bool = False) -> str:
    if not isinstance(value, str):
        raise ValidationError(f"{field} must be a string")
    if not allow_empty and not value:
        raise ValidationError(f"{field} must not be empty")
    return value


def _string_tuple(value: Any, field: str) -> tuple[str, ...]:
    if not isinstance(value, (list, tuple)):
        raise ValidationError(f"{field} must be a list of strings")
    result = []
    for index, item in enumerate(value):
        result.append(_string(item, f"{field}[{index}]"))
    return tuple(result)


def _object_tuple(value: Any, field: str) -> tuple[dict[str, Any], ...]:
    if not isinstance(value, (list, tuple)):
        raise ValidationError(f"{field} must be a list of objects")
    result = []
    for index, item in enumerate(value):
        result.append(dict(_mapping(item, f"{field}[{index}]")))
    return tuple(result)


def _check_unknown_keys(data: Mapping[str, Any], expected: set[str], field: str) -> None:
    unknown = sorted(set(data) - expected)
    if unknown:
        raise ValidationError(f"{field} contains unknown field(s): {', '.join(unknown)}")


def _check_required_keys(data: Mapping[str, Any], required: tuple[str, ...], field: str) -> None:
    missing = [key for key in required if key not in data]
    if missing:
        raise ValidationError(f"{field} is missing required field(s): {', '.join(missing)}")


def _external_refs(value: Any) -> tuple[dict[str, Any], ...]:
    refs = _object_tuple(value, "external_refs")
    seen = set()
    for index, ref in enumerate(refs):
        system = _string(ref.get("system"), f"external_refs[{index}].system")
        ref_id = _string(ref.get("id"), f"external_refs[{index}].id")
        key = (system.casefold(), ref_id.casefold())
        if key in seen:
            raise ValidationError(f"external_refs contains duplicate {system}:{ref_id}")
        seen.add(key)
    return refs


@dataclass(frozen=True)
class Organization:
    org_id: str
    name: str
    created_at: str
    created_by: str = "local"

    @classmethod
    def create(cls, name: str, *, created_by: str = "local") -> Organization:
        return cls(
            org_id=new_id(),
            name=validate_name(name),
            created_at=utc_now(),
            created_by=_string(created_by, "created_by"),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "org_id": self.org_id,
            "name": self.name,
            "created_at": self.created_at,
            "created_by": self.created_by,
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> Organization:
        data = _mapping(value, "organization")
        expected = {"org_id", "name", "created_at", "created_by"}
        _check_unknown_keys(data, expected, "organization")
        _check_required_keys(data, ("org_id", "name", "created_at", "created_by"), "organization")
        return cls(
            org_id=validate_id(data["org_id"], field="org_id"),
            name=validate_name(data["name"]),
            created_at=_string(data["created_at"], "created_at"),
            created_by=_string(data["created_by"], "created_by"),
        )


@dataclass(frozen=True)
class Workspace:
    workspace_id: str
    org_id: str
    name: str
    created_at: str
    created_by: str = "local"

    @classmethod
    def create(cls, org_id: str, name: str, *, created_by: str = "local") -> Workspace:
        return cls(
            workspace_id=new_id(),
            org_id=validate_id(org_id, field="org_id"),
            name=validate_name(name),
            created_at=utc_now(),
            created_by=_string(created_by, "created_by"),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "workspace_id": self.workspace_id,
            "org_id": self.org_id,
            "name": self.name,
            "created_at": self.created_at,
            "created_by": self.created_by,
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> Workspace:
        data = _mapping(value, "workspace")
        expected = {"workspace_id", "org_id", "name", "created_at", "created_by"}
        _check_unknown_keys(data, expected, "workspace")
        _check_required_keys(data, tuple(sorted(expected)), "workspace")
        return cls(
            workspace_id=validate_id(data["workspace_id"], field="workspace_id"),
            org_id=validate_id(data["org_id"], field="org_id"),
            name=validate_name(data["name"]),
            created_at=_string(data["created_at"], "created_at"),
            created_by=_string(data["created_by"], "created_by"),
        )


@dataclass(frozen=True)
class Container:
    container_id: str
    org_id: str
    workspace_id: str
    name: str
    description: str
    site_urls: tuple[str, ...]
    external_refs: tuple[dict[str, Any], ...]
    created_at: str
    created_by: str
    status: str = "active"

    @classmethod
    def create(
        cls,
        *,
        container_id: str,
        org_id: str,
        workspace_id: str,
        name: str | None = None,
        description: str = "",
        site_urls: tuple[str, ...] | list[str] = (),
        external_refs: tuple[dict[str, Any], ...] | list[dict[str, Any]] = (),
        created_by: str = "local",
    ) -> Container:
        container_id = validate_container_id(container_id)
        name = validate_name(name if name is not None else container_id)
        refs = _external_refs(external_refs)
        return cls(
            container_id=container_id,
            org_id=validate_id(org_id, field="org_id"),
            workspace_id=validate_id(workspace_id, field="workspace_id"),
            name=name,
            description=_string(description, "description", allow_empty=True),
            site_urls=_string_tuple(site_urls, "site_urls"),
            external_refs=refs,
            created_at=utc_now(),
            created_by=_string(created_by, "created_by"),
        )

    @property
    def uniqueness_key(self) -> str:
        return self.container_id.casefold()

    def to_dict(self) -> dict[str, Any]:
        return {
            "container_id": self.container_id,
            "org_id": self.org_id,
            "workspace_id": self.workspace_id,
            "name": self.name,
            "description": self.description,
            "site_urls": list(self.site_urls),
            "external_refs": [dict(ref) for ref in self.external_refs],
            "created_at": self.created_at,
            "created_by": self.created_by,
            "status": self.status,
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> Container:
        data = _mapping(value, "container")
        expected = {
            "container_id",
            "org_id",
            "workspace_id",
            "name",
            "description",
            "site_urls",
            "external_refs",
            "created_at",
            "created_by",
            "status",
        }
        _check_unknown_keys(data, expected, "container")
        _check_required_keys(data, tuple(sorted(expected)), "container")
        status = _string(data["status"], "status")
        if status not in _CONTAINER_STATUSES:
            raise ValidationError(f"unsupported container status: {status!r}")
        return cls(
            container_id=validate_container_id(data["container_id"]),
            org_id=validate_id(data["org_id"], field="org_id"),
            workspace_id=validate_id(data["workspace_id"], field="workspace_id"),
            name=validate_name(data["name"]),
            description=_string(data["description"], "description", allow_empty=True),
            site_urls=_string_tuple(data["site_urls"], "site_urls"),
            external_refs=_external_refs(data["external_refs"]),
            created_at=_string(data["created_at"], "created_at"),
            created_by=_string(data["created_by"], "created_by"),
            status=status,
        )


@dataclass(frozen=True)
class Environment:
    environment_id: str
    org_id: str
    container_id: str
    name: str
    protected: bool
    current_config_version: str | None
    created_at: str
    created_by: str = "local"
    previous_config_version: str | None = None
    updated_at: str | None = None
    updated_by: str | None = None

    @classmethod
    def create(
        cls,
        *,
        org_id: str,
        container_id: str,
        name: str,
        protected: bool = False,
        created_by: str = "local",
    ) -> Environment:
        return cls(
            environment_id=new_id(),
            org_id=validate_id(org_id, field="org_id"),
            container_id=validate_container_id(container_id),
            name=validate_name(name),
            protected=bool(protected),
            current_config_version=None,
            created_at=utc_now(),
            created_by=_string(created_by, "created_by"),
            previous_config_version=None,
            updated_at=None,
            updated_by=None,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "environment_id": self.environment_id,
            "org_id": self.org_id,
            "container_id": self.container_id,
            "name": self.name,
            "protected": self.protected,
            "current_config_version": self.current_config_version,
            "created_at": self.created_at,
            "created_by": self.created_by,
            "previous_config_version": self.previous_config_version,
            "updated_at": self.updated_at,
            "updated_by": self.updated_by,
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> Environment:
        data = _mapping(value, "environment")
        expected = {
            "environment_id",
            "org_id",
            "container_id",
            "name",
            "protected",
            "current_config_version",
            "created_at",
            "created_by",
            "previous_config_version",
            "updated_at",
            "updated_by",
        }
        _check_unknown_keys(data, expected, "environment")
        _check_required_keys(
            data,
            (
                "environment_id",
                "org_id",
                "container_id",
                "name",
                "protected",
                "current_config_version",
                "created_at",
                "created_by",
            ),
            "environment",
        )
        current = data["current_config_version"]
        if current is not None:
            current = validate_id(current, field="current_config_version")
        previous = data.get("previous_config_version")
        if previous is not None:
            previous = validate_id(previous, field="previous_config_version")
        if not isinstance(data["protected"], bool):
            raise ValidationError("protected must be a boolean")
        created_at = _string(data["created_at"], "created_at")
        created_by = _string(data["created_by"], "created_by")
        updated_at = data.get("updated_at")
        if updated_at is not None:
            updated_at = _string(updated_at, "updated_at")
        updated_by = data.get("updated_by")
        if updated_by is not None:
            updated_by = _string(updated_by, "updated_by")
        return cls(
            environment_id=validate_id(data["environment_id"], field="environment_id"),
            org_id=validate_id(data["org_id"], field="org_id"),
            container_id=validate_container_id(data["container_id"]),
            name=validate_name(data["name"]),
            protected=data["protected"],
            current_config_version=current,
            created_at=created_at,
            created_by=created_by,
            previous_config_version=previous,
            updated_at=updated_at,
            updated_by=updated_by,
        )


@dataclass(frozen=True)
class AuditEvent:
    event_id: str
    container_id: str
    action: str
    actor: str
    created_at: str
    result: str
    environment_id: str | None = None
    config_version: str | None = None
    previous_config_version: str | None = None
    checksum: str | None = None
    previous_checksum: str | None = None
    details: dict[str, Any] | None = None
    sequence: int = 0

    @classmethod
    def create(
        cls,
        *,
        container_id: str,
        action: str,
        actor: str = "local",
        result: str = "success",
        environment_id: str | None = None,
        config_version: str | None = None,
        previous_config_version: str | None = None,
        checksum: str | None = None,
        previous_checksum: str | None = None,
        details: Mapping[str, Any] | None = None,
        sequence: int = 0,
    ) -> AuditEvent:
        if isinstance(sequence, bool) or not isinstance(sequence, int) or sequence < 0:
            raise ValidationError("audit.sequence must be a non-negative integer")
        action = _string(action, "audit.action")
        if result not in {"success", "failed"}:
            raise ValidationError("audit.result must be 'success' or 'failed'")
        if environment_id is not None:
            environment_id = validate_id(environment_id, field="audit.environment_id")
        for field, value in (
            ("audit.config_version", config_version),
            ("audit.previous_config_version", previous_config_version),
        ):
            if value is not None:
                validate_id(value, field=field)
        for field, value in (
            ("audit.checksum", checksum),
            ("audit.previous_checksum", previous_checksum),
        ):
            if value is not None:
                _string(value, field)
        detail_map = dict(details or {})
        canonical_json(detail_map)
        return cls(
            event_id=new_id(),
            container_id=validate_container_id(container_id),
            action=action,
            actor=_string(actor, "audit.actor"),
            created_at=utc_now(),
            result=result,
            environment_id=environment_id,
            config_version=config_version,
            previous_config_version=previous_config_version,
            checksum=checksum,
            previous_checksum=previous_checksum,
            details=detail_map,
            sequence=sequence,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id,
            "container_id": self.container_id,
            "action": self.action,
            "actor": self.actor,
            "created_at": self.created_at,
            "result": self.result,
            "environment_id": self.environment_id,
            "config_version": self.config_version,
            "previous_config_version": self.previous_config_version,
            "checksum": self.checksum,
            "previous_checksum": self.previous_checksum,
            "details": dict(self.details or {}),
            "sequence": self.sequence,
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> AuditEvent:
        data = _mapping(value, "audit_event")
        expected = {
            "event_id",
            "container_id",
            "action",
            "actor",
            "created_at",
            "result",
            "environment_id",
            "config_version",
            "previous_config_version",
            "checksum",
            "previous_checksum",
            "details",
            "sequence",
        }
        _check_unknown_keys(data, expected, "audit_event")
        required = expected - {"sequence"}
        _check_required_keys(data, tuple(sorted(required)), "audit_event")
        sequence = data.get("sequence", 0)
        if isinstance(sequence, bool) or not isinstance(sequence, int) or sequence < 0:
            raise ValidationError("audit_event.sequence must be a non-negative integer")
        details = data.get("details", {})
        if not isinstance(details, Mapping):
            raise ValidationError("audit_event.details must be a JSON object")
        canonical_json(details)
        result = _string(data["result"], "audit_event.result")
        if result not in {"success", "failed"}:
            raise ValidationError("audit_event.result must be 'success' or 'failed'")
        for field in ("checksum", "previous_checksum"):
            if data.get(field) is not None:
                _string(data[field], f"audit_event.{field}")
        return cls(
            event_id=validate_id(data["event_id"], field="event_id"),
            container_id=validate_container_id(data["container_id"]),
            action=_string(data["action"], "audit_event.action"),
            actor=_string(data["actor"], "audit_event.actor"),
            created_at=_string(data["created_at"], "audit_event.created_at"),
            result=result,
            environment_id=(
                validate_id(data["environment_id"], field="environment_id")
                if data.get("environment_id") is not None
                else None
            ),
            config_version=(
                validate_id(data["config_version"], field="config_version")
                if data.get("config_version") is not None
                else None
            ),
            previous_config_version=(
                validate_id(data["previous_config_version"], field="previous_config_version")
                if data.get("previous_config_version") is not None
                else None
            ),
            checksum=data.get("checksum"),
            previous_checksum=data.get("previous_checksum"),
            details=dict(details),
            sequence=sequence,
        )


def _revision_checksum(
    *,
    container_id: str,
    config_version: str,
    revision_number: int,
    schema_version: str,
    parent_config_version: str | None,
    payload: ConfigPayload | Mapping[str, Any],
) -> str:
    payload_dict = (
        payload.to_dict()
        if isinstance(payload, ConfigPayload)
        else ConfigPayload.from_dict(payload).to_dict()
    )
    return checksum(
        {
            "container_id": container_id,
            "config_version": config_version,
            "revision_number": revision_number,
            "schema_version": schema_version,
            "parent_config_version": parent_config_version,
            "payload": payload_dict,
        }
    )


@dataclass(frozen=True)
class ConfigRevision:
    config_version: str
    container_id: str
    revision_number: int
    schema_version: str
    parent_config_version: str | None
    payload: ConfigPayload
    checksum: str
    status: str
    created_at: str
    created_by: str
    notes: str = ""

    @classmethod
    def create(
        cls,
        *,
        container_id: str,
        revision_number: int,
        parent_config_version: str | None,
        payload: ConfigPayload | Mapping[str, Any] | None = None,
        status: str = "draft",
        created_by: str = "local",
        notes: str = "",
        schema_version: str = SCHEMA_VERSION,
    ) -> ConfigRevision:
        container_id = validate_container_id(container_id)
        if not isinstance(revision_number, int) or revision_number < 1:
            raise ValidationError("revision_number must be a positive integer")
        if parent_config_version is not None:
            validate_id(parent_config_version, field="parent_config_version")
        if status not in _REVISION_STATUSES:
            raise ValidationError(f"unsupported revision status: {status!r}")
        parsed_payload = (
            ConfigPayload.empty()
            if payload is None
            else payload
            if isinstance(payload, ConfigPayload)
            else ConfigPayload.from_dict(payload)
        )
        config_version = new_id()
        digest = _revision_checksum(
            container_id=container_id,
            config_version=config_version,
            revision_number=revision_number,
            schema_version=schema_version,
            parent_config_version=parent_config_version,
            payload=parsed_payload,
        )
        return cls(
            config_version=config_version,
            container_id=container_id,
            revision_number=revision_number,
            schema_version=schema_version,
            parent_config_version=parent_config_version,
            payload=parsed_payload,
            checksum=digest,
            status=status,
            created_at=utc_now(),
            created_by=_string(created_by, "created_by"),
            notes=_string(notes, "notes", allow_empty=True),
        )

    def with_status(self, status: str) -> ConfigRevision:
        if status not in _REVISION_STATUSES:
            raise ValidationError(f"unsupported revision status: {status!r}")
        return replace(self, status=status)

    def verify(self) -> None:
        expected = _revision_checksum(
            container_id=self.container_id,
            config_version=self.config_version,
            revision_number=self.revision_number,
            schema_version=self.schema_version,
            parent_config_version=self.parent_config_version,
            payload=self.payload,
        )
        if expected != self.checksum:
            raise ValidationError(
                f"checksum mismatch for revision {self.config_version}: "
                f"expected {expected}, got {self.checksum}"
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            "config_version": self.config_version,
            "container_id": self.container_id,
            "revision_number": self.revision_number,
            "schema_version": self.schema_version,
            "parent_config_version": self.parent_config_version,
            "payload": self.payload.to_dict(),
            "checksum": self.checksum,
            "status": self.status,
            "created_at": self.created_at,
            "created_by": self.created_by,
            "notes": self.notes,
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> ConfigRevision:
        data = _mapping(value, "config_revision")
        expected = {
            "config_version",
            "container_id",
            "revision_number",
            "schema_version",
            "parent_config_version",
            "payload",
            "checksum",
            "status",
            "created_at",
            "created_by",
            "notes",
        }
        _check_unknown_keys(data, expected, "config_revision")
        _check_required_keys(data, tuple(sorted(expected)), "config_revision")
        revision_number = data["revision_number"]
        if not isinstance(revision_number, int) or revision_number < 1:
            raise ValidationError("revision_number must be a positive integer")
        revision = cls(
            config_version=validate_id(data["config_version"], field="config_version"),
            container_id=validate_container_id(data["container_id"]),
            revision_number=revision_number,
            schema_version=_string(data["schema_version"], "schema_version"),
            parent_config_version=(
                None
                if data["parent_config_version"] is None
                else validate_id(data["parent_config_version"], field="parent_config_version")
            ),
            payload=ConfigPayload.from_dict(data["payload"]),
            checksum=_string(data["checksum"], "checksum"),
            status=_string(data["status"], "status"),
            created_at=_string(data["created_at"], "created_at"),
            created_by=_string(data["created_by"], "created_by"),
            notes=_string(data["notes"], "notes", allow_empty=True),
        )
        if revision.status not in _REVISION_STATUSES:
            raise ValidationError(f"unsupported revision status: {revision.status!r}")
        revision.verify()
        return revision
