"""Versioned Solution Design Reference (SDR) parsing for runtime validation."""

from __future__ import annotations

import csv
import json
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

SDR_SCHEMA_VERSION = 1
SUPPORTED_TYPES = frozenset({"any", "string", "number", "integer", "boolean", "array", "object"})
_TYPE_ALIASES = {
    "str": "string",
    "text": "string",
    "float": "number",
    "int": "integer",
    "bool": "boolean",
    "list": "array",
    "dict": "object",
}


class SdrFormatError(ValueError):
    """Raised when an SDR file cannot be parsed into the v1 contract."""


@dataclass(frozen=True)
class SdrParameter:
    name: str
    types: tuple[str, ...] = ("any",)
    required: bool = True
    allowed: tuple[Any, ...] = ()


@dataclass(frozen=True)
class SdrEvent:
    event_name: str
    parameters: tuple[SdrParameter, ...] = ()
    page_contains: str = ""
    selector: str = ""
    require_network: bool = False


@dataclass(frozen=True)
class SdrSchema:
    name: str
    events: tuple[SdrEvent, ...]


def _normalize_header(value: str) -> str:
    return value.strip().lower().replace(" ", "_").replace("-", "_")


def _as_bool(value: Any, *, field: str) -> bool:
    if isinstance(value, bool):
        return value
    if value is None or value == "":
        return False
    text = str(value).strip().lower()
    if text in {"1", "true", "yes", "y"}:
        return True
    if text in {"0", "false", "no", "n"}:
        return False
    raise SdrFormatError(f"{field} must be a boolean, got {value!r}")


def _types(value: Any) -> tuple[str, ...]:
    if value is None or value == "":
        return ("any",)
    raw = value if isinstance(value, (list, tuple)) else str(value).replace(",", "|").split("|")
    normalized = []
    for item in raw:
        text = str(item).strip().lower().replace(" ", "_")
        text = _TYPE_ALIASES.get(text, text)
        if text not in SUPPORTED_TYPES:
            raise SdrFormatError(f"unsupported SDR parameter type: {item!r}")
        normalized.append(text)
    if not normalized or "any" in normalized:
        return ("any",)
    return tuple(dict.fromkeys(normalized))


def _allowed(value: Any) -> tuple[Any, ...]:
    if value is None or value == "":
        return ()
    if isinstance(value, (list, tuple)):
        return tuple(value)
    text = str(value)
    if "|" in text:
        parts = text.split("|")
    elif ";" in text:
        parts = text.split(";")
    else:
        parts = [text]
    return tuple(part.strip() for part in parts if part.strip())


def _merge_event(
    events: dict[str, dict[str, Any]],
    row: Mapping[str, Any],
    *,
    row_number: int,
) -> None:
    event_name = str(row.get("event_name") or row.get("event") or "").strip()
    if not event_name:
        raise SdrFormatError(f"row {row_number}: event_name is required")
    event = events.setdefault(
        event_name,
        {
            "event_name": event_name,
            "parameters": [],
            "page_contains": "",
            "selector": "",
            "require_network": False,
        },
    )
    for key in ("page_contains", "selector"):
        value = str(
            row.get(key) or (row.get("page") if key == "page_contains" else "") or ""
        ).strip()
        if value:
            if event[key] and event[key] != value:
                raise SdrFormatError(
                    f"row {row_number}: conflicting {key} for event {event_name!r}"
                )
            event[key] = value
    if row.get("require_network") not in (None, ""):
        event["require_network"] = _as_bool(row["require_network"], field="require_network")

    parameter_name = str(
        row.get("parameter_name")
        or row.get("parameter")
        or row.get("variable_name")
        or row.get("name")
        or ""
    ).strip()
    if not parameter_name:
        return
    if any(item["name"] == parameter_name for item in event["parameters"]):
        raise SdrFormatError(
            f"row {row_number}: duplicate parameter {parameter_name!r} for event {event_name!r}"
        )
    raw_required = row.get("required")
    required = True if raw_required in (None, "") else _as_bool(raw_required, field="required")
    event["parameters"].append(
        {
            "name": parameter_name,
            "types": _types(row.get("type") or row.get("data_type")),
            "required": required,
            "allowed": _allowed(row.get("allowed_values") or row.get("allowed")),
        }
    )


def _json_rows(events: list[Any]) -> Iterable[Mapping[str, Any]]:
    for index, event in enumerate(events, start=1):
        if not isinstance(event, Mapping):
            raise SdrFormatError(f"event {index}: event must be an object")
        base = {key: value for key, value in event.items() if key not in {"parameters", "params"}}
        parameters = event.get("parameters", event.get("params", []))
        if parameters in (None, ""):
            parameters = []
        if not isinstance(parameters, list):
            raise SdrFormatError(f"event {index}: parameters must be an array")
        if not parameters:
            yield base
            continue
        for parameter in parameters:
            if not isinstance(parameter, Mapping):
                raise SdrFormatError(f"event {index}: each parameter must be an object")
            yield {**base, **parameter}


def _schema_from_rows(
    name: str,
    rows: Iterable[Mapping[str, Any]],
) -> SdrSchema:
    events: dict[str, dict[str, Any]] = {}
    for index, row in enumerate(rows, start=2):
        if not isinstance(row, Mapping):
            raise SdrFormatError(f"row {index}: event must be an object")
        _merge_event(events, row, row_number=index)
    if not events:
        raise SdrFormatError("SDR contains no events")
    return SdrSchema(
        name=name,
        events=tuple(
            SdrEvent(
                event_name=item["event_name"],
                parameters=tuple(
                    SdrParameter(
                        name=parameter["name"],
                        types=parameter["types"],
                        required=parameter["required"],
                        allowed=parameter["allowed"],
                    )
                    for parameter in item["parameters"]
                ),
                page_contains=item["page_contains"],
                selector=item["selector"],
                require_network=item["require_network"],
            )
            for item in events.values()
        ),
    )


def _load_json(path: Path) -> SdrSchema:
    try:
        document = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SdrFormatError(f"cannot read SDR JSON: {exc}") from exc
    if isinstance(document, list):
        events = document
        name = path.stem
        version = SDR_SCHEMA_VERSION
    elif isinstance(document, Mapping):
        version = document.get("schema_version", SDR_SCHEMA_VERSION)
        events = document.get("events")
        name = str(document.get("name") or path.stem)
    else:
        raise SdrFormatError("SDR JSON must be an object or an array of events")
    if str(version) != str(SDR_SCHEMA_VERSION):
        raise SdrFormatError(f"unsupported SDR schema_version: {version!r}")
    if not isinstance(events, list):
        raise SdrFormatError("SDR JSON must contain an events array")
    return _schema_from_rows(name, _json_rows(events))


def _load_csv(path: Path) -> SdrSchema:
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            if reader.fieldnames is None:
                raise SdrFormatError("SDR CSV is empty")
            fieldnames = [_normalize_header(name) for name in reader.fieldnames]
            if "event_name" not in fieldnames and "event" not in fieldnames:
                raise SdrFormatError("SDR CSV requires an event_name or event column")
            reader.fieldnames = fieldnames
            rows = list(reader)
    except OSError as exc:
        raise SdrFormatError(f"cannot read SDR CSV: {exc}") from exc
    return _schema_from_rows(path.stem, rows)


def load_sdr(path: str | Path) -> SdrSchema:
    source = Path(path)
    if source.suffix.lower() == ".csv":
        return _load_csv(source)
    if source.suffix.lower() in {".json", ""}:
        return _load_json(source)
    raise SdrFormatError("SDR must use .json or .csv")
