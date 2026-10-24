"""HTTP adapter for the real PyTagShield event data plane.

Only the documented ingest endpoint is used. Configuration synchronization is
not implemented by PyTagShield 0.2.0 and is intentionally absent here.
"""

from __future__ import annotations

import ipaddress
import json
import socket
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from pytagmanager.control.errors import ValidationError
from pytagmanager.control.secrets import resolve_secret_ref

MAX_RESPONSE_BYTES = 65_536


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


@dataclass(frozen=True)
class ForwardResult:
    forwarded: bool
    http_status: int | None
    status: str
    event_id: str | None = None
    destinations: tuple[str, ...] = ()
    enqueued: tuple[str, ...] = ()
    skipped: tuple[dict[str, Any], ...] = ()
    rejected: tuple[dict[str, Any], ...] = ()
    matched_routes: tuple[str, ...] = ()
    consent: dict[str, bool] = field(default_factory=dict)
    consent_source: str | None = None
    transient: bool = False
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "forwarded": self.forwarded,
            "http_status": self.http_status,
            "status": self.status,
            "event_id": self.event_id,
            "destinations": list(self.destinations),
            "enqueued": list(self.enqueued),
            "skipped": list(self.skipped),
            "rejected": list(self.rejected),
            "matched_routes": list(self.matched_routes),
            "consent": dict(self.consent),
            "consent_source": self.consent_source,
            "transient": self.transient,
            "error": self.error,
        }


def _is_public_address(value: str) -> bool:
    try:
        address = ipaddress.ip_address(value)
    except ValueError:
        return False
    return not (
        address.is_private
        or address.is_loopback
        or address.is_link_local
        or address.is_multicast
        or address.is_reserved
        or address.is_unspecified
    )


def validate_pytagshield_url(value: str, *, allow_private_networks: bool = False) -> str:
    parsed = urllib.parse.urlsplit(value)
    if parsed.scheme not in {"https", "http"}:
        raise ValidationError("PyTagShield URL must use https (or http for a loopback test)")
    if parsed.username or parsed.password:
        raise ValidationError("PyTagShield URL must not contain credentials")
    if not parsed.hostname:
        raise ValidationError("PyTagShield URL must include a hostname")
    if parsed.scheme == "http" and not allow_private_networks:
        raise ValidationError(
            "PyTagShield URL must use HTTPS unless allow_private_networks is explicitly enabled"
        )
    if not allow_private_networks:
        try:
            addresses = {
                item[4][0]
                for item in socket.getaddrinfo(
                    parsed.hostname, parsed.port or 443, type=socket.SOCK_STREAM
                )
            }
        except OSError as exc:
            raise ValidationError(f"PyTagShield hostname cannot be resolved: {exc}") from exc
        if not addresses or any(not _is_public_address(address) for address in addresses):
            raise ValidationError(
                "PyTagShield URL resolves to a private, loopback, or reserved address; "
                "set allow_private_networks for an intentional self-hosted deployment"
            )
    return value.rstrip("/")


