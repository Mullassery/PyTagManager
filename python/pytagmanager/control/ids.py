"""Stable identifiers and user-facing container-ID rules.

Container IDs are user-supplied, immutable, and case-insensitively unique
within an organization. They are identifiers only: a GTM-shaped value such
as ``GTM-ABC1234`` does not grant access to, or imply ownership of, that GTM
container.
"""

from __future__ import annotations

import hashlib
import re
import uuid
from datetime import datetime, timezone

from pytagmanager.control.errors import ValidationError

_UUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$"
)
_CONTAINER_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_NAME_CONTROL_RE = re.compile(r"[\x00-\x1f\x7f]")
_SLUG_RE = re.compile(r"[^a-z0-9]+")

MAX_CONTAINER_ID_LENGTH = 128
MAX_NAME_LENGTH = 200


def new_id() -> str:
    """Return a new opaque UUIDv4 identity. Never derive identity from content."""
    return str(uuid.uuid4())


def validate_id(value: str, *, field: str = "id") -> str:
    """Validate an opaque UUID used in storage paths."""
    if not isinstance(value, str) or not _UUID_RE.fullmatch(value):
        raise ValidationError(f"{field} must be a lowercase UUID, got {value!r}")
    return value


def validate_container_id(value: str) -> str:
    """Validate a user-supplied container ID without rewriting it.

    GTM-shaped IDs are allowed. The value is not a credential and is never
    used directly as a filesystem path.
    """
    if not isinstance(value, str):
        raise ValidationError(f"container_id must be a string, got {type(value).__name__}")
    if not value or len(value) > MAX_CONTAINER_ID_LENGTH:
        raise ValidationError(
            f"container_id must be 1-{MAX_CONTAINER_ID_LENGTH} characters, got {value!r}"
        )
    if not _CONTAINER_ID_RE.fullmatch(value):
        raise ValidationError(
            "container_id must start with a letter or digit and contain only "
            "letters, digits, '.', '_', ':', or '-'"
        )
    return value


def normalize_container_id(value: str) -> str:
    """Return the case-insensitive uniqueness key for a container ID."""
    return validate_container_id(value).casefold()


def validate_name(value: str, *, field: str = "name") -> str:
    """Validate a human-readable name."""
    if not isinstance(value, str):
        raise ValidationError(f"{field} must be a string, got {type(value).__name__}")
    if not value or len(value) > MAX_NAME_LENGTH:
        raise ValidationError(f"{field} must be 1-{MAX_NAME_LENGTH} characters")
    if value != value.strip():
        raise ValidationError(f"{field} must not have leading or trailing whitespace")
    if _NAME_CONTROL_RE.search(value):
        raise ValidationError(f"{field} must not contain control characters")
    return value


def container_storage_key(org_id: str, container_id: str) -> str:
    """Return a safe, stable directory name for a container.

    The raw container ID is never used as a path component, so IDs such as
    ``../escape`` cannot traverse the store even if validation changes later.
    """
    validate_id(org_id, field="org_id")
    normalized = normalize_container_id(container_id)
    digest = hashlib.sha256(f"{org_id}\0{normalized}".encode("utf-8")).hexdigest()[:24]
    slug = _SLUG_RE.sub("-", normalized).strip("-")[:32] or "container"
    return f"{slug}-{digest}"


def utc_now() -> str:
    """Return an RFC 3339 UTC timestamp with millisecond precision."""
    return (
        datetime.now(timezone.utc)
        .isoformat(timespec="milliseconds")
        .replace("+00:00", "Z")
    )
