"""Canonical cross-platform event contract, validation, and normalization.

This module intentionally uses only the Python standard library so the
collection service can be deployed without extra packages. The same contract
is documented in ``schemas/events/v1/`` and implemented by the Web, Android,
and iOS SDKs.
"""

from __future__ import annotations

import copy
import json
import math
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable, Mapping

SCHEMA_VERSION = "1.0"
MAX_EVENT_BYTES = 32_768
MAX_BATCH_EVENTS = 100
MAX_PROPERTIES = 100
MAX_PROPERTY_DEPTH = 5
MAX_PROPERTY_STRING = 2_048
MAX_ARRAY_ITEMS = 100
MAX_OBJECT_KEYS = 50
MAX_NAME_LENGTH = 80
MAX_PROPERTY_KEY_LENGTH = 64
MAX_SUBJECT_LENGTH = 128
MAX_CORRELATION_LENGTH = 128
MAX_CONSENT_PURPOSES = 32

PLATFORMS = frozenset({"web", "android", "ios", "server"})
CONSENT_SOURCES = frozenset({"sdk", "host", "server", "unknown"})
CONSENT_PROVENANCE = frozenset({"explicit", "default", "stored", "unknown"})
TOP_LEVEL_FIELDS = frozenset(
    {
        "schema_version",
        "event_id",
        "event_name",
        "timestamp",
        "source",
        "container_id",
        "config_version",
        "subject",
        "consent",
        "correlation",
        "properties",
    }
)
SOURCE_FIELDS = frozenset({"platform", "sdk_name", "sdk_version", "app_version"})
SUBJECT_FIELDS = frozenset({"id", "type"})
CONSENT_FIELDS = frozenset({"purposes", "source", "provenance", "updated_at"})
CORRELATION_FIELDS = frozenset({"correlation_id", "session_id"})
REQUIRED_FIELDS = (
    "schema_version",
    "event_id",
    "event_name",
    "timestamp",
    "source",
    "container_id",
    "properties",
)

_EVENT_ID_RE = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-"
    r"[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
)
_EVENT_NAME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_.-]{0,79}$")
_CONTAINER_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$")
_CONFIG_VERSION_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$")
_SDK_NAME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_.-]{0,63}$")
_SDK_VERSION_RE = re.compile(r"^[0-9]+\.[0-9]+\.[0-9]+(?:[-+][A-Za-z0-9.-]+)?$")
_APP_VERSION_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.+-]{0,63}$")
_PROPERTY_KEY_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_.-]{0,63}$")
_PURPOSE_RE = re.compile(r"^[a-z][a-z0-9_-]{0,63}$")
_TIMESTAMP_RE = re.compile(
    r"^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):(\d{2})(?:\.(\d{1,3}))?Z$"
)
_SAFE_ID_RE = re.compile(r"^[^\x00-\x1f\x7f]+$")

_SENSITIVE_TOKENS = frozenset(
    {
        "password",
        "passwd",
        "passphrase",
        "secret",
        "token",
        "apikey",
        "credential",
        "credentials",
        "cvv",
        "cvc",
        "pin",
        "ssn",
        "socialsecurity",
        "email",
        "phone",
        "phonenumber",
        "address",
        "street",
        "postalcode",
        "zip",
        "iban",
        "accountnumber",
        "routingnumber",
        "taxid",
        "nationalid",
        "passport",
        "dob",
        "birthdate",
        "ip",
        "ipaddress",
        "latitude",
        "longitude",
        "geolocation",
        "cardnumber",
        "creditcard",
        "creditcardnumber",
        "securitycode",
        "routing",
    }
)
_SENSITIVE_PHRASES = frozenset(
    {
        "creditcard",
        "creditcardnumber",
        "cardnumber",
        "securitycode",
        "socialsecurity",
        "socialsecuritynumber",
        "phonenumber",
        "postalcode",
        "ipaddress",
        "dateofbirth",
        "bankaccount",
        "accountnumber",
        "routingnumber",
        "nationalid",
        "taxid",
        "passportnumber",
    }
)
_HASH_MARKERS = frozenset({"hash", "hashed", "sha256", "sha512", "hmac", "digest"})


