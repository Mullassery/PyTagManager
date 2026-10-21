"""Declarative condition AST with bounded depth and no ``eval``.

Missing-path rules are explicit: ``exists`` is false when a path is absent;
all other comparison operators are false for a missing value (including
``in``). ``equals`` compares null to null as true and uses strict type
comparison otherwise (``True`` is not equal to ``1``).
"""

from __future__ import annotations

import copy
from typing import Any, Mapping

from pytagmanager.control._sentinels import MISSING
from pytagmanager.control.checksums import canonical_json
from pytagmanager.control.errors import ValidationError

MAX_CONDITION_DEPTH = 32
MAX_CONDITION_NODES = 512
MAX_CONDITION_BYTES = 65536
MAX_PATH_LENGTH = 256
ALLOWED_NAMESPACES = frozenset({"event", "page", "dom", "data_layer", "consent", "variables"})
_LOGICAL_OPS = frozenset({"all", "any", "not"})
_COMPARISON_OPS = frozenset(
    {"equals", "contains", "starts_with", "matches_glob", "gt", "gte", "lt", "lte", "in"}
)
_STRING_OPS = frozenset({"starts_with", "matches_glob"})
_NUMERIC_OPS = frozenset({"gt", "gte", "lt", "lte"})


def _validate_path(path: Any) -> str:
    if not isinstance(path, str) or not path or len(path) > MAX_PATH_LENGTH:
        raise ValidationError(f"condition path must be a non-empty string up to {MAX_PATH_LENGTH} characters")
    parts = path.split(".")
    if any(not part or "__" in part for part in parts):
        raise ValidationError(f"condition path is malformed: {path!r}")
    if parts[0] not in ALLOWED_NAMESPACES:
        raise ValidationError(
            f"condition path must start with one of {sorted(ALLOWED_NAMESPACES)}, got {path!r}"
        )
    for part in parts:
        if not all(character.isalnum() or character in "_-" for character in part):
            raise ValidationError(f"condition path contains an unsafe segment: {part!r}")
    return path


def _check_keys(value: Mapping[str, Any], expected: set[str], field: str) -> None:
    unknown = sorted(set(value) - expected)
    missing = sorted(expected - set(value))
    if unknown:
        raise ValidationError(f"{field} contains unknown field(s): {', '.join(unknown)}")
    if missing:
        raise ValidationError(f"{field} is missing field(s): {', '.join(missing)}")


def _validate_value(value: Any, op: str) -> Any:
    canonical_json(value)
    if op in _STRING_OPS and not isinstance(value, str):
        raise ValidationError(f"condition '{op}' requires a string value")
    if op in _NUMERIC_OPS:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValidationError(f"condition '{op}' requires a numeric value")
    if op == "in" and not isinstance(value, (list, tuple)):
        raise ValidationError("condition 'in' requires a list value")
    if op == "contains" and not isinstance(value, (str, list, tuple)):
        raise ValidationError("condition 'contains' requires a string or list value")
    return copy.deepcopy(value)


def _validate(value: Any, depth: int, counter: list[int]) -> dict[str, Any]:
    counter[0] += 1
    if counter[0] > MAX_CONDITION_NODES:
        raise ValidationError("condition AST exceeds the node limit")
    if depth > MAX_CONDITION_DEPTH:
        raise ValidationError("condition AST exceeds the depth limit")
    if not isinstance(value, Mapping):
        raise ValidationError("condition nodes must be objects")
    op = value.get("op")
    if not isinstance(op, str) or not op:
        raise ValidationError("condition node is missing a valid 'op'")

    if op in _LOGICAL_OPS:
        _check_keys(value, {"op", "conditions"}, "condition")
        children = value["conditions"]
        if not isinstance(children, (list, tuple)):
            raise ValidationError(f"condition '{op}' requires a conditions list")
        if op == "not" and len(children) != 1:
            raise ValidationError("condition 'not' requires exactly one child")
        return {
            "op": op,
            "conditions": [_validate(child, depth + 1, counter) for child in children],
        }
    if op == "exists":
        _check_keys(value, {"op", "path"}, "condition")
        return {"op": "exists", "path": _validate_path(value["path"])}
    if op in _COMPARISON_OPS:
        _check_keys(value, {"op", "path", "value"}, "condition")
        return {
            "op": op,
            "path": _validate_path(value["path"]),
            "value": _validate_value(value["value"], op),
        }
    raise ValidationError(f"unsupported condition op: {op!r}")


