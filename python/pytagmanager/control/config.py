"""Managed tag, trigger, variable, destination, and payload models."""

from __future__ import annotations

import copy
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from pytagmanager.control.checksums import canonical_json
from pytagmanager.control.conditions import validate_condition
from pytagmanager.control.errors import ValidationError
from pytagmanager.control.expressions import validate_expression
from pytagmanager.control.ids import new_id, validate_id, validate_name
from pytagmanager.control.secrets import SecretRef

PAYLOAD_KEYS = ("tags", "triggers", "variables", "destinations")
TRIGGER_TYPES = frozenset(
    {
        "page_view",
        "custom_event",
        "click",
        "link_click",
        "form_submit",
        "route_change",
        "dom_condition",
        "consent_change",
        "variable_condition",
    }
)
VARIABLE_TYPES = frozenset({"string", "number", "boolean", "json", "list", "null"})
VARIABLE_SOURCES = frozenset(
    {
        "static",
        "page_url",
        "page_path",
        "page_title",
        "referrer",
        "dom",
        "data_layer",
        "event",
        "consent",
        "computed",
    }
)
_PAGE_SOURCES = frozenset({"page_url", "page_path", "page_title", "referrer"})
_PATH_RE = re.compile(r"^[A-Za-z0-9_-]+(?:\.[A-Za-z0-9_-]+)*$")
_PURPOSE_RE = re.compile(r"^[a-z][a-z0-9_-]{0,63}$")
_ALL_TRUE = {"op": "all", "conditions": []}


def _mapping(value: Any, field: str) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise ValidationError(f"{field} must be a JSON object")
    canonical_json(value)
    return copy.deepcopy(dict(value))


def _string(value: Any, field: str, *, allow_empty: bool = False) -> str:
    if not isinstance(value, str):
        raise ValidationError(f"{field} must be a string")
    if not allow_empty and not value:
        raise ValidationError(f"{field} must not be empty")
    return value


def _bool(value: Any, field: str) -> bool:
    if not isinstance(value, bool):
        raise ValidationError(f"{field} must be a boolean")
    return value


