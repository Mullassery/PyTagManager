"""Deterministic, clearly-labeled simulation of one event through a revision."""

from __future__ import annotations

import copy
import time
from collections.abc import Mapping
from typing import Any
from urllib.parse import urlsplit

from pytagmanager.control.adapters import AdapterRegistry, default_adapter_registry
from pytagmanager.control.conditions import evaluate_condition
from pytagmanager.control.config import ConfigPayload
from pytagmanager.control.errors import ValidationError
from pytagmanager.control.variables import ResolvedVariable, VariableResolver
from pytagmanager.observability.events import is_sensitive_key

_REDACTED = "[REDACTED]"
_CONTEXT_KEYS = frozenset({"page", "dom", "data_layer", "consent", "stored_consent", "properties"})
_TRIGGER_EVENT_TYPES = {
    "page_view": "page_view",
    "custom_event": "custom_event",
    "click": "click",
    "link_click": "link_click",
    "form_submit": "form_submit",
    "route_change": "route_change",
    "consent_change": "consent_change",
}
_RESOLVED = frozenset({"resolved", "default"})


def _redact(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {
            str(key): _REDACTED if is_sensitive_key(str(key)) else _redact(item)
            for key, item in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [_redact(item) for item in value]
    return value


def _mapping_field(event: Mapping[str, Any], key: str) -> dict[str, Any]:
    value = event.get(key, {})
    if value is None:
        return {}
    if not isinstance(value, Mapping):
        raise ValidationError(f"event.{key} must be an object")
    return copy.deepcopy(dict(value))


def _consent_map(value: Any, field: str) -> dict[str, bool]:
    if value is None:
        return {}
    if not isinstance(value, Mapping):
        raise ValidationError(f"{field} must be an object")
    result = {}
    for key, item in value.items():
        if not isinstance(key, str) or not key:
            raise ValidationError(f"{field} keys must be non-empty strings")
        if not isinstance(item, bool):
            raise ValidationError(f"{field}.{key} must be a boolean")
        result[key] = item
    return result


def normalize_event(event: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(event, Mapping):
        raise ValidationError("event must be a JSON object")
    name = event.get("name")
    if not isinstance(name, str) or not name:
        raise ValidationError("event.name must be a non-empty string")
    event_type = event.get("type", "custom_event")
    if not isinstance(event_type, str) or not event_type:
        raise ValidationError("event.type must be a non-empty string")
    properties = _mapping_field(event, "properties")
    page = _mapping_field(event, "page")
    if "path" not in page and isinstance(page.get("url"), str):
        page["path"] = urlsplit(page["url"]).path or "/"
    dom = _mapping_field(event, "dom")
    data_layer = _mapping_field(event, "data_layer")
    return {
        "name": name,
        "type": event_type,
        "properties": properties,
        "page": page,
        "dom": dom,
        "data_layer": data_layer,
        "consent": _consent_map(event.get("consent"), "event.consent"),
        "stored_consent": _consent_map(event.get("stored_consent"), "event.stored_consent"),
    }


def _consent_state(normalized, default_consent, consent_override) -> dict[str, bool]:
    consent = dict(_consent_map(default_consent, "default_consent"))
    consent.update(normalized["stored_consent"])
    consent.update(normalized["consent"])
    consent.update(_consent_map(consent_override, "consent"))
    return consent


def _event_core(normalized) -> dict[str, Any]:
    core = {
        "name": normalized["name"],
        "type": normalized["type"],
        "properties": copy.deepcopy(normalized["properties"]),
    }
    for key, value in normalized.items():
        if key not in _CONTEXT_KEYS and key not in {"name", "type"}:
            core[key] = copy.deepcopy(value)
    for key, value in normalized["properties"].items():
        core.setdefault(key, copy.deepcopy(value))
    return core


def _condition_context(normalized, consent, variables) -> dict[str, Any]:
    return {
        "event": _event_core(normalized),
        "page": copy.deepcopy(normalized["page"]),
        "dom": copy.deepcopy(normalized["dom"]),
        "data_layer": copy.deepcopy(normalized["data_layer"]),
        "consent": dict(consent),
        "variables": variables,
    }


def _trigger_type_matches(trigger_type: str, event_type: str) -> bool:
    expected = _TRIGGER_EVENT_TYPES.get(trigger_type)
    return expected is None or expected == event_type


def _tag_variables(tag, resolutions: dict[str, ResolvedVariable]) -> dict[str, Any]:
    result = {}
    for variable_id in tag.variable_ids:
        resolved = resolutions.get(variable_id)
        if resolved is None:
            result[variable_id] = None
        elif resolved.status in _RESOLVED:
            result[resolved.name] = resolved.redacted_value
        else:
            result[resolved.name] = None
    return result


def preview_event(
    payload: ConfigPayload,
    event: Mapping[str, Any],
    *,
    container_id: str | None = None,
    config_version: str | None = None,
    revision_status: str | None = None,
    default_consent: Mapping[str, bool] | None = None,
    consent_override: Mapping[str, bool] | None = None,
    registry: AdapterRegistry | None = None,
) -> dict[str, Any]:
    started = time.perf_counter()
    registry = registry or default_adapter_registry()
    normalized = normalize_event(event)
    consent = _consent_state(normalized, default_consent or {}, consent_override or {})
    resolved = VariableResolver(payload.variables, _condition_context(normalized, consent, {}))
    resolutions = resolved.resolve_all()
    resolution_by_id = {item.variable_id: item for item in resolutions}
    raw_variables = {
        item.variable_id: item.value for item in resolutions if item.status in _RESOLVED
    }
    context = _condition_context(normalized, consent, raw_variables)

    triggers = []
    matched_trigger_ids = set()
    ordered_triggers = sorted(
        enumerate(payload.triggers),
        key=lambda pair: (-pair[1].priority, pair[0]),
    )
    for declaration_index, trigger in ordered_triggers:
        if not trigger.enabled:
            matched = False
            reason = "disabled"
        elif not _trigger_type_matches(trigger.type, normalized["type"]):
            matched = False
            reason = "event_type_mismatch"
        elif evaluate_condition(trigger.conditions, context):
            matched = True
            reason = "matched"
        else:
            matched = False
            reason = "conditions_not_met"
        if matched:
            matched_trigger_ids.add(trigger.trigger_id)
        triggers.append(
            {
                "trigger_id": trigger.trigger_id,
                "name": trigger.name,
                "type": trigger.type,
                "priority": trigger.priority,
                "matched": matched,
                "reason": reason,
                "declaration_index": declaration_index,
            }
        )

    tags = []
    errors = []
    redacted_event = _redact(normalized)
    for tag in payload.tags:
        matched = [
            trigger_id for trigger_id in tag.trigger_ids if trigger_id in matched_trigger_ids
        ]
        blocked_reason = None
        if not tag.enabled:
            blocked_reason = "disabled"
        elif not tag.trigger_ids:
            blocked_reason = "no_trigger"
        elif not matched:
            blocked_reason = "conditions_not_met"
        elif tag.consent_purpose is not None:
            if tag.consent_purpose not in consent:
                blocked_reason = "consent_missing"
            elif consent[tag.consent_purpose] is not True:
                blocked_reason = "consent_denied"
        selected = blocked_reason is None
        item = {
            "tag_id": tag.tag_id,
            "name": tag.name,
            "type": tag.type,
            "enabled": tag.enabled,
            "selected": selected,
            "blocked_reason": blocked_reason,
            "matched_trigger_ids": matched,
            "consent_purpose": tag.consent_purpose,
            "adapter_result": None,
        }
        if selected:
            adapter = registry.get(tag.type)
            if adapter is None:
                error = f"no adapter is registered for tag type {tag.type!r}"
                item["adapter_result"] = {
                    "simulation": True,
                    "would_send": False,
                    "adapter": tag.type,
                    "error": error,
                }
                errors.append({"tag_id": tag.tag_id, "error": error})
            else:
                try:
                    result = adapter.build(
                        tag,
                        payload.destinations,
                        _tag_variables(tag, resolution_by_id),
                        redacted_event,
                    )
                except Exception as exc:
                    result = None
                    error = f"adapter failed: {exc}"
                    item["adapter_result"] = {
                        "simulation": True,
                        "would_send": False,
                        "adapter": tag.type,
                        "error": error,
                    }
                    errors.append({"tag_id": tag.tag_id, "error": error})
                if result is not None:
                    item["adapter_result"] = _redact(result.to_dict())
                    if result.error:
                        errors.append({"tag_id": tag.tag_id, "error": result.error})
        tags.append(item)

    trace = {
        "simulation": True,
        "trace_version": "1",
        "container_id": container_id,
        "config_version": config_version,
        "revision_status": revision_status,
        "event": redacted_event,
        "consent": dict(consent),
        "variables": [item.to_trace_dict() for item in resolutions],
        "triggers": triggers,
        "tags": tags,
        "errors": errors,
        "timing_ms": round((time.perf_counter() - started) * 1000, 3),
    }
    return trace
