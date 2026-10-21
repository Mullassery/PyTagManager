"""Versioned document envelopes and fail-closed schema handling."""

from __future__ import annotations

import re
from typing import Any, Mapping

from pytagmanager.control.errors import SchemaVersionError, ValidationError
from pytagmanager.control.models import SCHEMA_VERSION

CURRENT_SCHEMA_VERSION = SCHEMA_VERSION
_SCHEMA_RE = re.compile(r"^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$")

DOCUMENT_KINDS = frozenset(
    {
        "store",
        "organization",
        "workspace",
        "container",
        "environment",
        "audit_event",
        "config_revision",
        "container_export",
    }
)


def parse_schema_version(value: Any) -> tuple[int, int]:
    if not isinstance(value, str) or not _SCHEMA_RE.fullmatch(value):
        raise SchemaVersionError(f"invalid schema_version: {value!r}")
    major, minor = value.split(".", 1)
    return int(major), int(minor)


def ensure_supported_schema(value: Any) -> str:
    parsed = parse_schema_version(value)
    current = parse_schema_version(CURRENT_SCHEMA_VERSION)
    if parsed != current:
        raise SchemaVersionError(
            f"unsupported schema_version {value!r}; this build supports "
            f"{CURRENT_SCHEMA_VERSION!r}"
        )
    return CURRENT_SCHEMA_VERSION


def wrap_document(kind: str, data: Mapping[str, Any]) -> dict[str, Any]:
    if kind not in DOCUMENT_KINDS:
        raise ValidationError(f"unknown document kind: {kind!r}")
    if not isinstance(data, Mapping):
        raise ValidationError("document data must be an object")
    return {
        "schema_version": CURRENT_SCHEMA_VERSION,
        "kind": kind,
        "data": dict(data),
    }


def unwrap_document(
    document: Mapping[str, Any],
    *,
    expected_kind: str | None = None,
) -> Mapping[str, Any]:
    if not isinstance(document, Mapping):
        raise ValidationError("document must be a JSON object")
    expected_keys = {"schema_version", "kind", "data"}
    unknown = sorted(set(document) - expected_keys)
    missing = sorted(expected_keys - set(document))
    if unknown:
        raise ValidationError(f"document contains unknown field(s): {', '.join(unknown)}")
    if missing:
        raise ValidationError(f"document is missing field(s): {', '.join(missing)}")
    ensure_supported_schema(document["schema_version"])
    kind = document["kind"]
    if not isinstance(kind, str) or kind not in DOCUMENT_KINDS:
        raise ValidationError(f"unknown document kind: {kind!r}")
    if expected_kind is not None and kind != expected_kind:
        raise ValidationError(f"expected document kind {expected_kind!r}, got {kind!r}")
    data = document["data"]
    if not isinstance(data, Mapping):
        raise ValidationError("document data must be an object")
    return data


def migrate_document(document: Mapping[str, Any]) -> dict[str, Any]:
    """Migrate a stored document to the current schema, or fail closed.

    There are no older schema versions yet. The registry exists so future
    migrations are explicit, testable, and never applied implicitly during
    reads of an unknown major version.
    """
    if not isinstance(document, Mapping):
        raise ValidationError("document must be a JSON object")
    version = ensure_supported_schema(document.get("schema_version"))
    migrated = dict(document)
    migrated["schema_version"] = version
    return migrated
