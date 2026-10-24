"""Whole-payload validation: references, adapters, and draft warnings."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from pytagmanager.control.adapters import AdapterRegistry, default_adapter_registry
from pytagmanager.control.config import ConfigPayload
from pytagmanager.control.expressions import iter_variable_ids


@dataclass(frozen=True)
class ValidationIssue:
    severity: str
    code: str
    message: str
    object_type: str | None = None
    object_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "severity": self.severity,
            "code": self.code,
            "message": self.message,
            "object_type": self.object_type,
            "object_id": self.object_id,
        }


@dataclass(frozen=True)
class ConfigValidationReport:
    errors: tuple[ValidationIssue, ...]
    warnings: tuple[ValidationIssue, ...]
    counts: dict[str, int]

    @property
    def valid(self) -> bool:
        return not self.errors

    def to_dict(self) -> dict[str, Any]:
        return {
            "valid": self.valid,
            "errors": [issue.to_dict() for issue in self.errors],
            "warnings": [issue.to_dict() for issue in self.warnings],
            "counts": dict(self.counts),
        }


def _issue(severity, code, message, object_type=None, object_id=None):
    return ValidationIssue(severity, code, message, object_type, object_id)


def _condition_variable_ids(condition: Mapping[str, Any]):
    path = condition.get("path")
    if isinstance(path, str) and path.startswith("variables."):
        yield path.split(".", 2)[1]
    for child in condition.get("conditions", ()):
        if isinstance(child, Mapping):
            yield from _condition_variable_ids(child)


def _computed_cycle(variable_id, by_id, visiting, done) -> bool:
    if variable_id in visiting:
        return True
    if variable_id in done:
        return False
    variable = by_id.get(variable_id)
    if variable is None or variable.source != "computed":
        return False
    visiting.add(variable_id)
    for referenced in iter_variable_ids(variable.source_ref):
        if _computed_cycle(referenced, by_id, visiting, done):
            return True
    visiting.discard(variable_id)
    done.add(variable_id)
    return False


def validate_config_payload(
    payload: ConfigPayload,
    registry: AdapterRegistry | None = None,
) -> ConfigValidationReport:
    registry = registry or default_adapter_registry()
    errors: list[ValidationIssue] = []
    warnings: list[ValidationIssue] = []
    trigger_ids = {trigger.trigger_id for trigger in payload.triggers}
    variable_ids = {variable.variable_id for variable in payload.variables}
    destination_ids = {destination.destination_id for destination in payload.destinations}
    by_variable = {variable.variable_id: variable for variable in payload.variables}

    seen_ids: dict[str, str] = {}
    for object_type, item in payload.all_objects():
        identity = getattr(item, f"{object_type}_id")
        if identity in seen_ids:
            errors.append(
                _issue(
                    "error",
                    "duplicate_object_id",
                    f"id {identity!r} is used by both {seen_ids[identity]} and {object_type}",
                    object_type,
                    identity,
                )
            )
        seen_ids[identity] = object_type

    for destination in payload.destinations:
        adapter = registry.get_by_destination_kind(destination.kind)
        if adapter is None:
            warnings.append(
                _issue(
                    "warning",
                    "unknown_destination_kind",
                    f"no adapter knows destination kind {destination.kind!r}",
                    "destination",
                    destination.destination_id,
                )
            )
            continue
        for issue in adapter.validate_destination(destination):
            target = errors if issue.severity == "error" else warnings
            target.append(
                _issue(
                    issue.severity,
                    issue.code,
                    issue.message,
                    "destination",
                    destination.destination_id,
                )
            )

    for trigger in payload.triggers:
        for referenced in _condition_variable_ids(trigger.conditions):
            if referenced not in variable_ids:
                errors.append(
                    _issue(
                        "error",
                        "variable_reference_missing",
                        f"condition references missing variable {referenced}",
                        "trigger",
                        trigger.trigger_id,
                    )
                )

    for variable in payload.variables:
        if variable.source != "computed":
            continue
        for referenced in iter_variable_ids(variable.source_ref):
            if referenced not in variable_ids:
                errors.append(
                    _issue(
                        "error",
                        "variable_reference_missing",
                        f"computed expression references missing variable {referenced}",
                        "variable",
                        variable.variable_id,
                    )
                )
        if _computed_cycle(variable.variable_id, by_variable, set(), set()):
            errors.append(
                _issue(
                    "error",
                    "variable_cycle",
                    "computed variable references form a cycle",
                    "variable",
                    variable.variable_id,
                )
            )

    for tag in payload.tags:
        missing_triggers = [item for item in tag.trigger_ids if item not in trigger_ids]
        missing_variables = [item for item in tag.variable_ids if item not in variable_ids]
        missing_destinations = [item for item in tag.destination_ids if item not in destination_ids]
        for item in missing_triggers:
            errors.append(
                _issue(
                    "error",
                    "trigger_reference_missing",
                    f"tag references missing trigger {item}",
                    "tag",
                    tag.tag_id,
                )
            )
        for item in missing_variables:
            errors.append(
                _issue(
                    "error",
                    "variable_reference_missing",
                    f"tag references missing variable {item}",
                    "tag",
                    tag.tag_id,
                )
            )
        for item in missing_destinations:
            errors.append(
                _issue(
                    "error",
                    "destination_reference_missing",
                    f"tag references missing destination {item}",
                    "tag",
                    tag.tag_id,
                )
            )
        if not tag.trigger_ids:
            warnings.append(
                _issue(
                    "warning",
                    "tag_without_trigger",
                    "tag has no trigger_ids and cannot fire",
                    "tag",
                    tag.tag_id,
                )
            )
        if not tag.destination_ids:
            warnings.append(
                _issue(
                    "warning",
                    "tag_without_destination",
                    "tag has no destination_ids",
                    "tag",
                    tag.tag_id,
                )
            )
        if tag.consent_purpose is None:
            warnings.append(
                _issue(
                    "warning",
                    "tag_without_consent_purpose",
                    "tag has no consent purpose; it is not consent-gated",
                    "tag",
                    tag.tag_id,
                )
            )
        adapter = registry.get(tag.type)
        if adapter is None:
            errors.append(
                _issue(
                    "error",
                    "unknown_adapter",
                    f"no adapter is registered for tag type {tag.type!r}",
                    "tag",
                    tag.tag_id,
                )
            )
            continue
        for issue in adapter.validate_tag(tag, payload.destinations):
            target = errors if issue.severity == "error" else warnings
            target.append(_issue(issue.severity, issue.code, issue.message, "tag", tag.tag_id))
        evidence = tag.source_evidence or {}
        evidence_warnings = evidence.get("warnings", ())
        if isinstance(evidence_warnings, (list, tuple)):
            for warning in evidence_warnings:
                if isinstance(warning, str) and warning:
                    warnings.append(
                        _issue(
                            "warning",
                            "draft_warning",
                            warning,
                            "tag",
                            tag.tag_id,
                        )
                    )

    return ConfigValidationReport(
        errors=tuple(errors),
        warnings=tuple(warnings),
        counts={
            "tags": len(payload.tags),
            "triggers": len(payload.triggers),
            "variables": len(payload.variables),
            "destinations": len(payload.destinations),
        },
    )
