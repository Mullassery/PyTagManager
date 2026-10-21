"""Transport-independent collection service.

The service validates events, applies bounded abuse controls, deduplicates
retryable event ids, and optionally forwards normalized events to PyTagShield.
It deliberately does not apply destination routing; that remains server-side
policy owned by PyTagShield.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Mapping, Protocol

from pytagmanager.control.errors import ValidationError
from pytagmanager.control.secrets import resolve_secret_ref
from pytagmanager.events import EventValidationError, parse_event, validate_batch

from .dedupe import DedupeCache, DedupeStore, SQLiteDedupeStore
from .pytagshield import ForwardResult


class Forwarder(Protocol):
    def forward(self, event: Mapping[str, Any]) -> ForwardResult: ...


@dataclass(frozen=True)
class IngestConfig:
    allowed_containers: frozenset[str] | None = None
    max_body_bytes: int = 65_536
    max_batch_events: int = 100
    dedupe_ttl_seconds: int = 86_400
    dedupe_capacity: int = 100_000
    dedupe_claim_ttl_seconds: int = 60
    dedupe_store_path: str | None = None
    rate_limit_per_minute: int = 120
    api_token_ref: str | None = None
    cors_origins: tuple[str, ...] = ("*",)
    path: str = "/api/v1/events"
    home: str | None = None

    def __post_init__(self) -> None:
        if self.max_body_bytes < 1:
            raise ValueError("max_body_bytes must be positive")
        if self.max_batch_events < 1 or self.max_batch_events > 100:
            raise ValueError("max_batch_events must be between 1 and 100")
        if self.rate_limit_per_minute < 1:
            raise ValueError("rate_limit_per_minute must be positive")
        if self.dedupe_ttl_seconds < 1:
            raise ValueError("dedupe_ttl_seconds must be positive")
        if self.dedupe_claim_ttl_seconds < 1:
            raise ValueError("dedupe_claim_ttl_seconds must be positive")
        if self.dedupe_store_path is not None and not self.dedupe_store_path:
            raise ValueError("dedupe_store_path must not be empty")
        if not self.cors_origins:
            raise ValueError("at least one CORS origin must be configured")
        if "*" in self.cors_origins and len(self.cors_origins) != 1:
            raise ValueError("wildcard CORS origin cannot be combined with named origins")
        if not self.path.startswith("/") or "?" in self.path or "#" in self.path:
            raise ValueError("collection path must be an absolute path without query/fragment")


@dataclass(frozen=True)
class IngestResult:
    status: str
    event_id: str | None
    event_name: str | None
    accepted: bool
    duplicate: bool = False
    forwarded: bool = False
    forward: dict[str, Any] | None = None
    errors: tuple[dict[str, str], ...] = field(default_factory=tuple)
    retryable: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "event_id": self.event_id,
            "event_name": self.event_name,
            "accepted": self.accepted,
            "duplicate": self.duplicate,
            "forwarded": self.forwarded,
            "forward": self.forward,
            "errors": list(self.errors),
            "retryable": self.retryable,
        }


class TokenBucketLimiter:
    def __init__(self, per_minute: int, *, capacity: int | None = None) -> None:
        self.rate = per_minute / 60.0
        self.capacity = float(capacity or per_minute)
        self._buckets: dict[str, tuple[float, float]] = {}
        self._lock = threading.Lock()

    def allow(self, key: str, *, now: float | None = None) -> bool:
        current = time.monotonic() if now is None else now
        with self._lock:
            tokens, updated = self._buckets.get(key, (self.capacity, current))
            tokens = min(self.capacity, tokens + max(0.0, current - updated) * self.rate)
            if tokens < 1.0:
                self._buckets[key] = (tokens, current)
                return False
            if len(self._buckets) > 10_000:
                self._buckets.clear()
            self._buckets[key] = (tokens - 1.0, current)
            return True


class IngestService:
    def __init__(
        self,
        config: IngestConfig | None = None,
        *,
        forwarder: Forwarder | None = None,
    ) -> None:
        self.config = config or IngestConfig()
        self.forwarder = forwarder
        self.limiter = TokenBucketLimiter(self.config.rate_limit_per_minute)
        if self.config.dedupe_store_path:
            self.dedupe: DedupeStore = SQLiteDedupeStore(
                self.config.dedupe_store_path,
                self.config.dedupe_ttl_seconds,
                self.config.dedupe_capacity,
                claim_ttl_seconds=self.config.dedupe_claim_ttl_seconds,
            )
        else:
            self.dedupe = DedupeCache(
                self.config.dedupe_ttl_seconds, self.config.dedupe_capacity
            )
        self.api_token = (
            resolve_secret_ref(self.config.api_token_ref, home=self.config.home)
            if self.config.api_token_ref
            else None
        )

    def ingest_event(
        self,
        raw: Mapping[str, Any],
        *,
        client_ip: str | None = None,
        now: datetime | None = None,
    ) -> IngestResult:
        current = now or datetime.now(timezone.utc)
        if not self.limiter.allow(client_ip or "unknown"):
            return IngestResult(
                status="rate_limited",
                event_id=None,
                event_name=None,
                accepted=False,
                retryable=True,
                errors=({"message": "rate limit exceeded"},),
            )
        try:
            event = parse_event(raw, now=current)
        except EventValidationError as exc:
            return IngestResult(
                status="rejected",
                event_id=None,
                event_name=None,
                accepted=False,
                errors=tuple(issue.to_dict() for issue in exc.issues),
            )
        return self._process_validated(event, now=current)

    def ingest_batch(
        self,
        raw: Mapping[str, Any],
        *,
        client_ip: str | None = None,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        current = now or datetime.now(timezone.utc)
        if not self.limiter.allow(client_ip or "unknown"):
            return {
                "accepted": False,
                "status": "rate_limited",
                "results": [],
                "errors": [{"message": "rate limit exceeded"}],
            }
        try:
            accepted_events, rejected_events = validate_batch(
                raw, now=current, max_events=self.config.max_batch_events
            )
        except EventValidationError as exc:
            return {
                "accepted": False,
                "status": "rejected",
                "results": [],
                "errors": [issue.to_dict() for issue in exc.issues],
            }
        results = [
            self._process_validated(event, now=current) for event in accepted_events
        ]
        rejected_by_index = {
            int(item["index"]): item for item in rejected_events
        }
        ordered: list[dict[str, Any]] = []
        accepted_index = 0
        for index in range(len(accepted_events) + len(rejected_events)):
            if index in rejected_by_index:
                item = rejected_by_index[index]
                ordered.append(
                    IngestResult(
                        status="rejected",
                        event_id=None,
                        event_name=None,
                        accepted=False,
                        errors=tuple(item["issues"]),
                    ).to_dict()
                )
            else:
                ordered.append(results[accepted_index].to_dict())
                accepted_index += 1
        has_retryable = any(item.retryable for item in results)
        has_rejected = bool(rejected_events) or any(
            item.status == "rejected" for item in results
        )
        all_accepted = not has_rejected and all(
            item.accepted or item.duplicate for item in results
        )
        if has_retryable:
            status = "partial"
        elif has_rejected:
            status = "rejected" if not results else "partial"
        elif all_accepted:
            status = "accepted"
        else:
            status = "partial"
        return {
            "accepted": all_accepted and not has_retryable,
            "status": status,
            "results": ordered,
            "errors": [],
        }

    def close(self) -> None:
        self.dedupe.close()

    def _process_validated(
        self,
        event: Mapping[str, Any],
        *,
        now: datetime,
    ) -> IngestResult:
        event_id = str(event["event_id"])
        event_name = str(event["event_name"])
        if self.config.allowed_containers is not None:
            if event["container_id"] not in self.config.allowed_containers:
                return IngestResult(
                    status="rejected",
                    event_id=event_id,
                    event_name=event_name,
                    accepted=False,
                    errors=({"message": "container is not allowed by this endpoint"},),
                )
        claim = self.dedupe.claim(event_id)
        if claim == "completed":
            return IngestResult(
                status="duplicate",
                event_id=event_id,
                event_name=event_name,
                accepted=True,
                duplicate=True,
            )
        if claim == "inflight":
            return IngestResult(
                status="in_progress",
                event_id=event_id,
                event_name=event_name,
                accepted=True,
                duplicate=True,
                retryable=True,
            )
        if self.forwarder is None:
            self.dedupe.complete(event_id)
            return IngestResult(
                status="accepted",
                event_id=event_id,
                event_name=event_name,
                accepted=True,
            )
        try:
            forwarded = self.forwarder.forward(event)
        except Exception as exc:  # pragma: no cover - defensive boundary
            self.dedupe.release(event_id)
            return IngestResult(
                status="transient_error",
                event_id=event_id,
                event_name=event_name,
                accepted=False,
                retryable=True,
                errors=({"message": f"forwarder failure: {type(exc).__name__}"},),
            )
        if forwarded.transient:
            self.dedupe.release(event_id)
            return IngestResult(
                status="transient_error",
                event_id=event_id,
                event_name=event_name,
                accepted=False,
                retryable=True,
                forwarded=forwarded.forwarded,
                forward=forwarded.to_dict(),
                errors=({"message": forwarded.error or "transient forwarding failure"},),
            )
        self.dedupe.complete(event_id)
        if not forwarded.forwarded:
            return IngestResult(
                status="rejected",
                event_id=event_id,
                event_name=event_name,
                accepted=False,
                forward=forwarded.to_dict(),
                errors=({"message": forwarded.error or "PyTagShield rejected the event"},),
            )
        return IngestResult(
            status="forwarded",
            event_id=event_id,
            event_name=event_name,
            accepted=True,
            forwarded=True,
            forward=forwarded.to_dict(),
        )