@dataclass(frozen=True)
class EventIssue:
    code: str
    field: str
    message: str

    def to_dict(self) -> dict[str, str]:
        return {"code": self.code, "field": self.field, "message": self.message}


class EventValidationError(ValueError):
    """Raised when an event cannot be accepted under the v1 contract."""

    def __init__(self, issues: Iterable[EventIssue]) -> None:
        self.issues = tuple(issues)
        message = "; ".join(
            f"{issue.field}: {issue.message}" for issue in self.issues
        ) or "invalid event"
        super().__init__(message)

    def to_dict(self) -> dict[str, Any]:
        return {
            "error": "invalid_event",
            "schema_version": SCHEMA_VERSION,
            "issues": [issue.to_dict() for issue in self.issues],
        }


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def is_sensitive_property(key: str) -> bool:
    """Return True for property names that must not be collected by default.

    Values whose key is explicitly marked as a hash/digest (for example
    ``email_sha256`` or ``hashed_email``) are allowed because they are not
    raw personal data. This is a denylist, not a guarantee that a property is
    non-identifying.
    """
    tokens = re.findall(r"[a-z0-9]+", key.lower())
    if not tokens:
        return False
    normalized = "".join(tokens)
    if any(phrase in normalized for phrase in _SENSITIVE_PHRASES):
        if tokens[0] in _HASH_MARKERS or tokens[-1] in _HASH_MARKERS:
            return False
        return True
    sensitive = any(token in _SENSITIVE_TOKENS for token in tokens)
    if not sensitive:
        return False
    return not (tokens[0] in _HASH_MARKERS or tokens[-1] in _HASH_MARKERS)


def _parse_timestamp(value: Any) -> datetime | None:
    if not isinstance(value, str):
        return None
    match = _TIMESTAMP_RE.fullmatch(value)
    if match is None:
        return None
    year, month, day, hour, minute, second, millis = match.groups()
    try:
        return datetime(
            int(year),
            int(month),
            int(day),
            int(hour),
            int(minute),
            int(second),
            int((millis or "0").ljust(3, "0")) * 1000,
            tzinfo=timezone.utc,
        )
    except ValueError:
        return None


def _format_timestamp(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat(timespec="milliseconds").replace(
        "+00:00", "Z"
    )


def _is_number(value: Any) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(value)
    )


def _has_control(value: str, *, allow_whitespace: bool = False) -> bool:
    for char in value:
        if char in "\t\r\n" and allow_whitespace:
            continue
        if ord(char) < 0x20 or ord(char) == 0x7F:
            return True
    return False


def _check_string(
    value: Any,
    field: str,
    issues: list[EventIssue],
    *,
    max_length: int,
    pattern: re.Pattern[str] | None = None,
    allow_whitespace: bool = True,
    required: bool = True,
) -> bool:
    if value is None and not required:
        return True
    if not isinstance(value, str):
        issues.append(EventIssue("invalid_type", field, "must be a string"))
        return False
    if required and not value:
        issues.append(EventIssue("required", field, "must not be empty"))
        return False
    if len(value) > max_length:
        issues.append(
            EventIssue("too_long", field, f"must be at most {max_length} characters")
        )
        return False
    if _has_control(value, allow_whitespace=allow_whitespace):
        issues.append(EventIssue("invalid_characters", field, "must not contain control characters"))
        return False
    if pattern is not None and not pattern.fullmatch(value):
        issues.append(EventIssue("invalid_format", field, "has an invalid format"))
        return False
    return True