def to_pytagshield_event(event: Mapping[str, Any]) -> dict[str, Any]:
    """Map the canonical v1 event to PyTagShield's documented ingest shape.

    PyTagShield 0.2.0 accepts ``event``, ``distinct_id``, ``timestamp`` (Unix
    milliseconds), ``properties``, and a boolean consent map. Client-provided
    consent is forwarded as input only; PyTagShield still applies its own
    server policy and defaults to deny.
    """
    timestamp = event.get("timestamp")
    parsed = datetime.fromisoformat(str(timestamp).replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    subject = event.get("subject")
    if isinstance(subject, Mapping) and isinstance(subject.get("id"), str):
        distinct_id = subject["id"]
    else:
        # Never collapse unrelated anonymous events onto one shared identity.
        # The event id is stable across retries of the same logical event.
        distinct_id = f"anon:{event.get('event_id') or 'unknown'}"
    payload: dict[str, Any] = {
        "event": event["event_name"],
        "distinct_id": distinct_id,
        "timestamp": int(parsed.timestamp() * 1000),
        "properties": dict(event.get("properties") or {}),
    }
    consent = event.get("consent")
    if isinstance(consent, Mapping) and isinstance(consent.get("purposes"), Mapping):
        payload["consent"] = {
            purpose: bool(granted) for purpose, granted in consent["purposes"].items()
        }
    return payload


class PyTagShieldClient:
    """Bounded, non-retrying PyTagShield client.

    Retries belong at the SDK/collection boundary so the server cannot create
    a retry storm or duplicate downstream actions without an idempotency
    contract. The event id is sent as a correlation header.
    """

    def __init__(
        self,
        base_url: str,
        *,
        token_ref: str | None = None,
        home: str | None = None,
        timeout_seconds: float = 5.0,
        allow_private_networks: bool = False,
    ) -> None:
        self.base_url = validate_pytagshield_url(
            base_url, allow_private_networks=allow_private_networks
        )
        self.timeout_seconds = max(0.5, min(float(timeout_seconds), 30.0))
        self._token = resolve_secret_ref(token_ref, home=home) if token_ref else None
        self.endpoint = self.base_url + "/api/v1/event"

    def forward(self, event: Mapping[str, Any]) -> ForwardResult:
        payload = to_pytagshield_event(event)
        body = json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "pytagmanager-ingest/0.1",
            "x-pytagmanager-event-id": str(event.get("event_id", "")),
            "x-pytagmanager-event-schema": str(event.get("schema_version", "")),
        }
        if self._token:
            headers["Authorization"] = f"Bearer {self._token}"
        correlation = event.get("correlation")
        if isinstance(correlation, Mapping):
            correlation_id = correlation.get("correlation_id")
            session_id = correlation.get("session_id")
            if isinstance(correlation_id, str):
                headers["x-correlation-id"] = correlation_id
            if isinstance(session_id, str):
                headers["x-session-id"] = session_id
        request = urllib.request.Request(
            self.endpoint,
            data=body,
            headers=headers,
            method="POST",
        )
        try:
            opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), _NoRedirect())
            with opener.open(request, timeout=self.timeout_seconds) as response:
                raw = response.read(MAX_RESPONSE_BYTES + 1)
                if len(raw) > MAX_RESPONSE_BYTES:
                    return ForwardResult(
                        forwarded=False,
                        http_status=response.status,
                        status="rejected",
                        error="PyTagShield response exceeded the size limit",
                    )
                return self._parse(response.status, raw)
        except urllib.error.HTTPError as exc:
            raw = exc.read(MAX_RESPONSE_BYTES + 1) if exc.fp else b""
            transient = exc.code == 408 or exc.code == 425 or exc.code == 429 or exc.code >= 500
            return ForwardResult(
                forwarded=False,
                http_status=exc.code,
                status="transient_error" if transient else "rejected",
                transient=transient,
                error=f"PyTagShield HTTP {exc.code}",
            )
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            return ForwardResult(
                forwarded=False,
                http_status=None,
                status="transient_error",
                transient=True,
                error=f"PyTagShield request failed: {type(exc).__name__}",
            )

    def _parse(self, http_status: int, raw: bytes) -> ForwardResult:
        if not raw:
            return ForwardResult(
                forwarded=False,
                http_status=http_status,
                status="rejected",
                error="PyTagShield returned an empty response",
            )
        try:
            document = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return ForwardResult(
                forwarded=False,
                http_status=http_status,
                status="rejected",
                error="PyTagShield returned non-JSON output",
            )
        if not isinstance(document, Mapping):
            return ForwardResult(
                forwarded=False,
                http_status=http_status,
                status="rejected",
                error="PyTagShield returned a non-object response",
            )
        status = document.get("status")
        if status not in {"accepted", "partially_accepted", "backpressure", "rejected"}:
            return ForwardResult(
                forwarded=False,
                http_status=http_status,
                status="rejected",
                error="PyTagShield returned an unexpected ingest status",
            )
        consent = document.get("consent")
        if not isinstance(consent, Mapping):
            consent = {}
        return ForwardResult(
            forwarded=status in {"accepted", "partially_accepted"},
            http_status=http_status,
            status=status,
            transient=status == "backpressure",
            event_id=(
                document.get("event_id") if isinstance(document.get("event_id"), str) else None
            ),
            destinations=tuple(
                item for item in document.get("destinations", []) if isinstance(item, str)
            ),
            enqueued=tuple(item for item in document.get("enqueued", []) if isinstance(item, str)),
            skipped=tuple(
                dict(item) for item in document.get("skipped", []) if isinstance(item, Mapping)
            ),
            rejected=tuple(
                dict(item) for item in document.get("rejected", []) if isinstance(item, Mapping)
            ),
            matched_routes=tuple(
                item for item in document.get("matched_routes", []) if isinstance(item, str)
            ),
            consent={key: bool(value) for key, value in consent.items() if isinstance(value, bool)},
            consent_source=(
                str(document["consent_source"])
                if isinstance(document.get("consent_source"), str)
                else None
            ),
        )
