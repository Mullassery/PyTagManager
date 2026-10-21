"""Deterministic variable resolution with explicit missing/type errors."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from pytagmanager.control._sentinels import MISSING
from pytagmanager.control.conditions import resolve_path
from pytagmanager.control.config import Variable
from pytagmanager.control.expressions import (
    ExpressionError,
    evaluate_expression,
    iter_variable_ids,
)
from pytagmanager.observability.events import is_sensitive_key

_REDACTED = "[REDACTED]"
_RESOLVED = frozenset({"resolved", "default"})


@dataclass(frozen=True)
class ResolvedVariable:
    variable_id: str
    name: str
    type: str
    status: str
    value: Any
    error: str | None
    sensitive: bool

    @property
    def redacted_value(self) -> Any:
        return _REDACTED if self.sensitive and self.status in _RESOLVED else self.value

    def to_trace_dict(self) -> dict[str, Any]:
        item = {
            "variable_id": self.variable_id,
            "name": self.name,
            "type": self.type,
            "status": self.status,
            "value": self.redacted_value,
            "sensitive": self.sensitive,
        }
        if self.error is not None:
            item["error"] = self.error
        return item


def _type_matches(value: Any, value_type: str) -> bool:
    if value_type == "json":
        return True
    if value_type == "null":
        return value is None
    if value_type == "string":
        return isinstance(value, str)
    if value_type == "number":
        return not isinstance(value, bool) and isinstance(value, (int, float))
    if value_type == "boolean":
        return isinstance(value, bool)
    if value_type == "list":
        return isinstance(value, (list, tuple))
    return False


def _directly_sensitive_ref(variable: Variable) -> bool:
    if variable.sensitive:
        return True
    if variable.source in {"data_layer", "event", "consent"} and isinstance(variable.source_ref, str):
        return is_sensitive_key(variable.source_ref.rsplit(".", 1)[-1])
    if variable.source == "dom":
        if isinstance(variable.source_ref, str):
            return is_sensitive_key(variable.source_ref)
        if isinstance(variable.source_ref, Mapping):
            attribute = variable.source_ref.get("attribute")
            if isinstance(attribute, str):
                return is_sensitive_key(attribute)
    return False


class VariableResolver:
    def __init__(self, variables: tuple[Variable, ...], context: Mapping[str, Any]) -> None:
        self.variables = variables
        self.context = context
        self._by_id = {variable.variable_id: variable for variable in variables}
        self._cache: dict[str, ResolvedVariable] = {}
        self._visiting: set[str] = set()

    def resolve_all(self) -> list[ResolvedVariable]:
        return [self.resolve(variable.variable_id) for variable in self.variables]

    def resolve(self, variable_id: str) -> ResolvedVariable:
        cached = self._cache.get(variable_id)
        if cached is not None:
            return cached
        variable = self._by_id.get(variable_id)
        if variable is None:
            result = ResolvedVariable(
                variable_id=variable_id,
                name=variable_id,
                type="unknown",
                status="error",
                value=None,
                error=f"unknown variable {variable_id}",
                sensitive=False,
            )
            self._cache[variable_id] = result
            return result
        if not variable.enabled:
            result = ResolvedVariable(
                variable_id=variable.variable_id,
                name=variable.name,
                type=variable.type,
                status="disabled",
                value=None,
                error=None,
                sensitive=self._sensitive(variable),
            )
            self._cache[variable_id] = result
            return result
        if variable_id in self._visiting:
            result = ResolvedVariable(
                variable_id=variable.variable_id,
                name=variable.name,
                type=variable.type,
                status="error",
                value=None,
                error="computed variable cycle",
                sensitive=variable.sensitive,
            )
            self._cache[variable_id] = result
            return result

        self._visiting.add(variable_id)
        try:
            result = self._resolve_value(variable)
        finally:
            self._visiting.discard(variable_id)
        self._cache[variable_id] = result
        return result

    def _sensitive(self, variable: Variable, seen: set[str] | None = None) -> bool:
        if _directly_sensitive_ref(variable):
            return True
        if variable.source != "computed":
            return False
        seen = set() if seen is None else seen
        if variable.variable_id in seen:
            return False
        seen.add(variable.variable_id)
        for dependency_id in iter_variable_ids(variable.source_ref):
            dependency = self._by_id.get(dependency_id)
            if dependency is not None and self._sensitive(dependency, seen):
                return True
        return False

    def _resolve_value(self, variable: Variable) -> ResolvedVariable:
        try:
            found, value = self._source_value(variable)
            if found is MISSING:
                if variable.default is not None:
                    value = variable.default
                    status = "default"
                else:
                    return ResolvedVariable(
                        variable_id=variable.variable_id,
                        name=variable.name,
                        type=variable.type,
                        status="missing",
                        value=None,
                        error=None,
                        sensitive=self._sensitive(variable),
                    )
            else:
                status = "resolved"
            if not _type_matches(value, variable.type):
                return ResolvedVariable(
                    variable_id=variable.variable_id,
                    name=variable.name,
                    type=variable.type,
                    status="error",
                    value=None,
                    error=f"resolved value is not of type {variable.type}",
                    sensitive=self._sensitive(variable),
                )
            return ResolvedVariable(
                variable_id=variable.variable_id,
                name=variable.name,
                type=variable.type,
                status=status,
                value=value,
                error=None,
                sensitive=self._sensitive(variable),
            )
        except (ExpressionError, ValueError) as exc:
            return ResolvedVariable(
                variable_id=variable.variable_id,
                name=variable.name,
                type=variable.type,
                status="error",
                value=None,
                error=str(exc),
                sensitive=self._sensitive(variable),
            )

    def _source_value(self, variable: Variable) -> tuple[Any, Any]:
        source = variable.source
        if source == "static":
            return True, variable.default
        if source in {"page_url", "page_path", "page_title", "referrer"}:
            page = self.context.get("page", {})
            if not isinstance(page, Mapping):
                return MISSING, None
            key = {
                "page_url": "url",
                "page_path": "path",
                "page_title": "title",
                "referrer": "referrer",
            }[source]
            return (True, page[key]) if key in page else (MISSING, None)
        if source in {"data_layer", "event", "consent"}:
            namespace = self.context.get(source, {})
            value = resolve_path(namespace, variable.source_ref)
            return (MISSING, None) if value is MISSING else (True, value)
        if source == "dom":
            return self._dom_value(variable)
        if source == "computed":
            value = evaluate_expression(variable.source_ref, self._resolve_reference)
            return (MISSING, None) if value is MISSING else (True, value)
        return MISSING, None

    def _dom_value(self, variable: Variable) -> tuple[Any, Any]:
        dom = self.context.get("dom", {})
        if not isinstance(dom, Mapping):
            return MISSING, None
        ref = variable.source_ref
        if isinstance(ref, str):
            node = dom.get(ref)
            if node is None:
                return MISSING, None
            if not isinstance(node, Mapping):
                return True, node
            for key in ("text", "textContent", "innerText"):
                if key in node:
                    return True, node[key]
            return MISSING, None
        selector = ref["selector"]
        node = dom.get(selector)
        if node is None:
            return MISSING, None
        if not isinstance(node, Mapping):
            return True, node
        attribute = ref.get("attribute", "text")
        if attribute in {"text", "textContent", "innerText"}:
            return (True, node[attribute]) if attribute in node else (MISSING, None)
        attributes = node.get("attributes", {})
        if isinstance(attributes, Mapping) and attribute in attributes:
            return True, attributes[attribute]
        return MISSING, None

    def _resolve_reference(self, variable_id: str) -> Any:
        resolved = self.resolve(variable_id)
        if resolved.status in _RESOLVED:
            return resolved.value
        if resolved.status == "missing":
            return MISSING
        raise ExpressionError(
            f"variable {resolved.name!r} could not be resolved: {resolved.error or resolved.status}"
        )
