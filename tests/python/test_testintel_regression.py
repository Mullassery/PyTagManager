"""Tests for Phase 1.9 item 3's regression-category Test Candidates
(docs/VISION.md §15): reuses dictionary/schema_drift.py's DictionaryDrift
rather than new diff logic."""

from __future__ import annotations

from pytagmanager.dictionary.build import build_data_dictionary
from pytagmanager.dictionary.schema_drift import diff_dictionaries
from pytagmanager.observability.state import RuntimeStateSnapshot
from pytagmanager.testintel.candidates import CATEGORY_REGRESSION, SEVERITY_REQUIRES_VERIFICATION
from pytagmanager.testintel.regression import generate_regression_candidates


def _snapshot(page_url, timestamp, data_layer=None, cookies=None):
    return RuntimeStateSnapshot(
        page_url=page_url, timestamp=timestamp, label="page_load", data_layer=data_layer or [], cookies=cookies or {}
    )


def test_removed_datalayer_field_produces_a_regression_candidate_naming_the_exact_field():
    # Reproduces the Phase 1.9 exit criteria: a purchase event's
    # transaction_id field was removed between two crawls.
    old = build_data_dictionary(
        [_snapshot("https://example.com/checkout", 1.0, data_layer=[{"event": "purchase", "transaction_id": "T1"}])]
    )
    new = build_data_dictionary(
        [_snapshot("https://example.com/checkout", 2.0, data_layer=[{"event": "purchase"}])]
    )
    drift = diff_dictionaries(old, new)

    candidates = generate_regression_candidates(drift, "baseline.json", "latest.json")

    assert len(candidates) == 1
    candidate = candidates[0]
    assert candidate.category == CATEGORY_REGRESSION
    assert candidate.severity == SEVERITY_REQUIRES_VERIFICATION
    assert "transaction_id" in candidate.name
    assert "purchase" in candidate.name
    assert "transaction_id" in candidate.observed_problem
    assert "baseline.json" in candidate.observed
    assert candidate.evidence_pages == ("https://example.com/checkout",)


def test_no_removed_fields_produces_no_candidates():
    dictionary = build_data_dictionary(
        [_snapshot("https://example.com/checkout", 1.0, data_layer=[{"event": "purchase", "transaction_id": "T1"}])]
    )
    drift = diff_dictionaries(dictionary, dictionary)
    assert generate_regression_candidates(drift, "old", "new") == []


def test_removed_cookie_does_not_produce_a_regression_candidate():
    old = build_data_dictionary([_snapshot("https://example.com/", 1.0, cookies={})])
    # Simulate a cookie present in old but not new via direct dictionary construction
    from pytagmanager.observability.state import StorageEntry

    old_with_cookie = build_data_dictionary(
        [_snapshot("https://example.com/", 1.0, cookies={"session_id": StorageEntry(key="session_id", value_type="string", length=8)})]
    )
    new_without_cookie = build_data_dictionary([_snapshot("https://example.com/", 2.0, cookies={})])
    drift = diff_dictionaries(old_with_cookie, new_without_cookie)

    assert drift.removed_variables  # the cookie removal is real structural drift...
    assert generate_regression_candidates(drift, "old", "new") == []  # ...but not a regression *candidate*


def test_possible_rename_is_excluded_from_regression_candidates():
    old = build_data_dictionary(
        [_snapshot("https://example.com/p", 1.0, data_layer=[{"event": "product_view", "product_identifier": "p1"}])]
    )
    new = build_data_dictionary(
        [_snapshot("https://example.com/p", 2.0, data_layer=[{"event": "product_view", "product_id": "p1"}])]
    )
    drift = diff_dictionaries(old, new)
    assert drift.possible_renames  # confirm the rename heuristic actually caught this

    candidates = generate_regression_candidates(drift, "old", "new")
    assert candidates == []


def test_suggested_verification_names_the_field():
    old = build_data_dictionary(
        [_snapshot("https://example.com/checkout", 1.0, data_layer=[{"event": "purchase", "currency": "USD"}])]
    )
    new = build_data_dictionary([_snapshot("https://example.com/checkout", 2.0, data_layer=[{"event": "purchase"}])])
    drift = diff_dictionaries(old, new)

    candidate = generate_regression_candidates(drift, "old", "new")[0]
    assert any("currency" in step for step in candidate.suggested_verification)
