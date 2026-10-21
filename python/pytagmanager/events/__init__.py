"""Shared event contract used by SDKs, collection, and PyTagShield adapters."""

from pytagmanager.events.contract import (
    MAX_BATCH_EVENTS,
    MAX_EVENT_BYTES,
    SCHEMA_VERSION,
    EventIssue,
    EventValidationError,
    batch_document,
    canonical_json,
    event_age_seconds,
    is_sensitive_property,
    parse_event,
    validate_batch,
    validate_event,
)

__all__ = [
    "MAX_BATCH_EVENTS",
    "MAX_EVENT_BYTES",
    "SCHEMA_VERSION",
    "EventIssue",
    "EventValidationError",
    "batch_document",
    "canonical_json",
    "event_age_seconds",
    "is_sensitive_property",
    "parse_event",
    "validate_batch",
    "validate_event",
]