def _int(value: Any, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValidationError(f"{field} must be an integer")
    return value


def _keys(
    value: Mapping[str, Any],
    expected: set[str],
    field: str,
    *,
    required: set[str] | None = None,
) -> None:
    unknown = sorted(set(value) - expected)
    missing = sorted((required or set()) - set(value))
    if unknown:
        raise ValidationError(f"{field} contains unknown field(s): {', '.join(unknown)}")
    if missing:
        raise ValidationError(f"{field} is missing required field(s): {', '.join(missing)}")


def _id_list(value: Any, field: str) -> tuple[str, ...]:
    if not isinstance(value, (list, tuple)):
        raise ValidationError(f"{field} must be a list of IDs")
    result = []
    seen = set()
    for index, item in enumerate(value):
        item_id = validate_id(item, field=f"{field}[{index}]")
        if item_id in seen:
            raise ValidationError(f"{field} contains duplicate id {item_id!r}")
        seen.add(item_id)
        result.append(item_id)
    return tuple(result)


def _mapping_tuple(value: Any, field: str, parser) -> tuple[Any, ...]:
    if not isinstance(value, (list, tuple)):
        raise ValidationError(f"{field} must be a list")
    result = []
    seen = set()
    for item in value:
        parsed = parser.from_dict(item)
        identity = getattr(parsed, parser.identity_field)
        if identity in seen:
            raise ValidationError(f"{field} contains duplicate id {identity!r}")
        seen.add(identity)
        result.append(parsed)
    return tuple(result)


def _check_type(value: Any, value_type: str, field: str) -> None:
    if value_type == "json":
        canonical_json(value)
        return
    if value_type == "null":
        if value is not None:
            raise ValidationError(f"{field} must be null")
        return
    if value_type == "string" and not isinstance(value, str):
        raise ValidationError(f"{field} must be a string")
    if value_type == "number" and (isinstance(value, bool) or not isinstance(value, (int, float))):
        raise ValidationError(f"{field} must be a number")
    if value_type == "boolean" and not isinstance(value, bool):
        raise ValidationError(f"{field} must be a boolean")
    if value_type == "list" and not isinstance(value, (list, tuple)):
        raise ValidationError(f"{field} must be a list")


@dataclass(frozen=True)
class Tag:
    tag_id: str
    name: str
    type: str
    description: str = ""
    parameters: dict[str, Any] = field(default_factory=dict)
    trigger_ids: tuple[str, ...] = ()
    variable_ids: tuple[str, ...] = ()
    consent_purpose: str | None = None
    destination_ids: tuple[str, ...] = ()
    enabled: bool = True
    adapter_version: str = "1"
    compatibility: dict[str, Any] = field(default_factory=dict)
    source_evidence: dict[str, Any] | None = None

    identity_field = "tag_id"

    @classmethod
    def create(
        cls,
        *,
        name: str,
        type: str,
        description: str = "",
        parameters: Mapping[str, Any] | None = None,
        trigger_ids: tuple[str, ...] | list[str] = (),
        variable_ids: tuple[str, ...] | list[str] = (),
        consent_purpose: str | None = None,
        destination_ids: tuple[str, ...] | list[str] = (),
        enabled: bool = True,
        adapter_version: str = "1",
        compatibility: Mapping[str, Any] | None = None,
        source_evidence: Mapping[str, Any] | None = None,
    ) -> Tag:
        return cls(
            tag_id=new_id(),
            name=validate_name(name),
            type=_string(type, "tag.type"),
            description=_string(description, "tag.description", allow_empty=True),
            parameters=_mapping(parameters or {}, "tag.parameters"),
            trigger_ids=_id_list(trigger_ids, "tag.trigger_ids"),
            variable_ids=_id_list(variable_ids, "tag.variable_ids"),
            consent_purpose=_purpose(consent_purpose),
            destination_ids=_id_list(destination_ids, "tag.destination_ids"),
            enabled=_bool(enabled, "tag.enabled"),
            adapter_version=_string(adapter_version, "tag.adapter_version"),
            compatibility=_mapping(
                compatibility or {"min_schema": "1.0", "adapter_contract": "1"},
                "tag.compatibility",
            ),
            source_evidence=(
                None
                if source_evidence is None
                else _mapping(source_evidence, "tag.source_evidence")
            ),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "tag_id": self.tag_id,
            "name": self.name,
            "description": self.description,
            "type": self.type,
            "parameters": copy.deepcopy(self.parameters),
            "trigger_ids": list(self.trigger_ids),
            "variable_ids": list(self.variable_ids),
            "consent_purpose": self.consent_purpose,
            "destination_ids": list(self.destination_ids),
            "enabled": self.enabled,
            "adapter_version": self.adapter_version,
            "compatibility": copy.deepcopy(self.compatibility),
            "source_evidence": (
                None if self.source_evidence is None else copy.deepcopy(self.source_evidence)
            ),
        }

    @classmethod
    def from_dict(cls, value: Any) -> Tag:
        data = _mapping(value, "tag")
        expected = {
            "tag_id",
            "name",
            "description",
            "type",
            "parameters",
            "trigger_ids",
            "variable_ids",
            "consent_purpose",
            "destination_ids",
            "enabled",
            "adapter_version",
            "compatibility",
            "source_evidence",
        }
        _keys(data, expected, "tag", required={"tag_id", "name", "type"})
        return cls(
            tag_id=validate_id(data["tag_id"], field="tag.tag_id"),
            name=validate_name(data["name"]),
            description=_string(data.get("description", ""), "tag.description", allow_empty=True),
            type=_string(data["type"], "tag.type"),
            parameters=_mapping(data.get("parameters", {}), "tag.parameters"),
            trigger_ids=_id_list(data.get("trigger_ids", ()), "tag.trigger_ids"),
            variable_ids=_id_list(data.get("variable_ids", ()), "tag.variable_ids"),
            consent_purpose=_purpose(data.get("consent_purpose")),
            destination_ids=_id_list(data.get("destination_ids", ()), "tag.destination_ids"),
            enabled=_bool(data.get("enabled", True), "tag.enabled"),
            adapter_version=_string(data.get("adapter_version", "1"), "tag.adapter_version"),
            compatibility=_mapping(
                data.get("compatibility", {"min_schema": "1.0", "adapter_contract": "1"}),
                "tag.compatibility",
            ),
            source_evidence=(
                None
                if data.get("source_evidence") is None
                else _mapping(data["source_evidence"], "tag.source_evidence")
            ),
        )


@dataclass(frozen=True)
class Trigger:
    trigger_id: str
    name: str
    type: str
    conditions: dict[str, Any]
    priority: int = 0
    enabled: bool = True

    identity_field = "trigger_id"

    @classmethod
    def create(
        cls,
        *,
        name: str,
        type: str,
        conditions: Mapping[str, Any] | None = None,
        priority: int = 0,
        enabled: bool = True,
    ) -> Trigger:
        trigger_type = _string(type, "trigger.type")
        if trigger_type not in TRIGGER_TYPES:
            raise ValidationError(f"unsupported trigger type: {trigger_type!r}")
        return cls(
            trigger_id=new_id(),
            name=validate_name(name),
            type=trigger_type,
            conditions=validate_condition(conditions if conditions is not None else _ALL_TRUE),
            priority=_int(priority, "trigger.priority"),
            enabled=_bool(enabled, "trigger.enabled"),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "trigger_id": self.trigger_id,
            "name": self.name,
            "type": self.type,
            "conditions": copy.deepcopy(self.conditions),
            "priority": self.priority,
            "enabled": self.enabled,
        }

    @classmethod
    def from_dict(cls, value: Any) -> Trigger:
        data = _mapping(value, "trigger")
        expected = {"trigger_id", "name", "type", "conditions", "priority", "enabled"}
        _keys(data, expected, "trigger", required={"trigger_id", "name", "type"})
        trigger_type = _string(data["type"], "trigger.type")
        if trigger_type not in TRIGGER_TYPES:
            raise ValidationError(f"unsupported trigger type: {trigger_type!r}")
        return cls(
            trigger_id=validate_id(data["trigger_id"], field="trigger.trigger_id"),
            name=validate_name(data["name"]),
            type=trigger_type,
            conditions=validate_condition(data.get("conditions", _ALL_TRUE)),
            priority=_int(data.get("priority", 0), "trigger.priority"),
            enabled=_bool(data.get("enabled", True), "trigger.enabled"),
        )


def _purpose(value: Any) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not _PURPOSE_RE.fullmatch(value):
        raise ValidationError(
            "consent purpose must match [a-z][a-z0-9_-]* and be at most 64 characters"
        )
    return value


def _source_ref(source: str, value: Any) -> Any:
    if source in _PAGE_SOURCES or source == "static":
        if value is not None:
            raise ValidationError(f"variable source {source!r} does not accept source_ref")
        return None
    if source in {"data_layer", "event", "consent"}:
        if not isinstance(value, str) or not _PATH_RE.fullmatch(value):
            raise ValidationError(f"variable source {source!r} requires a dotted source_ref")
        return value
    if source == "dom":
        if isinstance(value, str):
            if not value:
                raise ValidationError("DOM source_ref selector must not be empty")
            return value
        if not isinstance(value, Mapping):
            raise ValidationError("DOM source_ref must be a selector or object")
        ref = _mapping(value, "variable.source_ref")
        _keys(ref, {"selector", "attribute"}, "variable.source_ref", required={"selector"})
        ref["selector"] = _string(ref["selector"], "variable.source_ref.selector")
        if "attribute" in ref:
            ref["attribute"] = _string(ref["attribute"], "variable.source_ref.attribute")
        return ref
    if source == "computed":
        return validate_expression(value)
    raise ValidationError(f"unsupported variable source: {source!r}")


@dataclass(frozen=True)
class Variable:
    variable_id: str
    name: str
    type: str
    source: str
    source_ref: Any = None
    default: Any = None
    sensitive: bool = False
    enabled: bool = True

    identity_field = "variable_id"

    @classmethod
    def create(
        cls,
        *,
        name: str,
        type: str,
        source: str,
        source_ref: Any = None,
        default: Any = None,
        sensitive: bool = False,
        enabled: bool = True,
    ) -> Variable:
        variable_type = _string(type, "variable.type")
        if variable_type not in VARIABLE_TYPES:
            raise ValidationError(f"unsupported variable type: {variable_type!r}")
        variable_source = _string(source, "variable.source")
        if variable_source not in VARIABLE_SOURCES:
            raise ValidationError(f"unsupported variable source: {variable_source!r}")
        canonical_json(default)
        if default is not None:
            _check_type(default, variable_type, "variable.default")
        return cls(
            variable_id=new_id(),
            name=validate_name(name),
            type=variable_type,
            source=variable_source,
            source_ref=_source_ref(variable_source, source_ref),
            default=copy.deepcopy(default),
            sensitive=_bool(sensitive, "variable.sensitive"),
            enabled=_bool(enabled, "variable.enabled"),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "variable_id": self.variable_id,
            "name": self.name,
            "type": self.type,
            "source": self.source,
            "source_ref": copy.deepcopy(self.source_ref),
            "default": copy.deepcopy(self.default),
            "sensitive": self.sensitive,
            "enabled": self.enabled,
        }

    @classmethod
    def from_dict(cls, value: Any) -> Variable:
        data = _mapping(value, "variable")
        expected = {
            "variable_id",
            "name",
            "type",
            "source",
            "source_ref",
            "default",
            "sensitive",
            "enabled",
        }
        _keys(
            data,
            expected,
            "variable",
            required={"variable_id", "name", "type", "source"},
        )
        variable_type = _string(data["type"], "variable.type")
        if variable_type not in VARIABLE_TYPES:
            raise ValidationError(f"unsupported variable type: {variable_type!r}")
        variable_source = _string(data["source"], "variable.source")
        if variable_source not in VARIABLE_SOURCES:
            raise ValidationError(f"unsupported variable source: {variable_source!r}")
        default = copy.deepcopy(data.get("default"))
        canonical_json(default)
        if default is not None:
            _check_type(default, variable_type, "variable.default")
        return cls(
            variable_id=validate_id(data["variable_id"], field="variable.variable_id"),
            name=validate_name(data["name"]),
            type=variable_type,
            source=variable_source,
            source_ref=_source_ref(variable_source, data.get("source_ref")),
            default=default,
            sensitive=_bool(data.get("sensitive", False), "variable.sensitive"),
            enabled=_bool(data.get("enabled", True), "variable.enabled"),
        )


@dataclass(frozen=True)
class Destination:
    destination_id: str
    name: str
    kind: str
    config: dict[str, Any] = field(default_factory=dict)
    secret_refs: dict[str, str] = field(default_factory=dict)
    enabled: bool = True

    identity_field = "destination_id"

    @classmethod
    def create(
        cls,
        *,
        name: str,
        kind: str,
        config: Mapping[str, Any] | None = None,
        secret_refs: Mapping[str, str] | None = None,
        enabled: bool = True,
    ) -> Destination:
        refs = {
            _string(key, "destination.secret_refs key"): str(SecretRef.parse(raw))
            for key, raw in (secret_refs or {}).items()
        }
        return cls(
            destination_id=new_id(),
            name=validate_name(name),
            kind=_string(kind, "destination.kind"),
            config=_mapping(config or {}, "destination.config"),
            secret_refs=refs,
            enabled=_bool(enabled, "destination.enabled"),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "destination_id": self.destination_id,
            "name": self.name,
            "kind": self.kind,
            "config": copy.deepcopy(self.config),
            "secret_refs": dict(self.secret_refs),
            "enabled": self.enabled,
        }

    @classmethod
    def from_dict(cls, value: Any) -> Destination:
        data = _mapping(value, "destination")
        expected = {
            "destination_id",
            "name",
            "kind",
            "config",
            "secret_refs",
            "enabled",
        }
        _keys(data, expected, "destination", required={"destination_id", "name", "kind"})
        raw_refs = data.get("secret_refs", {})
        if not isinstance(raw_refs, Mapping):
            raise ValidationError("destination.secret_refs must be an object")
        refs = {}
        for key, raw in raw_refs.items():
            key = _string(key, "destination.secret_refs key")
            if not isinstance(raw, str):
                raise ValidationError(f"destination.secret_refs[{key!r}] must be a string")
            refs[key] = str(SecretRef.parse(raw))
        return cls(
            destination_id=validate_id(data["destination_id"], field="destination.destination_id"),
            name=validate_name(data["name"]),
            kind=_string(data["kind"], "destination.kind"),
            config=_mapping(data.get("config", {}), "destination.config"),
            secret_refs=refs,
            enabled=_bool(data.get("enabled", True), "destination.enabled"),
        )


@dataclass(frozen=True)
class ConfigPayload:
    tags: tuple[Tag, ...] = ()
    triggers: tuple[Trigger, ...] = ()
    variables: tuple[Variable, ...] = ()
    destinations: tuple[Destination, ...] = ()

    @classmethod
    def empty(cls) -> ConfigPayload:
        return cls()

    @classmethod
    def from_dict(cls, value: Any) -> ConfigPayload:
        data = _mapping(value, "payload")
        _keys(data, set(PAYLOAD_KEYS), "payload")
        return cls(
            tags=_mapping_tuple(data.get("tags", ()), "payload.tags", Tag),
            triggers=_mapping_tuple(data.get("triggers", ()), "payload.triggers", Trigger),
            variables=_mapping_tuple(data.get("variables", ()), "payload.variables", Variable),
            destinations=_mapping_tuple(
                data.get("destinations", ()), "payload.destinations", Destination
            ),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "tags": [tag.to_dict() for tag in self.tags],
            "triggers": [trigger.to_dict() for trigger in self.triggers],
            "variables": [variable.to_dict() for variable in self.variables],
            "destinations": [destination.to_dict() for destination in self.destinations],
        }

    def object_count(self) -> int:
        return len(self.tags) + len(self.triggers) + len(self.variables) + len(self.destinations)

    def all_objects(self):
        yield from (("tag", tag) for tag in self.tags)
        yield from (("trigger", trigger) for trigger in self.triggers)
        yield from (("variable", variable) for variable in self.variables)
        yield from (("destination", destination) for destination in self.destinations)
