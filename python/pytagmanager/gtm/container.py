"""Read, inspect, and project GTM container exports.

GTM exports are JSON. The same document is valid YAML, so customers can keep
container snapshots in either representation. Loading is always safe: YAML is
parsed with ``safe_load`` and structured input is treated as untrusted data.
"""

from __future__ import annotations

import copy
import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping

from pytagmanager.control.config import ConfigPayload, Tag, Trigger, Variable
from pytagmanager.control.errors import ValidationError
from pytagmanager.control.ids import new_id, utc_now

_REF_RE = re.compile(r"\{\{\s*([^{}]+?)\s*\}\}")
_PATH_RE = re.compile(r"^[A-Za-z0-9_-]+(?:\.[A-Za-z0-9_-]+)*$")
_GA_MEASUREMENT_RE = re.compile(r"^G-[A-Z0-9]{4,}$")

_TRIGGER_MAP = {
    "PAGEVIEW": "page_view",
    "CUSTOM_EVENT": "custom_event",
    "CLICK": "click",
    "LINK_CLICK": "link_click",
    "FORM_SUBMISSION": "form_submit",
    "CONSENT_INIT": "consent_change",
}
_TRIGGER_REVERSE = {value: key for key, value in _TRIGGER_MAP.items()}
_TAG_MAP = {
    "gaawe": "ga4_event",
    "googtag": "ga4_config",
    "awct": "google_ads",
    "html": "custom_html",
}
_TAG_REVERSE = {value: key for key, value in _TAG_MAP.items()}

_BUILTIN_VARIABLES = {
    "Page URL",
    "Page Path",
    "Page Hostname",
    "Event",
    "Click Element",
    "Click URL",
    "Click Text",
    "Form Element",
    "Form URL",
    "Form Text",
    "Referrer",
    "Container ID",
    "Container Version",
    "Debug Mode",
    "Random Number",
    "HTML ID",
    "Event Name",
}


@dataclass(frozen=True)
class GtmFinding:
    code: str
    severity: str
    confidence: str
    message: str
    evidence: tuple[str, ...]
    remediation: str
    object_type: str
    object_ids: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "severity": self.severity,
            "confidence": self.confidence,
            "message": self.message,
            "evidence": list(self.evidence),
            "remediation": self.remediation,
            "object_type": self.object_type,
            "object_ids": list(self.object_ids),
        }


def _load_yaml(text: str) -> Any:
    try:
        import yaml
    except ImportError as exc:  # pragma: no cover - environment dependent
        raise ValidationError(
            "YAML input requires the optional PyYAML dependency "
            "(install pytagmanager[diagnostics])"
        ) from exc
    try:
        return yaml.safe_load(text)
    except Exception as exc:
        raise ValidationError(f"container YAML is invalid: {exc}") from exc


def load_container(path: str | Path) -> dict[str, Any]:
    source = Path(path)
    try:
        text = source.read_text(encoding="utf-8")
    except OSError as exc:
        raise ValidationError(f"cannot read container export: {exc}") from exc
    if not text.strip():
        raise ValidationError("container export is empty")
    document: Any
    try:
        document = json.loads(text)
    except json.JSONDecodeError:
        document = _load_yaml(text)
    if not isinstance(document, Mapping):
        raise ValidationError("container export must be an object")
    version = document.get("containerVersion", document)
    if not isinstance(version, Mapping):
        raise ValidationError("containerVersion must be an object")
    for field in ("tag", "trigger", "variable"):
        value = version.get(field, [])
        if value is not None and not isinstance(value, list):
            raise ValidationError(f"containerVersion.{field} must be a list")
    return copy.deepcopy(dict(document))


def _yaml_dump(document: Mapping[str, Any]) -> str:
    try:
        import yaml
    except ImportError as exc:  # pragma: no cover
        raise ValidationError(
            "YAML output requires PyYAML (install pytagmanager[diagnostics])"
        ) from exc
    return yaml.safe_dump(dict(document), sort_keys=False, allow_unicode=True)


def write_container(document: Mapping[str, Any], path: str | Path, *, format: str | None = None) -> Path:
    target = Path(path)
    selected = (format or target.suffix.lstrip(".") or "json").lower()
    if selected not in {"json", "yaml", "yml"}:
        raise ValidationError("container output format must be json or yaml")
    text = (
        json.dumps(document, indent=2, ensure_ascii=False) + "\n"
        if selected == "json"
        else _yaml_dump(document)
    )
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8")
    return target