def _validate_properties(
    value: Any,
    field: str,
    issues: list[EventIssue],
    *,
    depth: int = 0,
    seen_depth: int = 0,
) -> None:
    if seen_depth > MAX_PROPERTY_DEPTH:
        issues.append(
            EventIssue(
                "too_deep",
                field,
                f"must not exceed {MAX_PROPERTY_DEPTH} nested levels",
            )
        )
        return
    if value is None or isinstance(value, bool):
        return
    if isinstance(value, str):
        if len(value) > MAX_PROPERTY_STRING:
            issues.append(
                EventIssue(
                    "too_long",
                    field,
                    f"string values must be at most {MAX_PROPERTY_STRING} characters",
                )
            )
        if _has_control(value, allow_whitespace=True):
            issues.append(
                EventIssue("invalid_characters", field, "must not contain control characters")
            )
        return
    if _is_number(value):
        return
    if isinstance(value, (list, tuple)):
        if len(value) > MAX_ARRAY_ITEMS:
            issues.append(
                EventIssue("too_many_items", field, f"must have at most {MAX_ARRAY_ITEMS} items")
            )
        for index, item in enumerate(value):
            _validate_properties(
                item,
                f"{field}[{index}]",
                issues,
                depth=depth,
                seen_depth=seen_depth + 1,
            )
        return
    if isinstance(value, Mapping):
        if len(value) > MAX_OBJECT_KEYS:
            issues.append(
                EventIssue("too_many_keys", field, f"must have at most {MAX_OBJECT_KEYS} keys")
            )
        for key, item in value.items():
            if not isinstance(key, str):
                issues.append(EventIssue("invalid_key", field, "object keys must be strings"))
                continue
            child = f"{field}.{key}" if field else key
            if not _PROPERTY_KEY_RE.fullmatch(key):
                issues.append(
                    EventIssue(
                        "invalid_key",
                        child,
                        "property keys must match ^[A-Za-z][A-Za-z0-9_.-]{0,63}$",
                    )
                )
            elif is_sensitive_property(key):
                issues.append(
                    EventIssue(
                        "sensitive_property",
                        child,
                        "sensitive property names are prohibited by the v1 contract",
                    )
                )
            _validate_properties(
                item,
                child,
                issues,
                depth=depth,
                seen_depth=seen_depth + 1,
            )
        return
    issues.append(
        EventIssue(
            "invalid_type",
            field,
            "must be a JSON string, number, boolean, null, array, or object",
        )
    )


