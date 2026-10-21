"""Adapter contracts for draft/export previews. No adapter sends traffic."""

from __future__ import annotations

import copy
from dataclasses import dataclass
from typing import Any, Mapping
from urllib.parse import urlparse

from pytagmanager.control.config import Destination, Tag
from pytagmanager.control.errors import ValidationError


@dataclass(frozen=True)
class AdapterCapabilities:
    export: bool
    browser: bool
    server: bool

    def to_dict(self) -> dict[str, bool]:
        return {
            "export": self.export,
            "browser": self.browser,
            "server": self.server,
        }


@dataclass(frozen=True)
class AdapterIssue:
    severity: str
    code: str
    message: str

    def to_dict(self) -> dict[str, str]:
        return {"severity": self.severity, "code": self.code, "message": self.message}


@dataclass(frozen=True)
class AdapterBuildResult:
    adapter: str
    destination_id: str | None
    payload: dict[str, Any] | None
    secret_refs: dict[str, str]
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "simulation": True,
            "would_send": False,
            "adapter": self.adapter,
            "capability": "export",
            "destination_id": self.destination_id,
            "payload": copy.deepcopy(self.payload),
            "secret_refs": dict(self.secret_refs),
            "error": self.error,
        }


def _event_name(tag: Tag) -> str | None:
    raw = tag.parameters.get("event_name", tag.parameters.get("eventName"))
    if isinstance(raw, str) and raw:
        return raw
    return None


def _referenced_destinations(
    tag: Tag,
    destinations: tuple[Destination, ...],
    kind: str,
) -> tuple[list[Destination], list[AdapterIssue]]:
    by_id = {destination.destination_id: destination for destination in destinations}
    issues = []
    selected = []
    for destination_id in tag.destination_ids:
        destination = by_id.get(destination_id)
        if destination is None:
            issues.append(
                AdapterIssue("error", "destination_missing", f"destination {destination_id} does not exist")
            )
            continue
        if destination.kind != kind:
            issues.append(
                AdapterIssue(
                    "error",
                    "destination_kind_mismatch",
                    f"destination {destination.name!r} has kind {destination.kind!r}, expected {kind!r}",
                )
            )
            continue
        if not destination.enabled:
            issues.append(
                AdapterIssue(
                    "warning",
                    "destination_disabled",
                    f"destination {destination.name!r} is disabled",
                )
            )
            continue
        selected.append(destination)
    if not tag.destination_ids:
        selected = [
            destination
            for destination in destinations
            if destination.kind == kind and destination.enabled
        ]
        if not selected:
            issues.append(
                AdapterIssue(
                    "warning",
                    "destination_not_configured",
                    f"no enabled {kind!r} destination is available; preview cannot build a payload",
                )
            )
        else:
            issues.append(
                AdapterIssue(
                    "warning",
                    "destination_implicit",
                    f"tag has no destination_ids; preview uses the first enabled {kind!r} destination",
                )
            )
    return selected, issues


class Adapter:
    key = ""
    destination_kind = ""
    capabilities = AdapterCapabilities(export=True, browser=False, server=False)

    def validate_destination(self, destination: Destination) -> list[AdapterIssue]:
        return []

    def validate_tag(
        self,
        tag: Tag,
        destinations: tuple[Destination, ...],
    ) -> list[AdapterIssue]:
        issues = []
        if _event_name(tag) is None:
            issues.append(
                AdapterIssue(
                    "error",
                    "event_name_required",
                    "tag.parameters.event_name must be a non-empty string",
                )
            )
        selected, destination_issues = _referenced_destinations(tag, destinations, self.destination_kind)
        issues.extend(destination_issues)
        for destination in selected:
            issues.extend(self.validate_destination(destination))
        return issues

    def build(
        self,
        tag: Tag,
        destinations: tuple[Destination, ...],
        variables: Mapping[str, Any],
        event: Mapping[str, Any],
    ) -> AdapterBuildResult:
        selected, issues = _referenced_destinations(tag, destinations, self.destination_kind)
        errors = [issue for issue in issues if issue.severity == "error"]
        if errors:
            return AdapterBuildResult(
                adapter=self.key,
                destination_id=None,
                payload=None,
                secret_refs={},
                error="; ".join(issue.message for issue in errors),
            )
        if not selected:
            return AdapterBuildResult(
                adapter=self.key,
                destination_id=None,
                payload=None,
                secret_refs={},
                error=f"no enabled {self.destination_kind!r} destination",
            )
        destination = selected[0]
        payload, secret_refs, error = self._build_payload(tag, destination, variables, event)
        return AdapterBuildResult(
            adapter=self.key,
            destination_id=destination.destination_id,
            payload=payload,
            secret_refs=secret_refs,
            error=error,
        )

    def _build_payload(
        self,
        tag: Tag,
        destination: Destination,
        variables: Mapping[str, Any],
        event: Mapping[str, Any],
    ) -> tuple[dict[str, Any] | None, dict[str, str], str | None]:
        raise NotImplementedError


