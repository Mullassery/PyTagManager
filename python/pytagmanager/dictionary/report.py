"""Human-readable and JSON rendering for a `DataDictionary`
(docs/VISION.md §3), mirroring the `reporting/` package's
terminal/JSON split for the diagnostics side."""

from __future__ import annotations

from pytagmanager.dictionary.build import DataDictionary

JSON_SCHEMA_VERSION = 1

_SOURCE_LABELS = {
    "datalayer_event": "dataLayer events",
    "datalayer_field": "dataLayer fields",
    "cookie": "Cookies",
    "local_storage": "LocalStorage",
    "session_storage": "SessionStorage",
}
_SOURCE_ORDER = ("datalayer_event", "datalayer_field", "cookie", "local_storage", "session_storage")


def render_dictionary_report(dictionary: DataDictionary) -> str:
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
            lines.append(
                f"  {variable.path:<40} {variable.observed_count}/{variable.pages_total} pages "
                f"({ratio_str}), types: {types}"
            )
        lines.append("")

    if dictionary.pages_total == 0:
        lines.append("No pages were successfully observed.")

    return "\n".join(lines)


def build_dictionary_json(dictionary: DataDictionary) -> dict:
    return {
        "schema_version": JSON_SCHEMA_VERSION,
        "pages_total": dictionary.pages_total,
        "variables": [
            {
                "source": variable.source,
                "path": variable.path,
                "value_types": list(variable.value_types),
                "pages_present": list(variable.pages_present),
                "observed_count": variable.observed_count,
                "pages_total": variable.pages_total,
                "presence_ratio": (
                    round(variable.presence_ratio, 4) if variable.presence_ratio is not None else None
                ),
                "first_observed": variable.first_observed,
                "last_observed": variable.last_observed,
            }
            for variable in dictionary.variables
        ],
    }
