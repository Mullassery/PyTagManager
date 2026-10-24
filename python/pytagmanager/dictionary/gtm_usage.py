"""Cross-reference a Website Data Dictionary with a GTM container config.

ObservePoint-style validation answers "which tags depend on this dataLayer
field, and what breaks if it changes?"  PyTagManager already builds the
dictionary and schema-drift report; this module adds the missing GTM side.

Input is a GTM container export (the JSON produced by the Tag Manager API or
the admin UI's "Export container" action). No network call is made here; the
existing ``analytics_api.gtm_client.GtmApiClient`` can fetch a live container
and pass it in.

The matching is deliberately conservative: a GTM Data Layer Variable's
``dataLayerName`` is matched against a dictionary path only when it is the
same path or a dot-suffix of it (``price`` matches ``purchase.price``).
Anything broader would produce false "this tag uses that field" claims.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from pytagmanager.dictionary.build import DataDictionary

if TYPE_CHECKING:  # avoids a circular import: schema_drift imports this module
    from pytagmanager.dictionary.schema_drift import DictionaryDrift


@dataclass(frozen=True)
class GtmConsumer:
    """One GTM object that reads a dataLayer field."""

    kind: str  # "tag", "trigger", or "variable"
    name: str
    detail: str = ""

    def render(self) -> str:
        suffix = f" ({self.detail})" if self.detail else ""
        return f"{self.kind} {self.name!r}{suffix}"


@dataclass
class GtmUsageIndex:
    """Data Layer Variable name -> GTM objects that reference it."""

    by_data_layer_name: dict[str, tuple[GtmConsumer, ...]] = field(default_factory=dict)

    def consumers_for_path(self, path: str) -> tuple[GtmConsumer, ...]:
        """Return consumers for a dictionary path using exact/suffix matching."""
        matches: list[GtmConsumer] = []
        for name, consumers in sorted(self.by_data_layer_name.items()):
            if path == name or path.endswith("." + name):
                matches.extend(consumers)
        seen = set()
        unique: list[GtmConsumer] = []
        for consumer in matches:
            key = (consumer.kind, consumer.name, consumer.detail)
            if key in seen:
                continue
            seen.add(key)
            unique.append(consumer)
        return tuple(unique)

    def render_for_path(self, path: str) -> str | None:
        consumers = self.consumers_for_path(path)
        if not consumers:
            return None
        return "; ".join(consumer.render() for consumer in consumers)

    def drift_blast_radius(self, drift: DictionaryDrift) -> list[dict[str, Any]]:
        """Explain which GTM consumers may be affected by each dataLayer change."""
        impacts: list[dict[str, Any]] = []

        def add(change: str, path: str, detail: str = "") -> None:
            consumers = self.consumers_for_path(path)
            if not consumers:
                return
            impacts.append(
                {
                    "change": change,
                    "path": path,
                    "detail": detail,
                    "consumers": [
                        {"kind": c.kind, "name": c.name, "detail": c.detail} for c in consumers
                    ],
                }
            )

        for variable in drift.added_variables:
            if variable.source == "datalayer_field":
                add(
                    "added",
                    variable.path,
                    "new field; no existing GTM consumer should be assumed",
                )
        for variable in drift.removed_variables:
            if variable.source == "datalayer_field":
                add(
                    "removed",
                    variable.path,
                    "field no longer observed; dependent GTM objects may receive undefined",
                )
        for shift in drift.type_distribution_shifts:
            if shift.source == "datalayer_field":
                add("type_changed", shift.path, shift.render())
        for rename in drift.possible_renames:
            if rename.new_source == "datalayer_field":
                add(
                    "possible_rename",
                    rename.new_path,
                    f"possible rename from {rename.old_path}",
                )
        return impacts

    def render_drift_blast_radius(self, drift: DictionaryDrift) -> str:
        impacts = self.drift_blast_radius(drift)
        if not impacts:
            return ""
        lines = ["GTM blast radius (fields with known consumers):"]
        for impact in impacts:
            consumers = ", ".join(f"{c['kind']} {c['name']!r}" for c in impact["consumers"])
            lines.append(
                f"  ! {impact['change']}: {impact['path']} — read by {consumers}"
                + (f" ({impact['detail']})" if impact["detail"] else "")
            )
        return "\n".join(lines)


def _container_version(document: dict[str, Any]) -> dict[str, Any]:
    version = document.get("containerVersion")
    if isinstance(version, dict):
        return version
    return document


def _elements(document: dict[str, Any], key: str) -> list[dict[str, Any]]:
    version = _container_version(document)
    values = version.get(key) or []
    return [value for value in values if isinstance(value, dict)]


def _iter_strings(value: Any) -> Iterable[str]:
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for nested in value.values():
            yield from _iter_strings(nested)
    elif isinstance(value, list):
        for nested in value:
            yield from _iter_strings(nested)


def _references(value: Any) -> list[str]:
    """Extract `{{Variable Name}}` references from a GTM parameter value."""
    refs: list[str] = []
    for text in _iter_strings(value):
        start = 0
        while True:
            left = text.find("{{", start)
            if left < 0:
                break
            right = text.find("}}", left + 2)
            if right < 0:
                break
            refs.append(text[left + 2 : right].strip())
            start = right + 2
    return refs


def _data_layer_variables(document: dict[str, Any]) -> dict[str, str]:
    """GTM variable name -> dataLayerName for type `v` variables."""
    result: dict[str, str] = {}
    for variable in _elements(document, "variable"):
        if variable.get("type") != "v":
            continue
        name = variable.get("name")
        if not isinstance(name, str) or not name:
            continue
        for parameter in variable.get("parameter") or []:
            if not isinstance(parameter, dict):
                continue
            if parameter.get("key") == "dataLayerName":
                value = parameter.get("value")
                if isinstance(value, str) and value:
                    result[name] = value
                    break
    return result


def build_gtm_usage_index(container: dict[str, Any]) -> GtmUsageIndex:
    """Index which GTM tags/triggers/variables reference each dataLayer path."""
    data_layer_vars = _data_layer_variables(container)
    by_name: dict[str, list[GtmConsumer]] = {}

    # Another variable that reads {{DLV - price}} is itself a consumer of the
    # underlying dataLayer field, even if no tag references it yet.
    for variable in _elements(container, "variable"):
        variable_name = variable.get("name")
        if not isinstance(variable_name, str) or not variable_name:
            continue
        for reference in _references(variable):
            data_layer_name = data_layer_vars.get(reference)
            if data_layer_name and reference != variable_name:
                by_name.setdefault(data_layer_name, []).append(
                    GtmConsumer(
                        "variable",
                        variable_name,
                        f"via variable {reference!r}",
                    )
                )

    for kind in ("tag", "trigger"):
        for element in _elements(container, kind):
            name = element.get("name")
            if not isinstance(name, str) or not name:
                continue
            for reference in _references(element):
                data_layer_name = data_layer_vars.get(reference)
                if data_layer_name:
                    by_name.setdefault(data_layer_name, []).append(
                        GtmConsumer(kind, name, f"via variable {reference!r}")
                    )

    return GtmUsageIndex(
        by_data_layer_name={
            name: tuple(sorted(set(consumers), key=lambda c: (c.kind, c.name)))
            for name, consumers in by_name.items()
        }
    )


def load_gtm_container(path: str) -> dict[str, Any]:
    """Load a GTM container export from a local JSON file."""
    import json

    with open(path, encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise ValueError("GTM container export must be a JSON object")
    return data


def consumers_for_dictionary(
    dictionary: DataDictionary, usage: GtmUsageIndex
) -> dict[tuple[str, str], tuple[GtmConsumer, ...]]:
    """Map (source, path) -> GTM consumers for every dataLayer field."""
    result: dict[tuple[str, str], tuple[GtmConsumer, ...]] = {}
    for variable in dictionary.variables:
        if variable.source != "datalayer_field":
            continue
        consumers = usage.consumers_for_path(variable.path)
        if consumers:
            result[(variable.source, variable.path)] = consumers
    return result
