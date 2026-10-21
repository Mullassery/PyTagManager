"""Error hierarchy for the self-hosted control plane."""

from __future__ import annotations


class ControlError(Exception):
    """Base class for control-plane failures safe to surface to CLI users."""


class ValidationError(ControlError, ValueError):
    """A supplied identifier, name, payload, or document is invalid."""


class NotFoundError(ControlError, LookupError):
    """A requested organization, workspace, container, or revision does not exist."""


class ConflictError(ControlError):
    """The operation would violate identity, uniqueness, or optimistic-concurrency rules."""


class CorruptStoreError(ControlError):
    """Persisted state cannot be read safely."""


class SchemaVersionError(ControlError):
    """A document uses an unsupported or inconsistent schema version."""


class SecretError(ControlError):
    """A secret reference is malformed, unreadable, or insecurely permissioned."""
