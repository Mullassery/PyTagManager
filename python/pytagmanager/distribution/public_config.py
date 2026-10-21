"""Build secret-free public container configuration for CDN distribution."""

from __future__ import annotations

import copy
import hashlib
from datetime import datetime, timezone
from typing import Any, Iterable, Mapping

from pytagmanager.control.errors import NotFoundError, ValidationError
from pytagmanager.control.ids import utc_now
from pytagmanager.control.service import ControlPlaneService
from pytagmanager.events.contract import SCHEMA_VERSION, canonical_json

PUBLISHED_CONFIG_SCHEMA_VERSION = "1.0"
PUBLISHED_CONFIG_KIND = "pytagmanager.container"
IMMUTABLE_CACHE_MAX_AGE = 31_536_000
DEFAULT_MIN_SDK = {
    "web": "0.1.0",
    "android": "0.1.0",
    "ios": "0.1.0",
}
_SECRET_KEY_MARKERS = (
    "secret",
    "password",
    "passwd",
    "credential",
    "api_key",
    "apikey",
    "access_token",
    "refresh_token",
    "private_key",
)


def _check_public(value: Any, path: str = "$") -> None:
    if isinstance(value, Mapping):
        for key, item in value.items():
            lowered = str(key).lower()
            if any(marker in lowered for marker in _SECRET_KEY_MARKERS):
                raise ValidationError(
                    f"published configuration contains prohibited secret field {path}.{key}"
                )
            _check_public(item, f"{path}.{key}")
    elif isinstance(value, (list, tuple)):
        for index, item in enumerate(value):
            _check_public(item, f"{path}[{index}]")


def _event_names_from_condition(condition: Mapping[str, Any]) -> set[str]:
    names: set[str] = set()
    op = condition.get("op")
    if op in {"all", "any", "not"}:
        for child in condition.get("conditions", ()):
            if isinstance(child, Mapping):
                names.update(_event_names_from_condition(child))
        return names
    if condition.get("path") != "event.name":
        return names
    if op == "equals" and isinstance(condition.get("value"), str):
        names.add(condition["value"])
    elif op == "in" and isinstance(condition.get("value"), list):
        names.update(item for item in condition["value"] if isinstance(item, str))
    return names


def _trigger_event_names(trigger: Any) -> set[str]:
    trigger_type = trigger.type
    if trigger_type in {"page_view", "route_change"}:
        return {"page_view"}
    if trigger_type == "custom_event":
        return _event_names_from_condition(trigger.conditions)
    if trigger_type in {"click", "link_click"}:
        return {"click"}
    if trigger_type == "form_submit":
        return {"form_submit"}
    if trigger_type == "consent_change":
        return {"consent_change"}
    return set()


def _tag_event_name(tag: Any) -> str | None:
    raw = tag.parameters.get("event_name", tag.parameters.get("eventName"))
    return raw if isinstance(raw, str) and raw else None


def _build_event_index(payload: Any) -> list[dict[str, Any]]:
    triggers = {trigger.trigger_id: trigger for trigger in payload.triggers}
    event_tags: dict[str, set[str]] = {}
    event_purposes: dict[str, set[str]] = {}

    for tag in payload.tags:
        if not tag.enabled:
            continue
        names: set[str] = set()
        tag_event = _tag_event_name(tag)
        if tag_event:
            names.add(tag_event)
        for trigger_id in tag.trigger_ids:
            trigger = triggers.get(trigger_id)
            if trigger is not None and trigger.enabled:
                names.update(_trigger_event_names(trigger))
        for name in names:
            event_tags.setdefault(name, set()).add(tag.tag_id)
            if tag.consent_purpose:
                event_purposes.setdefault(name, set()).add(tag.consent_purpose)

    return [
        {
            "name": name,
            "purposes": sorted(event_purposes.get(name, set())),
            "tag_ids": sorted(event_tags[name]),
        }
        for name in sorted(event_tags)
    ]


def _public_tags(payload: Any) -> list[dict[str, Any]]:
    return [
        {
            "tag_id": tag.tag_id,
            "name": tag.name,
            "type": tag.type,
            "event_name": _tag_event_name(tag),
            "consent_purpose": tag.consent_purpose,
            "enabled": tag.enabled,
            "trigger_ids": list(tag.trigger_ids),
            "destination_ids": list(tag.destination_ids),
        }
        for tag in sorted(payload.tags, key=lambda item: (item.name, item.tag_id))
    ]


def _public_destinations(payload: Any) -> list[dict[str, Any]]:
    return [
        {
            "destination_id": destination.destination_id,
            "name": destination.name,
            "kind": destination.kind,
            "enabled": destination.enabled,
        }
        for destination in sorted(
            payload.destinations, key=lambda item: (item.name, item.destination_id)
        )
    ]