def validate_event(
    raw: Any,
    *,
    now: datetime | None = None,
    max_skew_seconds: int | None = 86_400,
    max_bytes: int = MAX_EVENT_BYTES,
) -> list[EventIssue]:
    """Validate a raw event against the v1 contract.

    Unknown fields are rejected. ``max_skew_seconds=None`` disables the
    clock-skew check (useful for deterministic fixture validation).
    """
    issues: list[EventIssue] = []
    if not isinstance(raw, Mapping):
        return [EventIssue("invalid_type", "$", "event must be a JSON object")]

    try:
        serialized = canonical_json(raw)
        if len(serialized.encode("utf-8")) > max_bytes:
            issues.append(
                EventIssue("too_large", "$", f"event must be at most {max_bytes} bytes")
            )
    except (TypeError, ValueError):
        issues.append(EventIssue("invalid_json", "$", "event must be JSON-serializable"))

    unknown = sorted(set(raw) - TOP_LEVEL_FIELDS)
    if unknown:
        issues.append(
            EventIssue(
                "unknown_field",
                "$",
                f"contains unknown field(s): {', '.join(unknown)}",
            )
        )
    missing = [field for field in REQUIRED_FIELDS if field not in raw]
    for field in missing:
        issues.append(EventIssue("required", field, "is required"))

    if "schema_version" in raw:
        if raw.get("schema_version") != SCHEMA_VERSION:
            issues.append(
                EventIssue(
                    "unsupported_schema",
                    "schema_version",
                    f"must be {SCHEMA_VERSION!r}",
                )
            )

    if "event_id" in raw:
        _check_string(
            raw.get("event_id"),
            "event_id",
            issues,
            max_length=36,
            pattern=_EVENT_ID_RE,
            allow_whitespace=False,
        )
    if "event_name" in raw:
        _check_string(
            raw.get("event_name"),
            "event_name",
            issues,
            max_length=MAX_NAME_LENGTH,
            pattern=_EVENT_NAME_RE,
            allow_whitespace=False,
        )

    if "timestamp" in raw:
        parsed = _parse_timestamp(raw.get("timestamp"))
        if parsed is None:
            issues.append(
                EventIssue(
                    "invalid_timestamp",
                    "timestamp",
                    "must be an RFC 3339 UTC timestamp ending in Z",
                )
            )
        elif max_skew_seconds is not None:
            current = now or datetime.now(timezone.utc)
            if current.tzinfo is None:
                current = current.replace(tzinfo=timezone.utc)
            skew = abs((current - parsed).total_seconds())
            if skew > max_skew_seconds:
                issues.append(
                    EventIssue(
                        "timestamp_skew",
                        "timestamp",
                        f"is outside the allowed {max_skew_seconds}-second clock-skew window",
                    )
                )

    if "source" in raw:
        source = raw.get("source")
        if not isinstance(source, Mapping):
            issues.append(EventIssue("invalid_type", "source", "must be an object"))
        else:
            unknown_source = sorted(set(source) - SOURCE_FIELDS)
            if unknown_source:
                issues.append(
                    EventIssue(
                        "unknown_field",
                        "source",
                        f"contains unknown field(s): {', '.join(unknown_source)}",
                    )
                )
            for field in ("platform", "sdk_name", "sdk_version"):
                if field not in source:
                    issues.append(
                        EventIssue("required", f"source.{field}", "is required")
                    )
            platform = source.get("platform")
            if platform not in PLATFORMS:
                issues.append(
                    EventIssue(
                        "invalid_platform",
                        "source.platform",
                        f"must be one of: {', '.join(sorted(PLATFORMS))}",
                    )
                )
            _check_string(
                source.get("sdk_name"),
                "source.sdk_name",
                issues,
                max_length=64,
                pattern=_SDK_NAME_RE,
                allow_whitespace=False,
            )
            _check_string(
                source.get("sdk_version"),
                "source.sdk_version",
                issues,
                max_length=32,
                pattern=_SDK_VERSION_RE,
                allow_whitespace=False,
            )
            if "app_version" in source:
                _check_string(
                    source.get("app_version"),
                    "source.app_version",
                    issues,
                    max_length=64,
                    pattern=_APP_VERSION_RE,
                    allow_whitespace=False,
                )

    if "container_id" in raw:
        _check_string(
            raw.get("container_id"),
            "container_id",
            issues,
            max_length=128,
            pattern=_CONTAINER_RE,
            allow_whitespace=False,
        )

    if "config_version" in raw and raw.get("config_version") is not None:
        _check_string(
            raw.get("config_version"),
            "config_version",
            issues,
            max_length=128,
            pattern=_CONFIG_VERSION_RE,
            allow_whitespace=False,
        )

    if "subject" in raw and raw.get("subject") is not None:
        subject = raw.get("subject")
        if not isinstance(subject, Mapping):
            issues.append(EventIssue("invalid_type", "subject", "must be an object"))
        else:
            unknown_subject = sorted(set(subject) - SUBJECT_FIELDS)
            if unknown_subject:
                issues.append(
                    EventIssue(
                        "unknown_field",
                        "subject",
                        f"contains unknown field(s): {', '.join(unknown_subject)}",
                    )
                )
            if "id" not in subject:
                issues.append(EventIssue("required", "subject.id", "is required"))
            if "type" not in subject:
                issues.append(EventIssue("required", "subject.type", "is required"))
            _check_string(
                subject.get("id"),
                "subject.id",
                issues,
                max_length=MAX_SUBJECT_LENGTH,
                pattern=_SAFE_ID_RE,
                allow_whitespace=True,
            )
            if subject.get("type") not in {"user", "anonymous"}:
                issues.append(
                    EventIssue(
                        "invalid_subject_type",
                        "subject.type",
                        "must be 'user' or 'anonymous'",
                    )
                )

    if "consent" in raw and raw.get("consent") is not None:
        consent = raw.get("consent")
        if not isinstance(consent, Mapping):
            issues.append(EventIssue("invalid_type", "consent", "must be an object"))
        else:
            unknown_consent = sorted(set(consent) - CONSENT_FIELDS)
            if unknown_consent:
                issues.append(
                    EventIssue(
                        "unknown_field",
                        "consent",
                        f"contains unknown field(s): {', '.join(unknown_consent)}",
                    )
                )
            for field in ("purposes", "source", "provenance"):
                if field not in consent:
                    issues.append(
                        EventIssue("required", f"consent.{field}", "is required")
                    )
            purposes = consent.get("purposes")
            if not isinstance(purposes, Mapping) or not purposes:
                issues.append(
                    EventIssue(
                        "invalid_consent",
                        "consent.purposes",
                        "must be a non-empty object mapping purposes to booleans",
                    )
                )
            else:
                if len(purposes) > MAX_CONSENT_PURPOSES:
                    issues.append(
                        EventIssue(
                            "too_many_purposes",
                            "consent.purposes",
                            f"must have at most {MAX_CONSENT_PURPOSES} purposes",
                        )
                    )
                for purpose, granted in purposes.items():
                    field = f"consent.purposes.{purpose}"
                    if not isinstance(purpose, str) or not _PURPOSE_RE.fullmatch(purpose):
                        issues.append(
                            EventIssue(
                                "invalid_purpose",
                                field,
                                "purpose must match ^[a-z][a-z0-9_-]{0,63}$",
                            )
                        )
                    if not isinstance(granted, bool):
                        issues.append(
                            EventIssue(
                                "invalid_consent",
                                field,
                                "must be true or false",
                            )
                        )
            if consent.get("source") not in CONSENT_SOURCES:
                issues.append(
                    EventIssue(
                        "invalid_consent_source",
                        "consent.source",
                        f"must be one of: {', '.join(sorted(CONSENT_SOURCES))}",
                    )
                )
            if consent.get("provenance") not in CONSENT_PROVENANCE:
                issues.append(
                    EventIssue(
                        "invalid_consent_provenance",
                        "consent.provenance",
                        f"must be one of: {', '.join(sorted(CONSENT_PROVENANCE))}",
                    )
                )
            updated_at = consent.get("updated_at")
            if updated_at is not None and _parse_timestamp(updated_at) is None:
                issues.append(
                    EventIssue(
                        "invalid_timestamp",
                        "consent.updated_at",
                        "must be an RFC 3339 UTC timestamp ending in Z",
                    )
                )

    if "correlation" in raw and raw.get("correlation") is not None:
        correlation = raw.get("correlation")
        if not isinstance(correlation, Mapping):
            issues.append(EventIssue("invalid_type", "correlation", "must be an object"))
        else:
            unknown_correlation = sorted(set(correlation) - CORRELATION_FIELDS)
            if unknown_correlation:
                issues.append(
                    EventIssue(
                        "unknown_field",
                        "correlation",
                        f"contains unknown field(s): {', '.join(unknown_correlation)}",
                    )
                )
            for field in ("correlation_id", "session_id"):
                if field in correlation:
                    _check_string(
                        correlation.get(field),
                        f"correlation.{field}",
                        issues,
                        max_length=MAX_CORRELATION_LENGTH,
                        allow_whitespace=True,
                    )

    if "properties" in raw:
        properties = raw.get("properties")
        if not isinstance(properties, Mapping):
            issues.append(EventIssue("invalid_type", "properties", "must be an object"))
        else:
            if len(properties) > MAX_PROPERTIES:
                issues.append(
                    EventIssue(
                        "too_many_properties",
                        "properties",
                        f"must have at most {MAX_PROPERTIES} keys",
                    )
                )
            for key, value in properties.items():
                child = f"properties.{key}"
                if not isinstance(key, str):
                    issues.append(
                        EventIssue("invalid_key", "properties", "keys must be strings")
                    )
                    continue
                if not _PROPERTY_KEY_RE.fullmatch(key):
                    issues.append(
                        EventIssue(
                            "invalid_key",
                            child,
                            "property keys must match ^[A-Za-z][A-Za-z0-9_.-]{0,63}$",
                        )
                    )
                    continue
                if is_sensitive_property(key):
                    issues.append(
                        EventIssue(
                            "sensitive_property",
                            child,
                            "sensitive property names are prohibited by the v1 contract",
                        )
                    )
                _validate_properties(value, child, issues)
    return issues