def _version(document: Mapping[str, Any]) -> Mapping[str, Any]:
    value = document.get("containerVersion", document)
    return value if isinstance(value, Mapping) else {}


def _items(version: Mapping[str, Any], key: str) -> list[Mapping[str, Any]]:
    value = version.get(key, [])
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, Mapping)]


def _params(item: Mapping[str, Any]) -> dict[str, Any]:
    raw = item.get("parameter", item.get("parameters", {}))
    if isinstance(raw, Mapping):
        return {str(key): value for key, value in raw.items()}
    result: dict[str, Any] = {}
    if isinstance(raw, list):
        for entry in raw:
            if isinstance(entry, Mapping) and isinstance(entry.get("key"), str):
                result[entry["key"]] = entry.get("value")
    return result


def _param_list(parameters: Mapping[str, Any]) -> list[dict[str, str]]:
    result = []
    for key, value in parameters.items():
        if isinstance(value, (dict, list)):
            rendered = json.dumps(value, ensure_ascii=False)
        elif isinstance(value, bool):
            rendered = "true" if value else "false"
        elif value is None:
            rendered = ""
        else:
            rendered = str(value)
        result.append({"key": str(key), "value": rendered})
    return result


def _refs(value: Any) -> set[str]:
    found: set[str] = set()
    if isinstance(value, str):
        found.update(match.strip() for match in _REF_RE.findall(value))
    elif isinstance(value, Mapping):
        for item in value.values():
            found.update(_refs(item))
    elif isinstance(value, (list, tuple)):
        for item in value:
            found.update(_refs(item))
    return found


def _event_trigger_conditions(trigger: Mapping[str, Any]) -> dict[str, Any]:
    filters = trigger.get("customEventFilter")
    if isinstance(filters, list):
        conditions = []
        for entry in filters:
            if not isinstance(entry, Mapping):
                continue
            params = _params(entry)
            if params.get("arg0") == "{{_event}}" and entry.get("type") == "EQUALS":
                conditions.append(
                    {"op": "equals", "path": "event.name", "value": params.get("arg1")}
                )
        if conditions:
            return {"op": "all", "conditions": conditions}
    return {"op": "all", "conditions": []}


