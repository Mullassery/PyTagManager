"""Canonical JSON and checksums for immutable configuration revisions."""

from __future__ import annotations

import hashlib
import json
import math
from typing import Any

from pytagmanager.control.errors import ValidationError


def _check_json_value(value: Any, path: str) -> None:
    if value is None or isinstance(value, (bool, int, str)):
        return
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValidationError(f"{path} contains a non-finite number")
        return
    if isinstance(value, (list, tuple)):
        for index, item in enumerate(value):
            _check_json_value(item, f"{path}[{index}]")
        return
    if isinstance(value, dict):
        for key, item in value.items():
            if not isinstance(key, str):
                raise ValidationError(f"{path} contains a non-string key: {key!r}")
            _check_json_value(item, f"{path}.{key}")
        return
    raise ValidationError(f"{path} contains a non-JSON value of type {type(value).__name__}")


def canonical_json(value: Any) -> str:
    """Serialize a JSON value deterministically, rejecting non-finite numbers."""
    _check_json_value(value, "value")
    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    )


def sha256_hex(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def checksum(value: Any) -> str:
    """Return a prefixed SHA-256 checksum over canonical JSON."""
    return f"sha256:{sha256_hex(canonical_json(value))}"


def verify_checksum(value: Any, expected: str) -> bool:
    return checksum(value) == expected