def parse_event(
    raw: Any,
    *,
    now: datetime | None = None,
    max_skew_seconds: int | None = 86_400,
    max_bytes: int = MAX_EVENT_BYTES,
) -> dict[str, Any]:
    issues = validate_event(
        raw,
        now=now,
        max_skew_seconds=max_skew_seconds,
        max_bytes=max_bytes,
    )
    if issues:
        raise EventValidationError(issues)
    normalized = {
        "schema_version": SCHEMA_VERSION,
        "event_id": raw["event_id"],
        "event_name": raw["event_name"],
        "timestamp": _format_timestamp(_parse_timestamp(raw["timestamp"])),
        "source": {
            key: raw["source"][key]
            for key in ("platform", "sdk_name", "sdk_version", "app_version")
            if key in raw["source"]
        },
        "container_id": raw["container_id"],
    }
    if "config_version" in raw:
        normalized["config_version"] = raw["config_version"]
    if "subject" in raw and raw["subject"] is not None:
        normalized["subject"] = {
            "id": raw["subject"]["id"],
            "type": raw["subject"]["type"],
        }
    if "consent" in raw and raw["consent"] is not None:
        consent = {
            "purposes": {
                purpose: bool(granted)
                for purpose, granted in sorted(raw["consent"]["purposes"].items())
            },
            "source": raw["consent"]["source"],
            "provenance": raw["consent"]["provenance"],
        }
        updated_at = raw["consent"].get("updated_at")
        if updated_at is not None:
            consent["updated_at"] = _format_timestamp(_parse_timestamp(updated_at))
        normalized["consent"] = consent
    if "correlation" in raw and raw["correlation"] is not None:
        normalized["correlation"] = {
            key: raw["correlation"][key]
            for key in ("correlation_id", "session_id")
            if key in raw["correlation"]
        }
    normalized["properties"] = copy.deepcopy(dict(raw["properties"]))
    return normalized