def analyze_container(document: Mapping[str, Any]) -> list[GtmFinding]:
    version = _version(document)
    tags = _items(version, "tag")
    triggers = _items(version, "trigger")
    variables = _items(version, "variable")
    builtins = {
        str(item.get("type"))
        for item in _items(version, "builtInVariable")
        if isinstance(item.get("type"), str)
    }
    variable_names = {
        str(item.get("name")) for item in variables if item.get("name") is not None
    }
    known_refs = {name.replace("_", " ") for name in variable_names} | _BUILTIN_VARIABLES | builtins
    findings: list[GtmFinding] = []

    tag_names: dict[str, list[str]] = {}
    trigger_names: dict[str, list[str]] = {}
    for tag in tags:
        name = str(tag.get("name", "")).casefold()
        if name:
            tag_names.setdefault(name, []).append(str(tag.get("tagId", "")))
    for trigger in triggers:
        name = str(trigger.get("name", "")).casefold()
        if name:
            trigger_names.setdefault(name, []).append(str(trigger.get("triggerId", "")))
    for name, ids in tag_names.items():
        if len(ids) > 1:
            findings.append(
                GtmFinding(
                    "duplicate_tag_name",
                    "medium",
                    "confirmed",
                    f"Multiple tags share the name {name!r}.",
                    tuple(f"tagId={item}" for item in ids),
                    "Give each tag a unique name before editing so reviews and exports are unambiguous.",
                    "tag",
                    tuple(ids),
                )
            )
    for name, ids in trigger_names.items():
        if len(ids) > 1:
            findings.append(
                GtmFinding(
                    "duplicate_trigger_name",
                    "low",
                    "confirmed",
                    f"Multiple triggers share the name {name!r}.",
                    tuple(f"triggerId={item}" for item in ids),
                    "Rename or consolidate duplicate triggers; verify no tag depends on both.",
                    "trigger",
                    tuple(ids),
                )
            )

    tags_by_id = {str(tag.get("tagId")): tag for tag in tags if tag.get("tagId") is not None}
    trigger_ids = {str(trigger.get("triggerId")) for trigger in triggers}
    tags_using_trigger: dict[str, list[str]] = {}
    ga4_event_owners: dict[tuple[str, str], list[str]] = {}
    measurements: dict[str, list[str]] = {}

    for tag in tags:
        tag_id = str(tag.get("tagId", ""))
        firing = tag.get("firingTriggerId", tag.get("firingTriggerIds", []))
        if not isinstance(firing, list):
            firing = [firing] if firing else []
        if not firing:
            findings.append(
                GtmFinding(
                    "tag_without_trigger",
                    "high",
                    "confirmed",
                    f"Tag {tag.get('name')!r} has no firing trigger and cannot fire.",
                    (f"tagId={tag_id}", f"type={tag.get('type')}"),
                    "Attach the intended trigger after confirming the expected event or page condition.",
                    "tag",
                    (tag_id,),
                )
            )
        for trigger_id in firing:
            key = str(trigger_id)
            tags_using_trigger.setdefault(key, []).append(tag_id)
            if key not in trigger_ids:
                findings.append(
                    GtmFinding(
                        "dangling_trigger_reference",
                        "high",
                        "confirmed",
                        f"Tag {tag.get('name')!r} references missing trigger {key!r}.",
                        (f"tagId={tag_id}", f"triggerId={key}"),
                        "Restore or remove the missing trigger reference; re-import and validate the container.",
                        "tag",
                        (tag_id,),
                    )
                )
        if bool(tag.get("paused")):
            findings.append(
                GtmFinding(
                    "paused_tag",
                    "informational",
                    "confirmed",
                    f"Tag {tag.get('name')!r} is paused.",
                    (f"tagId={tag_id}",),
                    "Confirm the pause is intentional; a paused tag will not explain missing events.",
                    "tag",
                    (tag_id,),
                )
            )
        params = _params(tag)
        unresolved = sorted(
            ref for ref in _refs(params) if ref not in known_refs and ref not in builtins
        )
        for ref in unresolved:
            findings.append(
                GtmFinding(
                    "unresolved_variable",
                    "high",
                    "high-confidence",
                    f"Tag {tag.get('name')!r} references undefined variable {{{{{ref}}}}}.",
                    (f"tagId={tag_id}", f"variable={ref}"),
                    f"Create the GTM variable {ref!r}, fix the reference spelling, or remove the parameter.",
                    "tag",
                    (tag_id,),
                )
            )
        tag_type = str(tag.get("type", ""))
        event_name = params.get("eventName", params.get("event"))
        if tag_type == "gaawe":
            if not event_name:
                findings.append(
                    GtmFinding(
                        "ga4_event_missing_name",
                        "high",
                        "confirmed",
                        f"GA4 event tag {tag.get('name')!r} has no eventName parameter.",
                        (f"tagId={tag_id}",),
                        "Set the GA4 event name or replace the tag with the intended event configuration.",
                        "tag",
                        (tag_id,),
                    )
                )
            elif isinstance(event_name, str):
                key = (str(event_name), str(firing))
                ga4_event_owners.setdefault(key, []).append(tag_id)
        measurement = params.get("measurementId") or params.get("measurementIdOverride") or params.get("tagId")
        if isinstance(measurement, str) and _GA_MEASUREMENT_RE.fullmatch(measurement):
            measurements.setdefault(measurement, []).append(tag_id)

    for trigger in triggers:
        trigger_id = str(trigger.get("triggerId", ""))
        if trigger_id and trigger_id not in tags_using_trigger and not bool(trigger.get("paused")):
            findings.append(
                GtmFinding(
                    "trigger_without_tag",
                    "low",
                    "confirmed",
                    f"Trigger {trigger.get('name')!r} is not used by any tag.",
                    (f"triggerId={trigger_id}", f"type={trigger.get('type')}"),
                    "Remove unused triggers only after confirming no intended tag is missing.",
                    "trigger",
                    (trigger_id,),
                )
            )

    for (event_name, firing), owners in ga4_event_owners.items():
        if len(owners) > 1:
            findings.append(
                GtmFinding(
                    "duplicate_ga4_event_delivery",
                    "high",
                    "high-confidence",
                    f"Multiple GA4 event tags send {event_name!r} on the same trigger set.",
                    tuple(f"tagId={item}" for item in owners),
                    "Consolidate the tags or give them distinct triggers; otherwise the same event may be sent twice.",
                    "tag",
                    tuple(owners),
                )
            )
    for measurement, owners in measurements.items():
        unique = sorted(set(owners))
        if len(unique) > 1:
            findings.append(
                GtmFinding(
                    "duplicate_measurement_id",
                    "medium",
                    "high-confidence",
                    f"Measurement ID {measurement!r} is configured on multiple tags.",
                    tuple(f"tagId={item}" for item in unique),
                    "Confirm the duplication is intentional, then consolidate shared configuration.",
                    "tag",
                    tuple(unique),
                )
            )

    return findings


