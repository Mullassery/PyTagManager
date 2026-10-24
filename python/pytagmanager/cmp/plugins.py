"""Declarative custom CMP adapter files.

Custom adapters are data, not code: a JSON file declares signatures, cookie
names and consent-control selectors. PyTagManager never imports or evaluates
Python/JavaScript from an adapter file, so adding a vendor does not grant the
file arbitrary code execution.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from pytagmanager.cmp.adapters import ADAPTERS, CmpAdapter

_ADAPTER_FILE_KEYS = frozenset({"schema_version", "adapters"})
_ADAPTER_KEYS = frozenset(
    {
        "adapter_id",
        "vendor",
        "contract_version",
        "script_markers",
        "url_markers",
        "markup_markers",
        "global_names",
        "cookie_names",
        "cookie_prefixes",
        "accept_selectors",
        "reject_selectors",
        "notes",
    }
)
_ADAPTER_ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9._-]{0,63}$")
_MAX_ADAPTERS = 100
_MAX_ITEMS = 100
_MAX_ITEM_LENGTH = 500


class AdapterFileError(ValueError):
    """Raised when a declarative adapter file is malformed or unsafe."""


def load_adapter_files(
    paths: Sequence[str | Path], *, reserved_ids: Sequence[str] = ()
) -> tuple[CmpAdapter, ...]:
    reserved = set(reserved_ids) or {adapter.adapter_id for adapter in ADAPTERS}
    loaded = []
    seen = set(reserved)
    for raw_path in paths:
        path = Path(raw_path)
        for adapter in load_adapter_file(path, reserved_ids=tuple(seen)):
            if adapter.adapter_id in seen:
                raise AdapterFileError(f"{path}: duplicate adapter_id {adapter.adapter_id!r}")
            seen.add(adapter.adapter_id)
            loaded.append(adapter)
    return tuple(loaded)


def load_adapter_file(
    path: str | Path, *, reserved_ids: Sequence[str] = ()
) -> tuple[CmpAdapter, ...]:
    resolved = Path(path)
    try:
        payload = json.loads(resolved.read_text(encoding="utf-8"))
    except OSError as exc:
        raise AdapterFileError(f"{resolved}: could not read adapter file: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise AdapterFileError(f"{resolved}: invalid JSON: {exc}") from exc

    if not isinstance(payload, dict):
        raise AdapterFileError(f"{resolved}: top-level value must be a JSON object")
    unknown = set(payload) - _ADAPTER_FILE_KEYS
    if unknown:
        raise AdapterFileError(
            f"{resolved}: unsupported top-level key(s): {', '.join(sorted(unknown))}"
        )
    if payload.get("schema_version") != 1:
        raise AdapterFileError(f"{resolved}: schema_version must be 1")
    raw_adapters = payload.get("adapters")
    if not isinstance(raw_adapters, list) or not raw_adapters:
        raise AdapterFileError(f"{resolved}: adapters must be a non-empty array")
    if len(raw_adapters) > _MAX_ADAPTERS:
        raise AdapterFileError(f"{resolved}: at most {_MAX_ADAPTERS} adapters are allowed")

    reserved = set(reserved_ids) or {adapter.adapter_id for adapter in ADAPTERS}
    result = []
    for index, raw in enumerate(raw_adapters):
        adapter = adapter_from_mapping(
            raw,
            location=f"{resolved}: adapters[{index}]",
            reserved_ids=reserved,
        )
        if adapter.adapter_id in reserved:
            raise AdapterFileError(
                f"{resolved}: adapters[{index}]: duplicate adapter_id {adapter.adapter_id!r}"
            )
        reserved.add(adapter.adapter_id)
        result.append(adapter)
    return tuple(result)


def adapter_from_mapping(
    raw: Mapping[str, Any],
    *,
    location: str = "adapter",
    reserved_ids: Sequence[str] = (),
) -> CmpAdapter:
    if not isinstance(raw, dict):
        raise AdapterFileError(f"{location}: adapter must be a JSON object")
    unknown = set(raw) - _ADAPTER_KEYS
    if unknown:
        raise AdapterFileError(f"{location}: unsupported key(s): {', '.join(sorted(unknown))}")

    adapter_id = raw.get("adapter_id")
    if not isinstance(adapter_id, str) or not _ADAPTER_ID_PATTERN.fullmatch(adapter_id):
        raise AdapterFileError(f"{location}: adapter_id must match {_ADAPTER_ID_PATTERN.pattern}")
    if adapter_id in set(reserved_ids):
        raise AdapterFileError(
            f"{location}: adapter_id {adapter_id!r} is reserved or already loaded"
        )

    vendor = raw.get("vendor")
    if not isinstance(vendor, str) or not vendor.strip():
        raise AdapterFileError(f"{location}: vendor must be a non-empty string")
    if len(vendor) > 200:
        raise AdapterFileError(f"{location}: vendor must be at most 200 characters")

    contract_version = raw.get("contract_version", "1")
    if not isinstance(contract_version, str) or not contract_version.strip():
        raise AdapterFileError(f"{location}: contract_version must be a non-empty string")

    adapter = CmpAdapter()
    adapter.adapter_id = adapter_id
    adapter.vendor = vendor.strip()
    adapter.contract_version = contract_version.strip()
    adapter.script_markers = _string_tuple(raw, "script_markers", location)
    adapter.url_markers = _string_tuple(raw, "url_markers", location)
    adapter.markup_markers = _string_tuple(raw, "markup_markers", location)
    adapter.global_names = _string_tuple(raw, "global_names", location)
    adapter.cookie_names = _string_tuple(raw, "cookie_names", location)
    adapter.cookie_prefixes = _string_tuple(raw, "cookie_prefixes", location)
    adapter.accept_selectors = _string_tuple(raw, "accept_selectors", location)
    adapter.reject_selectors = _string_tuple(raw, "reject_selectors", location)
    adapter.notes = _string_tuple(raw, "notes", location)
    adapter.supports_consent_api = False
    if not any(
        (
            adapter.script_markers,
            adapter.url_markers,
            adapter.markup_markers,
            adapter.global_names,
            adapter.cookie_names,
            adapter.cookie_prefixes,
        )
    ):
        raise AdapterFileError(f"{location}: at least one detection signature is required")
    return adapter


def _string_tuple(raw: Mapping[str, Any], field: str, location: str) -> tuple[str, ...]:
    value = raw.get(field, [])
    if value is None:
        return ()
    if not isinstance(value, list):
        raise AdapterFileError(f"{location}: {field} must be an array of strings")
    if len(value) > _MAX_ITEMS:
        raise AdapterFileError(f"{location}: {field} must contain at most {_MAX_ITEMS} items")
    result = []
    for index, item in enumerate(value):
        if not isinstance(item, str) or not item.strip():
            raise AdapterFileError(f"{location}: {field}[{index}] must be a non-empty string")
        if len(item) > _MAX_ITEM_LENGTH:
            raise AdapterFileError(
                f"{location}: {field}[{index}] exceeds {_MAX_ITEM_LENGTH} characters"
            )
        result.append(item.strip())
    return tuple(result)
