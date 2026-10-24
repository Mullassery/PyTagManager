"""Bounded, declarative computed-variable expressions. No ``eval``."""

from __future__ import annotations

import copy
import json
import math
import re
from collections.abc import Callable, Mapping
from typing import Any

from pytagmanager.control._sentinels import MISSING
from pytagmanager.control.checksums import canonical_json
from pytagmanager.control.errors import ValidationError
from pytagmanager.control.ids import validate_id

MAX_EXPRESSION_DEPTH = 16
MAX_EXPRESSION_NODES = 128
MAX_EXPRESSION_BYTES = 32768

_UNARY_OPS = frozenset({"to_number", "to_string", "to_boolean", "json_parse", "length"})
_INTEGER_RE = re.compile(r"^[+-]?[0-9]+$")


class ExpressionError(Exception):
    """A computed expression could not be evaluated safely."""


def _keys(value: Mapping[str, Any], expected: set[str], field: str) -> None:
    unknown = sorted(set(value) - expected)
    missing = sorted(expected - set(value))
    if unknown:
        raise ValidationError(f"{field} contains unknown field(s): {', '.join(unknown)}")
    if missing:
        raise ValidationError(f"{field} is missing field(s): {', '.join(missing)}")


def _depth(value: Any, current: int = 0) -> int:
    if isinstance(value, Mapping):
        return max([current] + [_depth(item, current + 1) for item in value.values()])
    if isinstance(value, (list, tuple)):
        return max([current] + [_depth(item, current + 1) for item in value])
    return current


def _validate(value: Any, depth: int, counter: list[int]) -> dict[str, Any]:
    counter[0] += 1
    if counter[0] > MAX_EXPRESSION_NODES:
        raise ValidationError("computed expression exceeds the node limit")
    if depth > MAX_EXPRESSION_DEPTH:
        raise ValidationError("computed expression exceeds the depth limit")
    if not isinstance(value, Mapping):
        raise ValidationError("computed expression nodes must be objects")
    op = value.get("op")
    if not isinstance(op, str) or not op:
        raise ValidationError("computed expression is missing a valid 'op'")

    if op == "literal":
        _keys(value, {"op", "value"}, "computed expression")
        canonical_json(value["value"])
        return {"op": "literal", "value": copy.deepcopy(value["value"])}
    if op == "variable":
        _keys(value, {"op", "id"}, "computed expression")
        return {"op": "variable", "id": validate_id(value["id"], field="variable id")}
    if op in {"coalesce", "concat"}:
        _keys(value, {"op", "args"}, "computed expression")
        args = value["args"]
        if not isinstance(args, (list, tuple)) or not args:
            raise ValidationError(f"computed '{op}' requires a non-empty args list")
        if len(args) > 64:
            raise ValidationError(f"computed '{op}' exceeds the argument limit")
        return {
            "op": op,
            "args": [_validate(item, depth + 1, counter) for item in args],
        }
    if op in _UNARY_OPS:
        _keys(value, {"op", "arg"}, "computed expression")
        return {"op": op, "arg": _validate(value["arg"], depth + 1, counter)}
    raise ValidationError(f"unsupported computed expression op: {op!r}")


def validate_expression(value: Any) -> dict[str, Any]:
    """Validate and normalize a computed-variable expression AST."""
    counter = [0]
    normalized = _validate(value, 0, counter)
    if _depth(normalized) > MAX_EXPRESSION_DEPTH:
        raise ValidationError("computed expression exceeds the depth limit")
    if len(canonical_json(normalized).encode("utf-8")) > MAX_EXPRESSION_BYTES:
        raise ValidationError("computed expression exceeds the size limit")
    return normalized


def iter_variable_ids(expression: Any):
    if not isinstance(expression, Mapping):
        return
    if expression.get("op") == "variable" and isinstance(expression.get("id"), str):
        yield expression["id"]
    for key in ("arg",):
        if key in expression:
            yield from iter_variable_ids(expression[key])
    for key in ("args",):
        if isinstance(expression.get(key), (list, tuple)):
            for item in expression[key]:
                yield from iter_variable_ids(item)


def _arg(expression: Mapping[str, Any], resolver: Callable[[str], Any]) -> Any:
    return evaluate_expression(expression["arg"], resolver)


def _number(value: Any, op: str) -> float | int:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ExpressionError(f"{op} requires a number, got {type(value).__name__}")
    if isinstance(value, float) and not math.isfinite(value):
        raise ExpressionError(f"{op} received a non-finite number")
    return value


def evaluate_expression(
    expression: Mapping[str, Any], resolve_variable: Callable[[str], Any]
) -> Any:
    """Evaluate a validated expression. ``MISSING`` means unresolved/missing."""
    op = expression.get("op")
    if op == "literal":
        return copy.deepcopy(expression.get("value"))
    if op == "variable":
        return resolve_variable(expression["id"])
    if op == "coalesce":
        for item in expression["args"]:
            value = evaluate_expression(item, resolve_variable)
            if value is not MISSING and value is not None:
                return value
        return MISSING
    if op == "concat":
        values = [evaluate_expression(item, resolve_variable) for item in expression["args"]]
        if any(value is MISSING or value is None or not isinstance(value, str) for value in values):
            raise ExpressionError("concat requires non-missing string arguments")
        return "".join(values)
    if op == "to_number":
        value = _arg(expression, resolve_variable)
        if isinstance(value, bool) or value is MISSING or value is None:
            raise ExpressionError("to_number requires a numeric value")
        if isinstance(value, (int, float)):
            return _number(value, "to_number")
        if isinstance(value, str):
            raw = value.strip()
            if _INTEGER_RE.fullmatch(raw):
                return int(raw)
            try:
                number = float(raw)
            except ValueError:
                raise ExpressionError(f"cannot convert {value!r} to a number") from None
            return _number(number, "to_number")
        raise ExpressionError(f"cannot convert {type(value).__name__} to a number")
    if op == "to_string":
        value = _arg(expression, resolve_variable)
        if value is MISSING or value is None:
            raise ExpressionError("to_string requires a non-missing value")
        if isinstance(value, str):
            return value
        if isinstance(value, bool):
            return "true" if value else "false"
        if isinstance(value, (int, float)):
            return str(_number(value, "to_string"))
        raise ExpressionError(f"cannot convert {type(value).__name__} to a string")
    if op == "to_boolean":
        value = _arg(expression, resolve_variable)
        if isinstance(value, bool):
            return value
        if value in (1, 0):
            return bool(value)
        if isinstance(value, str):
            lowered = value.strip().lower()
            if lowered == "true":
                return True
            if lowered == "false":
                return False
        raise ExpressionError(f"cannot convert {value!r} to a boolean")
    if op == "json_parse":
        value = _arg(expression, resolve_variable)
        if not isinstance(value, str):
            raise ExpressionError("json_parse requires a string")
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError as exc:
            raise ExpressionError(f"json_parse failed: {exc}") from exc
        return parsed
    if op == "length":
        value = _arg(expression, resolve_variable)
        if isinstance(value, (str, list, tuple, dict)):
            return len(value)
        raise ExpressionError("length requires a string, list, or object")
    raise ExpressionError(f"unsupported computed expression op: {op!r}")
