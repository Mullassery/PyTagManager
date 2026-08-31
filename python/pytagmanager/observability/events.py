"""Normalized tracking-event model shared by every layer of the Tracking
Observability capability (docs/ARCHITECTURE.md).

Every collector -- the browser agent's telemetry (`session.py`), network
sniffing, GTM/GA4 API lookups -- normalizes its raw signal into a
`TrackingEvent` rather than exposing its own shape, so
`pytagmanager.correlation.journey` and `pytagmanager.diagnostics.rules` have
one common currency to reason about regardless of where an observation
originated.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

# Where an observation originated (spec: browser / DOM / mutation observer /
# dataLayer / GTM / network / JS runtime / consent management platform).
SOURCES = frozenset(
    {
        "browser",
        "dom",
        "mutation_observer",
        "datalayer",
        "gtm",
        "network",
        "javascript",
        "consent",
        "application_api",
        "visibility",
    }
)

# What kind of thing was observed.
EVENT_TYPES = frozenset(
    {
        "click",
        "form_submit",
        "change",
        "dom_insert",
        "dom_remove",
        "mutation",
        "datalayer_push",
        "gtm_event",
        "tag_execution",
        "network_request",
        "route_change",
        "js_error",
        "consent_change",
        "api_call",
        "visibility",
    }
)

# Substrings (checked against lowercased payload keys) redacted before a
# TrackingEvent is ever constructed or persisted -- see docs/ARCHITECTURE.md's
# privacy section. This is a denylist, not a guarantee: callers that observe
# raw form contents or full request bodies must not hand them to
# `payload`/`metadata` in the first place.
_SENSITIVE_KEY_MARKERS = (
    "password",
    "passwd",
    "token",
    "secret",
    "authorization",
    "auth",
    "credit_card",
    "card_number",
    "cvv",
    "cvc",
    "ssn",
    "api_key",
)
_REDACTED = "[REDACTED]"


def redact_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Return a shallow copy of `payload` with values whose key looks
    sensitive replaced by a redaction marker. Applied by every collector
    before a raw browser/network payload becomes part of a `TrackingEvent`.
    """
    redacted: Dict[str, Any] = {}
    for key, value in payload.items():
        key_lower = str(key).lower()
        if any(marker in key_lower for marker in _SENSITIVE_KEY_MARKERS):
            redacted[key] = _REDACTED
        elif isinstance(value, dict):
            redacted[key] = redact_payload(value)
        else:
            redacted[key] = value
    return redacted


@dataclass(frozen=True)
class TrackingEvent:
    """A single normalized observation from anywhere in the tracking chain:
    a browser interaction, a DOM mutation, a dataLayer push, GTM tag
    execution, or an analytics network request.
    """

    id: str
    timestamp: float  # unix epoch seconds
    source: str  # one of SOURCES
    event_type: str  # one of EVENT_TYPES
    event_name: str = ""  # e.g. "add_to_cart"; "" when not applicable (a raw click)
    page_url: str = ""
    selector: Optional[str] = None
    payload: Dict[str, Any] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def create(
        cls,
        *,
        source: str,
        event_type: str,
        event_name: str = "",
        page_url: str = "",
        selector: Optional[str] = None,
        payload: Optional[Dict[str, Any]] = None,
        metadata: Optional[Dict[str, Any]] = None,
        timestamp: Optional[float] = None,
    ) -> "TrackingEvent":
        return cls(
            id=str(uuid.uuid4()),
            timestamp=timestamp if timestamp is not None else time.time(),
            source=source,
            event_type=event_type,
            event_name=event_name,
            page_url=page_url,
            selector=selector,
            payload=redact_payload(dict(payload or {})),
            metadata=dict(metadata or {}),
        )

    @classmethod
    def from_dict(cls, data: dict) -> "TrackingEvent":
        return cls(
            id=data["id"],
            timestamp=float(data["timestamp"]),
            source=data["source"],
            event_type=data["event_type"],
            event_name=data.get("event_name", ""),
            page_url=data.get("page_url", ""),
            selector=data.get("selector"),
            payload=dict(data.get("payload", {})),
            metadata=dict(data.get("metadata", {})),
        )