class GA4Adapter(Adapter):
    key = "ga4_event"
    destination_kind = "ga4"

    def validate_destination(self, destination: Destination) -> list[AdapterIssue]:
        measurement_id = destination.config.get("measurement_id")
        if not isinstance(measurement_id, str) or not measurement_id:
            return [
                AdapterIssue(
                    "error",
                    "measurement_id_required",
                    "GA4 destination config.measurement_id must be a non-empty string",
                )
            ]
        return []

    def _build_payload(self, tag, destination, variables, event):
        event_name = _event_name(tag)
        params = tag.parameters.get("parameters", {})
        if not isinstance(params, Mapping):
            return None, {}, "tag.parameters.parameters must be an object"
        payload = {
            "measurement_id": destination.config["measurement_id"],
            "event_name": event_name,
            "parameters": copy.deepcopy(dict(params)),
            "variables": copy.deepcopy(dict(variables)),
        }
        return payload, dict(destination.secret_refs), None


class SegmentAdapter(Adapter):
    key = "segment_track"
    destination_kind = "segment"

    def validate_destination(self, destination: Destination) -> list[AdapterIssue]:
        issues = []
        if "write_key" not in destination.secret_refs:
            issues.append(
                AdapterIssue(
                    "warning",
                    "write_key_missing",
                    "Segment destination should provide secret_refs.write_key",
                )
            )
        return issues

    def _build_payload(self, tag, destination, variables, event):
        event_name = _event_name(tag)
        payload = {
            "type": "track",
            "event": event_name,
            "properties": copy.deepcopy(dict(tag.parameters.get("parameters", {})))
            if isinstance(tag.parameters.get("parameters", {}), Mapping)
            else {},
            "variables": copy.deepcopy(dict(variables)),
        }
        return payload, dict(destination.secret_refs), None


class HttpWebhookAdapter(Adapter):
    key = "http_webhook"
    destination_kind = "http_webhook"
    _METHODS = frozenset({"POST", "PUT", "PATCH", "GET"})

    def validate_destination(self, destination: Destination) -> list[AdapterIssue]:
        issues = []
        url = destination.config.get("url")
        parsed = urlparse(url) if isinstance(url, str) else None
        if parsed is None or parsed.scheme not in {"http", "https"} or not parsed.netloc:
            issues.append(
                AdapterIssue(
                    "error",
                    "invalid_url",
                    "http_webhook destination config.url must be an absolute http(s) URL",
                )
            )
        method = destination.config.get("method", "POST")
        if method not in self._METHODS:
            issues.append(
                AdapterIssue(
                    "error",
                    "invalid_method",
                    f"http_webhook method must be one of {sorted(self._METHODS)}",
                )
            )
        return issues

    def _build_payload(self, tag, destination, variables, event):
        payload = {
            "method": destination.config.get("method", "POST"),
            "url": destination.config["url"],
            "headers": copy.deepcopy(dict(destination.config.get("headers", {})))
            if isinstance(destination.config.get("headers", {}), Mapping)
            else {},
            "body": {
                "event": copy.deepcopy(dict(event)),
                "parameters": copy.deepcopy(dict(tag.parameters.get("parameters", {})))
                if isinstance(tag.parameters.get("parameters", {}), Mapping)
                else {},
                "variables": copy.deepcopy(dict(variables)),
            },
        }
        return payload, dict(destination.secret_refs), None


class AdapterRegistry:
    def __init__(self) -> None:
        self._adapters: dict[str, Adapter] = {}

    def register(self, adapter: Adapter) -> None:
        if not adapter.key or adapter.key in self._adapters:
            raise ValidationError(f"duplicate or empty adapter key: {adapter.key!r}")
        self._adapters[adapter.key] = adapter

    def get(self, key: str) -> Adapter | None:
        return self._adapters.get(key)

    def keys(self) -> tuple[str, ...]:
        return tuple(sorted(self._adapters))

    def get_by_destination_kind(self, kind: str) -> Adapter | None:
        for adapter in self._adapters.values():
            if adapter.destination_kind == kind:
                return adapter
        return None

    def capabilities(self) -> dict[str, dict[str, bool]]:
        return {key: self._adapters[key].capabilities.to_dict() for key in self.keys()}


def default_adapter_registry() -> AdapterRegistry:
    registry = AdapterRegistry()
    registry.register(GA4Adapter())
    registry.register(SegmentAdapter())
    registry.register(HttpWebhookAdapter())
    return registry