def _gtm_trigger_type(value: str) -> str:
    return _TRIGGER_MAP.get(value.upper(), "custom_event")


def _gtm_variable(variable: Mapping[str, Any]) -> Variable | None:
    raw_type = str(variable.get("type", ""))
    name = str(variable.get("name", "")).strip()
    if not name:
        return None
    params = _params(variable)
    if raw_type == "v":
        ref = name.split(" - ")[-1].strip()
        if not _PATH_RE.fullmatch(ref):
            return None
        source = "data_layer"
        source_ref: Any = ref
    elif raw_type == "c":
        source = "static"
        source_ref = None
    elif raw_type == "u":
        source = "page_url"
        source_ref = None
    else:
        return None
    return Variable.create(
        name=name,
        type="string",
        source=source,
        source_ref=source_ref,
        default=params.get("value") if raw_type == "c" else None,
        enabled=True,
    )


def gtm_to_payload(document: Mapping[str, Any]) -> tuple[ConfigPayload, list[str]]:
    """Best-effort import of a GTM export into a draft control payload.

    Unsupported conditions/variables are preserved only as warnings; nothing is
    activated. This function intentionally refuses to invent semantics for
    triggers or variables it cannot represent.
    """
    version = _version(document)
    warnings: list[str] = []
    trigger_ids: dict[str, str] = {}
    variable_ids: dict[str, str] = {}
    triggers: list[Trigger] = []
    variables: list[Variable] = []
    tags: list[Tag] = []

    for raw in _items(version, "variable"):
        variable = _gtm_variable(raw)
        if variable is None:
            warnings.append(f"variable {raw.get('name')!r} ({raw.get('type')!r}) was not imported")
            continue
        variable_ids[str(raw.get("variableId", raw.get("name")))] = variable.variable_id
        variables.append(variable)

    for raw in _items(version, "trigger"):
        gtm_type = str(raw.get("type", ""))
        if gtm_type.upper() not in _TRIGGER_MAP:
            warnings.append(f"trigger {raw.get('name')!r} type {gtm_type!r} mapped to custom_event")
        conditions = _event_trigger_conditions(raw)
        if not conditions["conditions"] and gtm_type.upper() not in {"PAGEVIEW", "CUSTOM_EVENT"}:
            warnings.append(
                f"trigger {raw.get('name')!r} conditions are not fully representable; raw GTM data is retained"
            )
        trigger = Trigger.create(
            name=str(raw.get("name") or f"Imported trigger {raw.get('triggerId')}"),
            type=_gtm_trigger_type(gtm_type),
            conditions=conditions,
            enabled=not bool(raw.get("paused")),
        )
        trigger_ids[str(raw.get("triggerId", raw.get("name")))] = trigger.trigger_id
        triggers.append(trigger)

    for raw in _items(version, "tag"):
        name = str(raw.get("name") or f"Imported tag {raw.get('tagId')}")
        gtm_type = str(raw.get("type", ""))
        if gtm_type not in _TAG_MAP:
            warnings.append(f"tag {name!r} type {gtm_type!r} imported as gtm:{gtm_type}")
        params = _params(raw)
        refs = _refs(params)
        mapped_variables = []
        for ref in refs:
            if ref in variable_ids:
                mapped_variables.append(variable_ids[ref])
            elif ref not in _BUILTIN_VARIABLES:
                warnings.append(f"tag {name!r} references unimported variable {ref!r}")
        firing = raw.get("firingTriggerId", raw.get("firingTriggerIds", []))
        if not isinstance(firing, list):
            firing = [firing] if firing else []
        mapped_triggers = []
        for trigger_id in firing:
            mapped = trigger_ids.get(str(trigger_id))
            if mapped is None:
                warnings.append(f"tag {name!r} references unknown trigger {trigger_id!r}")
            else:
                mapped_triggers.append(mapped)
        tags.append(
            Tag.create(
                name=name,
                type=_TAG_MAP.get(gtm_type, f"gtm:{gtm_type}"),
                parameters=params,
                trigger_ids=mapped_triggers,
                variable_ids=mapped_variables,
                enabled=not bool(raw.get("paused")),
                compatibility={"gtm": {"format_version": document.get("exportFormatVersion", 2)}},
                source_evidence={"system": "gtm", "tag_id": raw.get("tagId")},
            )
        )

    return ConfigPayload(
        tags=tuple(tags),
        triggers=tuple(triggers),
        variables=tuple(variables),
    ), warnings