def validate_condition(value: Any) -> dict[str, Any]:
    """Validate and normalize a condition AST."""
    counter = [0]
    normalized = _validate(value, 0, counter)
    if len(canonical_json(normalized).encode("utf-8")) > MAX_CONDITION_BYTES:
        raise ValidationError("condition AST exceeds the size limit")
    return normalized


def resolve_path(context: Mapping[str, Any], path: str) -> Any:
    current: Any = context
    for part in path.split("."):
        if isinstance(current, Mapping):
            if part not in current:
                return MISSING
            current = current[part]
        elif isinstance(current, (list, tuple)):
            if not part.isdigit() or int(part) >= len(current):
                return MISSING
            current = current[int(part)]
        else:
            return MISSING
    return current


def _strict_equal(actual: Any, expected: Any) -> bool:
    if actual is MISSING:
        return False
    if actual is None or expected is None:
        return actual is expected
    if isinstance(actual, bool) or isinstance(expected, bool):
        return actual is expected
    if isinstance(actual, (int, float)) and isinstance(expected, (int, float)):
        return actual == expected
    if type(actual) is not type(expected):
        return False
    return actual == expected


def pattern_matches(pattern: str, value: str) -> bool:
    """PyTagShield-compatible ``*`` / ``?`` wildcard matching."""
    pattern_chars = list(pattern)
    value_chars = list(value)
    pattern_index = 0
    value_index = 0
    star_index: int | None = None
    star_value_index = 0

    while value_index < len(value_chars):
        if pattern_index < len(pattern_chars) and (
            pattern_chars[pattern_index] == "?" or pattern_chars[pattern_index] == value_chars[value_index]
        ):
            pattern_index += 1
            value_index += 1
        elif pattern_index < len(pattern_chars) and pattern_chars[pattern_index] == "*":
            star_index = pattern_index
            pattern_index += 1
            star_value_index = value_index
        elif star_index is not None:
            pattern_index = star_index + 1
            star_value_index += 1
            value_index = star_value_index
        else:
            return False
    while pattern_index < len(pattern_chars) and pattern_chars[pattern_index] == "*":
        pattern_index += 1
    return pattern_index == len(pattern_chars)


def _number(value: Any) -> bool:
    return not isinstance(value, bool) and isinstance(value, (int, float))


def evaluate_condition(condition: Mapping[str, Any], context: Mapping[str, Any]) -> bool:
    op = condition.get("op")
    if op == "all":
        return all(evaluate_condition(child, context) for child in condition["conditions"])
    if op == "any":
        return any(evaluate_condition(child, context) for child in condition["conditions"])
    if op == "not":
        return not evaluate_condition(condition["conditions"][0], context)
    if op == "exists":
        return resolve_path(context, condition["path"]) is not MISSING

    actual = resolve_path(context, condition["path"])
    expected = condition["value"]
    if op == "equals":
        return _strict_equal(actual, expected)
    if op == "in":
        return actual is not MISSING and any(_strict_equal(actual, item) for item in expected)
    if op == "contains":
        if actual is MISSING:
            return False
        if isinstance(actual, str) and isinstance(expected, str):
            return expected in actual
        if isinstance(actual, (list, tuple)):
            return any(_strict_equal(item, expected) for item in actual)
        return False
    if op == "starts_with":
        return isinstance(actual, str) and isinstance(expected, str) and actual.startswith(expected)
    if op == "matches_glob":
        return isinstance(actual, str) and isinstance(expected, str) and pattern_matches(expected, actual)
    if op in _NUMERIC_OPS:
        if actual is MISSING or not _number(actual) or not _number(expected):
            return False
        if op == "gt":
            return actual > expected
        if op == "gte":
            return actual >= expected
        if op == "lt":
            return actual < expected
        return actual <= expected
    return False
