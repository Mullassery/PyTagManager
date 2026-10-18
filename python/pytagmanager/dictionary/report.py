"""Human-readable and JSON rendering for a `DataDictionary`
(docs/VISION.md §3), mirroring the `reporting/` package's
terminal/JSON split for the diagnostics side."""

from __future__ import annotations

from typing import Dict, Optional, Tuple

from pytagmanager.dictionary.build import DataDictionary, DictionaryVariable
from pytagmanager.dictionary.labels import PresenceLabel, label_presence
from pytagmanager.dictionary.gtm_usage import GtmUsageIndex
from pytagmanager.dictionary.purpose import PurposeResult

JSON_SCHEMA_VERSION = 2

_SOURCE_LABELS = {
    "datalayer_event": "dataLayer events",
    "datalayer_field": "dataLayer fields",
    "cookie": "Cookies",
    "local_storage": "LocalStorage",
    "session_storage": "SessionStorage",
}
_SOURCE_ORDER = ("datalayer_event", "datalayer_field", "cookie", "local_storage", "session_storage")

# Purpose classification only applies to sources §6 of docs/VISION.md scopes
# it to: cookies and browser storage, not dataLayer events/fields.
_PURPOSE_ELIGIBLE_SOURCES = ("cookie", "local_storage", "session_storage")


def _variable_key(variable: DictionaryVariable) -> Tuple[str, str]:
    return (variable.source, variable.path)


def render_dictionary_report(
    dictionary: DataDictionary,
    purpose_by_key: Optional[Dict[Tuple[str, str], PurposeResult]] = None,
    include_presence: bool = False,
    gtm_usage: Optional[GtmUsageIndex] = None,
) -> str:
    lines = ["PyTagManager Website Data Dictionary", "=" * 37, ""]
    lines.append(f"Pages analyzed: {dictionary.pages_total}")
    lines.append("")

    for source in _SOURCE_ORDER:
        variables = dictionary.by_source(source)
        if not variables:
            continue
        label = _SOURCE_LABELS[source]
        lines.append(label)
        lines.append("-" * len(label))
        for variable in sorted(variables, key=lambda v: (-v.observed_count, v.path)):
            ratio = variable.presence_ratio
            ratio_str = f"{ratio:.0%}" if ratio is not None else "n/a"
            types = ", ".join(variable.value_types) or "unknown"
            line = (
                f"  {variable.path:<40} {variable.observed_count}/{variable.pages_total} pages "
                f"({ratio_str}), types: {types}"
            )
            if include_presence:
                presence = label_presence(variable)
                line += f" [{presence.accessibility}]"
            lines.append(line)
            if gtm_usage is not None and source == "datalayer_field":
                usage = gtm_usage.render_for_path(variable.path)
                if usage:
                    lines.append(f"      GTM consumers: {usage}")
            if purpose_by_key is not None and source in _PURPOSE_ELIGIBLE_SOURCES:
                result = purpose_by_key.get(_variable_key(variable))
                if result is not None:
                    lines.append(f"      purpose: {result.purpose} (confidence {result.confidence:.0%})")
                    for item in result.evidence:
                        lines.append(f"        evidence: {item}")
        lines.append("")

    if dictionary.pages_total == 0:
        lines.append("No pages were successfully observed.")

    return "\n".join(lines)


def build_dictionary_json(
    dictionary: DataDictionary,
    purpose_by_key: Optional[Dict[Tuple[str, str], PurposeResult]] = None,
    include_presence: bool = False,
    gtm_usage: Optional[GtmUsageIndex] = None,
) -> dict:
    variables_json = []
    for variable in dictionary.variables:
        entry = {
            "source": variable.source,
            "path": variable.path,
            "value_types": list(variable.value_types),
            "pages_present": list(variable.pages_present),
            "observed_count": variable.observed_count,
            "pages_total": variable.pages_total,
            "presence_ratio": (round(variable.presence_ratio, 4) if variable.presence_ratio is not None else None),
            "first_observed": variable.first_observed,
            "last_observed": variable.last_observed,
            "value_type_counts": [list(pair) for pair in variable.value_type_counts],
        }
        if include_presence:
            presence = label_presence(variable)
            entry["presence"] = {
                "exists": presence.exists,
                "exposed": presence.exposed,
                "accessibility": presence.accessibility,
                "rationale": presence.rationale,
            }
        if gtm_usage is not None and variable.source == "datalayer_field":
            consumers = gtm_usage.consumers_for_path(variable.path)
            if consumers:
                entry["gtm_usage"] = [
                    {"kind": c.kind, "name": c.name, "detail": c.detail}
                    for c in consumers
                ]
        if purpose_by_key is not None and variable.source in _PURPOSE_ELIGIBLE_SOURCES:
            result = purpose_by_key.get(_variable_key(variable))
            if result is not None:
                entry["purpose"] = {
                    "purpose": result.purpose,
                    "confidence": result.confidence,
                    "evidence": result.evidence,
                    "rationale": result.rationale,
                }
        variables_json.append(entry)

    return {
        "schema_version": JSON_SCHEMA_VERSION,
        "pages_total": dictionary.pages_total,
        "variables": variables_json,
    }