def payload_to_gtm(payload: ConfigPayload) -> dict[str, Any]:
    trigger_ids = {trigger.trigger_id: str(index) for index, trigger in enumerate(payload.triggers, 1)}
    variable_ids = {variable.variable_id: str(index) for index, variable in enumerate(payload.variables, 1)}
    tags = []
    for index, tag in enumerate(payload.tags, 1):
        tags.append(
            {
                "accountId": "0",
                "containerId": "0",
                "tagId": str(index),
                "name": tag.name,
                "type": _TAG_REVERSE.get(tag.type, tag.type),
                "parameter": _param_list(tag.parameters),
                "firingTriggerId": [trigger_ids[item] for item in tag.trigger_ids if item in trigger_ids],
                "firingRuleId": [],
                "blockingTriggerId": [],
                "tagFiringOption": "oncePerEvent",
                "paused": not tag.enabled,
                "notes": tag.description,
            }
        )
    triggers = []
    for index, trigger in enumerate(payload.triggers, 1):
        item = {
            "accountId": "0",
            "containerId": "0",
            "triggerId": str(index),
            "name": trigger.name,
            "type": _TRIGGER_REVERSE.get(trigger.type, trigger.type.upper()),
        }
        if trigger.type == "custom_event":
            conditions = trigger.conditions.get("conditions", [])
            filters = []
            for condition in conditions if isinstance(conditions, list) else []:
                if condition.get("path") == "event.name":
                    filters.append(
                        {
                            "type": "EQUALS",
                            "parameter": [
                                {"key": "arg0", "value": "{{_event}}"},
                                {"key": "arg1", "value": str(condition.get("value", ""))},
                            ],
                        }
                    )
            if filters:
                item["customEventFilter"] = filters
        if not trigger.enabled:
            item["paused"] = True
        triggers.append(item)
    variables = []
    for index, variable in enumerate(payload.variables, 1):
        if variable.source == "data_layer":
            raw_type = "v"
            params = [
                {"key": "dataLayerVersion", "value": "2"},
                {"key": "setDefaultValue", "value": "false"},
            ]
        elif variable.source == "static":
            raw_type = "c"
            params = [{"key": "value", "value": str(variable.default if variable.default is not None else "")}]
        elif variable.source in {"page_url", "page_path", "page_title", "referrer"}:
            raw_type = "u"
            params = []
        else:
            raw_type = "jsm"
            params = [{"key": "javascript", "value": str(variable.source_ref or "")}]
        variables.append(
            {
                "accountId": "0",
                "containerId": "0",
                "variableId": str(index),
                "name": variable.name,
                "type": raw_type,
                "parameter": params,
            }
        )
    return {
        "exportFormatVersion": 2,
        "exportTime": utc_now(),
        "containerVersion": {
            "accountId": "0",
            "containerId": "0",
            "containerVersionId": "0",
            "tag": tags,
            "trigger": triggers,
            "variable": variables,
            "folder": [],
            "builtInVariable": [
                {"type": "PAGE_URL", "name": "Page URL"},
                {"type": "PAGE_PATH", "name": "Page Path"},
                {"type": "PAGE_HOSTNAME", "name": "Page Hostname"},
                {"type": "EVENT", "name": "Event"},
            ],
            "notes": "Exported by PyTagManager. Review before importing into GTM.",
        },
    }