def validate_batch(
    raw: Any,
    *,
    now: datetime | None = None,
    max_skew_seconds: int | None = 86_400,
    max_bytes: int = MAX_EVENT_BYTES,
    max_events: int = MAX_BATCH_EVENTS,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Validate a batch envelope.

    Returns ``(accepted, rejected)`` where rejected entries include the event
    index and the structured validation issues. A malformed envelope raises
    :class:`EventValidationError`.
    """
    if not isinstance(raw, Mapping):
        raise EventValidationError(
            [EventIssue("invalid_type", "$", "batch must be a JSON object")]
        )
    unknown = sorted(set(raw) - {"schema_version", "events"})
    if unknown:
        raise EventValidationError(
            [
                EventIssue(
                    "unknown_field",
                    "$",
                    f"contains unknown field(s): {', '.join(unknown)}",
                )
            ]
        )
    if raw.get("schema_version") != SCHEMA_VERSION:
        raise EventValidationError(
            [
                EventIssue(
                    "unsupported_schema",
                    "schema_version",
                    f"must be {SCHEMA_VERSION!r}",
                )
            ]
        )
    events = raw.get("events")
    if not isinstance(events, list) or not events:
        raise EventValidationError(
            [EventIssue("invalid_batch", "events", "must be a non-empty array")]
        )
    if len(events) > max_events:
        raise EventValidationError(
            [
                EventIssue(
                    "too_many_events",
                    "events",
                    f"must have at most {max_events} events",
                )
            ]
        )
    accepted = []
    rejected = []
    for index, event in enumerate(events):
        try:
            accepted.append(
                parse_event(
                    event,
                    now=now,
                    max_skew_seconds=max_skew_seconds,
                    max_bytes=max_bytes,
                )
            )
        except EventValidationError as exc:
            rejected.append(
                {
                    "index": index,
                    "issues": [issue.to_dict() for issue in exc.issues],
                }
            )
    return accepted, rejected


def batch_document(events: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    return {"schema_version": SCHEMA_VERSION, "events": list(events)}


def event_age_seconds(event: Mapping[str, Any], *, now: datetime | None = None) -> float:
    parsed = _parse_timestamp(event.get("timestamp"))
    if parsed is None:
        return 0.0
    current = now or datetime.now(timezone.utc)
    return abs((current - parsed).total_seconds())
