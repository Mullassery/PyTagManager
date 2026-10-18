"""Tests for GTM container cross-referencing (Data Dictionary Phase 1.7 remainder)."""

from pytagmanager.dictionary.build import DataDictionary, DictionaryVariable
from pytagmanager.dictionary.gtm_usage import (
    build_gtm_usage_index,
    consumers_for_dictionary,
    load_gtm_container,
)
from pytagmanager.dictionary.report import build_dictionary_json, render_dictionary_report
from pytagmanager.dictionary.schema_drift import (
    build_drift_json,
    diff_dictionaries,
    render_drift_report,
)

CONTAINER = {
    "containerVersion": {
        "variable": [
            {
                "name": "DLV - price",
                "type": "v",
                "parameter": [{"key": "dataLayerName", "value": "price", "type": "template"}],
            },
            {
                "name": "CJS - formatted price",
                "type": "jsm",
                "parameter": [{"key": "javascript", "value": "return {{DLV - price}};"}],
            },
        ],
        "tag": [
            {
                "name": "GA4 Purchase",
                "type": "gaawe",
                "parameter": [
                    {
                        "key": "eventParameters",
                        "list": [
                            {
                                "map": [
                                    {"key": "name", "value": "value"},
                                    {"key": "value", "value": "{{DLV - price}}"},
                                ]
                            }
                        ],
                    }
                ],
            }
        ],
        "trigger": [
            {
                "name": "Purchase",
                "type": "CUSTOM_EVENT",
                "customEventFilter": [
                    {"parameter": [{"key": "arg1", "value": "{{DLV - price}}"}]}
                ],
            }
        ],
    }
}


def _variable(path: str, types=("number",)) -> DictionaryVariable:
    return DictionaryVariable(
        source="datalayer_field",
        path=path,
        value_types=types,
        pages_present=("https://example.test/",),
        pages_total=1,
        first_observed=1.0,
        last_observed=1.0,
        value_type_counts=tuple((t, 1) for t in types),
    )


def test_builds_index_and_matches_suffix_paths():
    usage = build_gtm_usage_index(CONTAINER)
    consumers = usage.consumers_for_path("purchase.price")

    assert {c.kind for c in consumers} == {"tag", "trigger", "variable"}
    names = {c.name for c in consumers}
    assert "GA4 Purchase" in names
    assert "Purchase" in names
    assert "CJS - formatted price" in names
    assert usage.consumers_for_path("purchase.value") == ()


def test_dictionary_report_and_json_include_gtm_consumers():
    usage = build_gtm_usage_index(CONTAINER)
    dictionary = DataDictionary(variables=(_variable("purchase.price"), _variable("purchase.value")), pages_total=1)

    text = render_dictionary_report(dictionary, gtm_usage=usage)
    assert "GTM consumers:" in text
    assert "GA4 Purchase" in text
    assert "purchase.value" in text

    payload = build_dictionary_json(dictionary, gtm_usage=usage)
    by_path = {entry["path"]: entry for entry in payload["variables"]}
    assert {c["name"] for c in by_path["purchase.price"]["gtm_usage"]} >= {
        "GA4 Purchase",
        "Purchase",
        "CJS - formatted price",
    }
    assert "gtm_usage" not in by_path["purchase.value"]


def test_schema_drift_reports_gtm_blast_radius():
    usage = build_gtm_usage_index(CONTAINER)
    old = DataDictionary(variables=(_variable("purchase.price", ("string",)),), pages_total=1)
    new = DataDictionary(variables=(_variable("purchase.price", ("number",)),), pages_total=1)
    drift = diff_dictionaries(old, new)

    assert drift.type_distribution_shifts

    text = render_drift_report(drift, gtm_usage=usage)
    assert "GTM blast radius" in text
    assert "purchase.price" in text
    assert "GA4 Purchase" in text

    payload = build_drift_json(drift, gtm_usage=usage)
    assert payload["gtm_blast_radius"]
    impact = payload["gtm_blast_radius"][0]
    assert impact["path"] == "purchase.price"
    assert {c["name"] for c in impact["consumers"]} >= {"GA4 Purchase", "Purchase"}


def test_load_gtm_container_reads_export_file(tmp_path):
    path = tmp_path / "container.json"
    path.write_text(__import__("json").dumps(CONTAINER), encoding="utf-8")

    loaded = load_gtm_container(str(path))
    usage = build_gtm_usage_index(loaded)
    assert usage.consumers_for_path("price")


def test_consumers_for_dictionary_only_includes_datalayer_fields():
    usage = build_gtm_usage_index(CONTAINER)
    dictionary = DataDictionary(
        variables=(
            _variable("purchase.price"),
            DictionaryVariable(
                source="cookie",
                path="price",
                value_types=("string",),
                pages_present=("https://example.test/",),
                pages_total=1,
                first_observed=1.0,
                last_observed=1.0,
            ),
        ),
        pages_total=1,
    )
    result = consumers_for_dictionary(dictionary, usage)
    assert ("datalayer_field", "purchase.price") in result
    assert ("cookie", "price") not in result
