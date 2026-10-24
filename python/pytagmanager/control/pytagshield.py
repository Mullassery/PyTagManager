"""Project managed configuration onto PyTagShield's runtime YAML schema.

PyTagShield consumes YAML and routes already-produced events to destinations.
This module performs a deliberately conservative projection:

* only event-name matching is translated; richer trigger conditions and tag
  parameters are not silently dropped;
* destination credentials are resolved only through an explicit callback;
* routes with any unsupported part are omitted so a partial export can never
  broaden delivery.

The resulting mapping is JSON-serializable, and JSON is valid YAML, so it can
be passed directly to ``pytagshield.Config.from_yaml``.
"""

from __future__ import annotations

import copy
import json
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

from pytagmanager.control.config import ConfigPayload, Destination, Trigger

_ALL_TRUE = {"op": "all", "conditions": []}


@dataclass(frozen=True)
class PytagshieldIssue:
    severity: str
    code: str
    message: str
    tag_id: str | None = None
    destination_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "severity": self.severity,
            "code": self.code,
            "message": self.message,
            "tag_id": self.tag_id,
            "destination_id": self.destination_id,
        }


@dataclass(frozen=True)
class PytagshieldExport:
    config: dict[str, Any]
    errors: tuple[PytagshieldIssue, ...]
    warnings: tuple[PytagshieldIssue, ...]

    @property
    def exportable(self) -> bool:
        return not self.errors

    def to_dict(self) -> dict[str, Any]:
        return {
            "exportable": self.exportable,
            "config": copy.deepcopy(self.config),
            "errors": [issue.to_dict() for issue in self.errors],
            "warnings": [issue.to_dict() for issue in self.warnings],
        }

    def to_yaml_compatible_json(self) -> str:
        return json.dumps(self.config, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


class _UnsupportedTrigger(ValueError):
    pass


def _patterns_from_condition(condition: Mapping[str, Any]) -> set[str] | None:
    """Return event-name patterns, None for no name constraint.

    Raises ``_UnsupportedTrigger`` when a constraint cannot be represented by
    PyTagShield's event/property match rule.
    """
    op = condition.get("op")
    path = condition.get("path")
    if op in {"equals", "matches_glob"} and path == "event.name":
        value = condition.get("value")
        if not isinstance(value, str) or not value:
            raise _UnsupportedTrigger("event.name comparison has no usable pattern")
        return {value}
    if op == "in" and path == "event.name":
        value = condition.get("value")
        if not isinstance(value, (list, tuple)) or not value:
            raise _UnsupportedTrigger("event.name 'in' condition has no usable patterns")
        patterns = set()
        for item in value:
            if not isinstance(item, str) or not item:
                raise _UnsupportedTrigger("event.name 'in' contains a non-string pattern")
            patterns.add(item)
        return patterns
    if op == "all":
        children = [
            child for child in condition.get("conditions", ()) if isinstance(child, Mapping)
        ]
        if not children:
            return None
        combined: set[str] | None = None
        for child in children:
            patterns = _patterns_from_condition(child)
            if patterns is None:
                raise _UnsupportedTrigger("condition mixes event.name with unsupported predicates")
            combined = patterns if combined is None else combined & patterns
        if not combined:
            raise _UnsupportedTrigger("conditions require contradictory event names")
        return combined
    if op == "any":
        children = [
            child for child in condition.get("conditions", ()) if isinstance(child, Mapping)
        ]
        if not children:
            raise _UnsupportedTrigger("empty 'any' condition")
        combined: set[str] = set()
        for child in children:
            patterns = _patterns_from_condition(child)
            if patterns is None:
                raise _UnsupportedTrigger("condition branch has no event.name constraint")
            combined |= patterns
        return combined
    raise _UnsupportedTrigger("condition cannot be represented by PyTagShield match rules")


def _trigger_patterns(trigger: Trigger) -> set[str]:
    patterns = _patterns_from_condition(trigger.conditions)
    if patterns is None:
        if trigger.type == "page_view":
            return {"page_view"}
        if trigger.conditions == _ALL_TRUE:
            raise _UnsupportedTrigger(
                f"trigger type {trigger.type!r} needs an event.name condition for server-side routing"
            )
        raise _UnsupportedTrigger(f"trigger type {trigger.type!r} has no event.name condition")
    return patterns


def _secret(
    destination: Destination,
    key: str,
    *,
    resolver: Callable[[str], str] | None,
    errors: list[PytagshieldIssue],
    warnings: list[PytagshieldIssue],
) -> str | None:
    reference = destination.secret_refs.get(key)
    if reference is not None:
        if resolver is None:
            errors.append(
                PytagshieldIssue(
                    "error",
                    "secret_resolver_required",
                    f"destination {destination.name!r} needs secret {key!r}; provide a resolver",
                    destination_id=destination.destination_id,
                )
            )
            return None
        try:
            value = resolver(reference)
        except Exception as exc:
            errors.append(
                PytagshieldIssue(
                    "error",
                    "secret_resolution_failed",
                    f"cannot resolve {key!r} for destination {destination.name!r}: {exc}",
                    destination_id=destination.destination_id,
                )
            )
            return None
        if not isinstance(value, str) or not value:
            errors.append(
                PytagshieldIssue(
                    "error",
                    "secret_empty",
                    f"resolved secret {key!r} for destination {destination.name!r} is empty",
                    destination_id=destination.destination_id,
                )
            )
            return None
        return value

    literal = destination.config.get(key)
    if isinstance(literal, str) and literal:
        warnings.append(
            PytagshieldIssue(
                "warning",
                "literal_credential",
                f"destination {destination.name!r} embeds a literal {key!r}; prefer secret_refs",
                destination_id=destination.destination_id,
            )
        )
        return literal
    errors.append(
        PytagshieldIssue(
            "error",
            "credential_missing",
            f"destination {destination.name!r} requires {key!r}",
            destination_id=destination.destination_id,
        )
    )
    return None


def _copy_mapping(value: Any) -> dict[str, Any]:
    return copy.deepcopy(dict(value)) if isinstance(value, Mapping) else {}


def _destination_settings(
    destination: Destination,
    *,
    resolver: Callable[[str], str] | None,
    errors: list[PytagshieldIssue],
    warnings: list[PytagshieldIssue],
) -> tuple[str, dict[str, Any]] | None:
    kind = destination.kind
    config = destination.config
    settings: dict[str, Any] = {}
    shield_kind: str

    if kind in {"log", "debug"}:
        shield_kind = "log"
    elif kind == "ga4":
        shield_kind = "ga4"
        measurement_id = config.get("measurement_id")
        if not isinstance(measurement_id, str) or not measurement_id:
            errors.append(
                PytagshieldIssue(
                    "error",
                    "measurement_id_missing",
                    f"GA4 destination {destination.name!r} needs config.measurement_id",
                    destination_id=destination.destination_id,
                )
            )
            return None
        api_secret = _secret(
            destination,
            "api_secret",
            resolver=resolver,
            errors=errors,
            warnings=warnings,
        )
        if api_secret is None:
            return None
        settings = {"measurement_id": measurement_id, "api_secret": api_secret}
        if "host" in config:
            settings["host"] = config["host"]
        if "debug_mode" in config:
            settings["debug_mode"] = config["debug_mode"]
    elif kind == "posthog":
        shield_kind = "posthog"
        api_key = _secret(
            destination, "api_key", resolver=resolver, errors=errors, warnings=warnings
        )
        if api_key is None:
            return None
        settings = {"api_key": api_key}
        if "host" in config:
            settings["host"] = config["host"]
    elif kind == "meta":
        shield_kind = "meta"
        pixel_id = config.get("pixel_id")
        if not isinstance(pixel_id, str) or not pixel_id:
            errors.append(
                PytagshieldIssue(
                    "error",
                    "pixel_id_missing",
                    f"Meta destination {destination.name!r} needs config.pixel_id",
                    destination_id=destination.destination_id,
                )
            )
            return None
        access_token = _secret(
            destination,
            "access_token",
            resolver=resolver,
            errors=errors,
            warnings=warnings,
        )
        if access_token is None:
            return None
        settings = {"pixel_id": pixel_id, "access_token": access_token}
        for key in ("host", "api_version", "test_event_code"):
            if key in config:
                settings[key] = config[key]
    elif kind == "sgtm":
        shield_kind = "sgtm"
        url = config.get("url")
        if not isinstance(url, str) or not url:
            errors.append(
                PytagshieldIssue(
                    "error",
                    "url_missing",
                    f"sGTM destination {destination.name!r} needs config.url",
                    destination_id=destination.destination_id,
                )
            )
            return None
        settings = {"url": url}
        if "measurement_id" in config:
            settings["measurement_id"] = config["measurement_id"]
        for key in ("query", "headers"):
            if key in config:
                settings[key] = _copy_mapping(config[key])
    elif kind in {"http_webhook", "webhook"}:
        shield_kind = "webhook"
        method = str(config.get("method", "POST")).upper()
        if method != "POST":
            errors.append(
                PytagshieldIssue(
                    "error",
                    "webhook_method_unsupported",
                    f"PyTagShield webhooks are POST-only; {destination.name!r} uses {method}",
                    destination_id=destination.destination_id,
                )
            )
            return None
        url = config.get("url")
        if not isinstance(url, str) or not url:
            errors.append(
                PytagshieldIssue(
                    "error",
                    "url_missing",
                    f"webhook destination {destination.name!r} needs config.url",
                    destination_id=destination.destination_id,
                )
            )
            return None
        settings = {"url": url}
        if "headers" in config:
            settings["headers"] = _copy_mapping(config["headers"])
    else:
        errors.append(
            PytagshieldIssue(
                "error",
                "destination_kind_unsupported",
                f"destination kind {kind!r} is not understood by PyTagShield",
                destination_id=destination.destination_id,
            )
        )
        return None

    allowed = set(settings)
    for key in config:
        if key not in allowed and key not in {"api_secret", "api_key", "access_token"}:
            warnings.append(
                PytagshieldIssue(
                    "warning",
                    "destination_setting_not_projected",
                    f"destination {destination.name!r} config field {key!r} is not projected",
                    destination_id=destination.destination_id,
                )
            )
    return shield_kind, settings


def _alias_name(
    destination: Destination,
    purpose: str | None,
    used: set[str],
) -> str:
    base = f"{destination.name} ({purpose or 'ungated'})"
    if base not in used:
        used.add(base)
        return base
    candidate = f"{base} [{destination.destination_id[:8]}]"
    while candidate in used:
        candidate = f"{candidate}_"
    used.add(candidate)
    return candidate


def project_to_pytagshield(
    payload: ConfigPayload,
    *,
    pseudonymize_salt: str,
    default_policy: str = "deny",
    secret_resolver: Callable[[str], str] | None = None,
) -> PytagshieldExport:
    """Build a PyTagShield-compatible configuration from a managed payload."""
    errors: list[PytagshieldIssue] = []
    warnings: list[PytagshieldIssue] = []
    if not isinstance(pseudonymize_salt, str) or not pseudonymize_salt:
        errors.append(
            PytagshieldIssue(
                "error",
                "pseudonymize_salt_required",
                "a non-empty pseudonymization salt is required",
            )
        )
        pseudonymize_salt = ""
    elif len(pseudonymize_salt) < 16:
        warnings.append(
            PytagshieldIssue(
                "warning",
                "pseudonymize_salt_short",
                "pseudonymization salt is shorter than 16 characters",
            )
        )
    if default_policy not in {"deny", "allow"}:
        errors.append(
            PytagshieldIssue(
                "error",
                "default_policy_invalid",
                "default_policy must be 'deny' or 'allow'",
            )
        )
        default_policy = "deny"

    destinations_by_id = {
        destination.destination_id: destination for destination in payload.destinations
    }
    triggers_by_id = {trigger.trigger_id: trigger for trigger in payload.triggers}

    used_aliases: set[str] = set()
    used_routes: set[str] = set()
    shield_destinations: list[dict[str, Any]] = []
    aliases: dict[tuple[str, str | None], str] = {}
    purposes: set[str] = set()
    routes: list[dict[str, Any]] = []

    for tag in payload.tags:
        selected: list[tuple[Destination, str | None, str]] = []
        valid = True
        if not tag.destination_ids:
            errors.append(
                PytagshieldIssue(
                    "error",
                    "tag_without_destination",
                    f"tag {tag.name!r} has no destinations",
                    tag_id=tag.tag_id,
                )
            )
            valid = False
        for destination_id in tag.destination_ids:
            destination = destinations_by_id.get(destination_id)
            if destination is None:
                errors.append(
                    PytagshieldIssue(
                        "error",
                        "destination_missing",
                        f"tag {tag.name!r} references missing destination {destination_id}",
                        tag_id=tag.tag_id,
                        destination_id=destination_id,
                    )
                )
                valid = False
                continue
            key = (destination.destination_id, tag.consent_purpose)
            alias = aliases.get(key)
            if alias is None:
                projected = _destination_settings(
                    destination,
                    resolver=secret_resolver,
                    errors=errors,
                    warnings=warnings,
                )
                if projected is None:
                    valid = False
                    continue
                shield_kind, settings = projected
                alias = _alias_name(destination, tag.consent_purpose, used_aliases)
                entry: dict[str, Any] = {
                    "name": alias,
                    "type": shield_kind,
                    "enabled": destination.enabled,
                }
                if tag.consent_purpose is not None:
                    entry["purpose"] = tag.consent_purpose
                    purposes.add(tag.consent_purpose)
                entry[shield_kind] = settings
                shield_destinations.append(entry)
                aliases[key] = alias
            selected.append((destination, tag.consent_purpose, alias))

        patterns: set[str] = set()
        for trigger_id in tag.trigger_ids:
            trigger = triggers_by_id.get(trigger_id)
            if trigger is None:
                errors.append(
                    PytagshieldIssue(
                        "error",
                        "trigger_missing",
                        f"tag {tag.name!r} references missing trigger {trigger_id}",
                        tag_id=tag.tag_id,
                    )
                )
                valid = False
                continue
            if not trigger.enabled:
                continue
            try:
                patterns |= _trigger_patterns(trigger)
            except _UnsupportedTrigger as exc:
                errors.append(
                    PytagshieldIssue(
                        "error",
                        "trigger_not_projectable",
                        f"tag {tag.name!r} trigger {trigger.name!r}: {exc}",
                        tag_id=tag.tag_id,
                    )
                )
                valid = False
        if not patterns:
            errors.append(
                PytagshieldIssue(
                    "error",
                    "event_name_unresolved",
                    f"tag {tag.name!r} has no enabled trigger with a projectable event name",
                    tag_id=tag.tag_id,
                )
            )
            valid = False

        if tag.variable_ids:
            warnings.append(
                PytagshieldIssue(
                    "warning",
                    "variables_not_projected",
                    f"tag {tag.name!r} uses variables; PyTagShield routes the incoming event as-is",
                    tag_id=tag.tag_id,
                )
            )
        if tag.parameters:
            warnings.append(
                PytagshieldIssue(
                    "warning",
                    "parameters_not_projected",
                    f"tag {tag.name!r} parameters are not projected into PyTagShield routes",
                    tag_id=tag.tag_id,
                )
            )
        if not valid:
            continue

        route_name = f"{tag.name} ({tag.tag_id[:8]})"
        while route_name in used_routes:
            route_name = f"{route_name}_"
        used_routes.add(route_name)
        routes.append(
            {
                "name": route_name,
                "destinations": [alias for _, _, alias in selected],
                "enabled": tag.enabled,
                "match": {"events": sorted(patterns)},
            }
        )

    if not routes:
        errors.append(
            PytagshieldIssue(
                "error",
                "no_exportable_routes",
                "no tag could be projected into a PyTagShield route",
            )
        )
    if not purposes:
        purposes.add("analytics")

    config: dict[str, Any] = {
        "minimization": {
            "pseudonymize_ids": True,
            "pseudonymize_salt": pseudonymize_salt,
        },
        "consent": {
            "purposes": sorted(purposes),
            "default_policy": default_policy,
        },
        "destinations": shield_destinations,
        "routes": routes,
    }
    return PytagshieldExport(
        config=config,
        errors=tuple(errors),
        warnings=tuple(warnings),
    )


def validate_with_pytagshield(
    config: Mapping[str, Any],
) -> tuple[bool | None, tuple[str, ...]]:
    """Validate a projected config with PyTagShield when it is installed.

    Returns ``(None, ())`` when the optional dependency is unavailable.
    """
    try:
        import pytagshield  # type: ignore[import-not-found]
    except ImportError:
        return None, ()
    try:
        pytagshield.Config.from_yaml(json.dumps(config))
    except Exception as exc:  # noqa: BLE001 - optional third-party boundary
        return False, (str(exc),)
    return True, ()