def build_published_config(
    service: ControlPlaneService,
    container_id: str,
    environment_ref: str,
    *,
    org_id: str | None = None,
    published_at: str | None = None,
    default_consent: Mapping[str, bool] | None = None,
    min_sdk: Mapping[str, str] | None = None,
    allow_protected: bool = False,
) -> dict[str, Any]:
    """Build and integrity-seal a public configuration document.

    The revision must already be active in the environment, must validate,
    and the builder never includes destination configuration or secret
    references. ``allow_protected`` is an explicit operator approval for
    publishing a protected environment.
    """
    environment = service.get_environment(container_id, environment_ref, org_id=org_id)
    if environment.protected and not allow_protected:
        raise ValidationError(
            f"environment {environment.name!r} is protected; explicit allow_protected "
            "is required to publish it"
        )
    if environment.current_config_version is None:
        raise ValidationError(
            f"environment {environment.name!r} has no active configuration revision"
        )
    revision = service.get_revision(
        container_id, environment.current_config_version, org_id=org_id
    )
    report = service.validate_config(
        container_id, config_version=revision.config_version, org_id=org_id
    )
    if not report.valid:
        messages = "; ".join(issue.message for issue in report.errors)
        raise ValidationError(
            f"revision {revision.config_version!r} failed validation: {messages}"
        )

    unsigned: dict[str, Any] = {
        "schema_version": PUBLISHED_CONFIG_SCHEMA_VERSION,
        "kind": PUBLISHED_CONFIG_KIND,
        "container_id": container_id,
        "config_version": revision.config_version,
        "revision_number": revision.revision_number,
        "revision_checksum": revision.checksum,
        "environment": {
            "name": environment.name,
            "protected": environment.protected,
        },
        "published_at": published_at or utc_now(),
        "event_schema_version": SCHEMA_VERSION,
        "events": _build_event_index(revision.payload),
        "tags": _public_tags(revision.payload),
        "destinations": _public_destinations(revision.payload),
        "features": {
            "client_side_execution": False,
            "event_collection": True,
            "server_side_forwarding": True,
        },
        "compatibility": {
            "event_contract": SCHEMA_VERSION,
            "min_sdk": dict(DEFAULT_MIN_SDK if min_sdk is None else min_sdk),
        },
        "cache": {
            "max_age_seconds": IMMUTABLE_CACHE_MAX_AGE,
            "immutable": True,
        },
    }
    if default_consent is not None:
        unsigned["consent_defaults"] = {
            str(purpose): bool(value)
            for purpose, value in sorted(default_consent.items())
        }

    _check_public(unsigned)
    digest = hashlib.sha256(canonical_json(unsigned).encode("utf-8")).hexdigest()
    document = copy.deepcopy(unsigned)
    document["integrity"] = {"algorithm": "sha256", "digest": digest}
    _check_public(document)
    return document


def verify_published_config(document: Mapping[str, Any]) -> str:
    """Verify the self-checksum and return the digest.

    This detects corruption in transit. It does not authenticate the
    publisher and is not a substitute for TLS or a trusted distribution
    channel.
    """
    if not isinstance(document, Mapping):
        raise ValidationError("published configuration must be an object")
    integrity = document.get("integrity")
    if not isinstance(integrity, Mapping):
        raise ValidationError("published configuration is missing integrity metadata")
    if integrity.get("algorithm") != "sha256":
        raise ValidationError("unsupported published configuration integrity algorithm")
    unsigned = {key: value for key, value in document.items() if key != "integrity"}
    digest = hashlib.sha256(canonical_json(unsigned).encode("utf-8")).hexdigest()
    if digest != integrity.get("digest"):
        raise ValidationError("published configuration integrity digest does not match")
    return digest


def environment_slug(name: str) -> str:
    value = "".join(
        character.lower() if character.isalnum() else "-" for character in name
    ).strip("-")
    while "--" in value:
        value = value.replace("--", "-")
    if not value:
        raise ValidationError("environment name cannot be converted to a URL slug")
    return value[:96]


def published_config_paths(
    container_key: str,
    config_version: str,
    slug: str,
) -> dict[str, str]:
    base = f"containers/{container_key}"
    return {
        "config": f"{base}/revisions/{config_version}/config.json",
        "latest": f"{base}/environments/{slug}/latest.json",
        "manifest": f"{base}/environments/{slug}/manifest.json",
    }


def utc_timestamp(value: datetime | None = None) -> str:
    return (value or datetime.now(timezone.utc)).astimezone(timezone.utc).isoformat(
        timespec="milliseconds"
    ).replace("+00:00", "Z")


def iter_event_names(config: Mapping[str, Any]) -> Iterable[str]:
    for event in config.get("events", ()):
        if isinstance(event, Mapping) and isinstance(event.get("name"), str):
            yield event["name"]


def purpose_requirements(config: Mapping[str, Any]) -> dict[str, tuple[str, ...]]:
    result = {}
    for event in config.get("events", ()):
        if not isinstance(event, Mapping) or not isinstance(event.get("name"), str):
            continue
        purposes = event.get("purposes", ())
        result[event["name"]] = tuple(
            purpose for purpose in purposes if isinstance(purpose, str)
        )
    return result


def find_public_event(config: Mapping[str, Any], name: str) -> Mapping[str, Any] | None:
    for event in config.get("events", ()):
        if isinstance(event, Mapping) and event.get("name") == name:
            return event
    return None


def require_current_revision(
    service: ControlPlaneService,
    container_id: str,
    environment_ref: str,
    *,
    org_id: str | None = None,
) -> tuple[str, int]:
    environment = service.get_environment(container_id, environment_ref, org_id=org_id)
    if environment.current_config_version is None:
        raise NotFoundError(
            f"environment {environment.name!r} has no active configuration revision"
        )
    revision = service.get_revision(
        container_id, environment.current_config_version, org_id=org_id
    )
    return revision.config_version, revision.revision_number
