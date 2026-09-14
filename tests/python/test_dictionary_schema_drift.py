"""Tests for Phase 1.7's DataLayer schema drift detection
(docs/VISION.md §5): diffing two DataDictionary snapshots for
added/removed fields, type-distribution shifts, and possible renames."""

from __future__ import annotations

from pytagmanager.dictionary.build import DataDictionary, build_data_dictionary, data_dictionary_from_json
from pytagmanager.dictionary.report import build_dictionary_json
from pytagmanager.dictionary.schema_drift import diff_dictionaries, render_drift_report
from pytagmanager.observability.state import RuntimeStateSnapshot


def _snapshot(page_url: str, timestamp: float, data_layer) -> RuntimeStateSnapshot:
    return RuntimeStateSnapshot(page_url=page_url, timestamp=timestamp, label="page_load", data_layer=data_layer)


def test_added_field_is_reported():
    old = build_data_dictionary([_snapshot("https://example.com/a", 1.0, [{"event": "purchase", "id": "T1"}])])
    new = build_data_dictionary(
        [_snapshot("https://example.com/a", 2.0, [{"event": "purchase", "id": "T1", "currency": "USD"}])]
    )

    drift = diff_dictionaries(old, new)

    assert any(v.path == "purchase.currency" for v in drift.added_variables)
    assert drift.has_changes


def test_removed_field_is_reported():
    old = build_data_dictionary(
        [_snapshot("https://example.com/a", 1.0, [{"event": "purchase", "id": "T1", "currency": "USD"}])]
    )
    new = build_data_dictionary([_snapshot("https://example.com/a", 2.0, [{"event": "purchase", "id": "T1"}])])

    drift = diff_dictionaries(old, new)

    assert any(v.path == "purchase.currency" for v in drift.removed_variables)


def test_type_distribution_shift_is_detected():
    old_snapshots = [_snapshot(f"https://example.com/{i}", float(i), [{"event": "purchase", "transaction_id": "T1"}]) for i in range(24)]
    old_snapshots += [
        _snapshot("https://example.com/num", 25.0, [{"event": "purchase", "transaction_id": 123}])
    ]
    old = build_data_dictionary(old_snapshots)  # 24/25 string, 1/25 number

    new_snapshots = [
        _snapshot(f"https://example.com/{i}", float(i), [{"event": "purchase", "transaction_id": 123}])
        for i in range(25)
    ]
    new = build_data_dictionary(new_snapshots)  # 25/25 number

    drift = diff_dictionaries(old, new)

    shift = next(s for s in drift.type_distribution_shifts if s.path == "purchase.transaction_id")
    assert shift.new_distribution.get("number") == 1.0
    assert "purchase.transaction_id" in render_drift_report(drift)


def test_nested_field_restructure_is_flagged_as_possible_rename():
    # The Phase 1.7 exit criteria case: dataLayer.product.price ->
    # dataLayer.product.pricing.amount.
    old = build_data_dictionary(
        [_snapshot("https://example.com/p", 1.0, [{"event": "product_view", "product": {"price": 9.99}}])]
    )
    new = build_data_dictionary(
        [
            _snapshot(
                "https://example.com/p", 2.0, [{"event": "product_view", "product": {"pricing": {"amount": 9.99}}}]
            )
        ]
    )

    drift = diff_dictionaries(old, new)

    renames = {(r.old_path, r.new_path) for r in drift.possible_renames}
    # "price" -> "amount" leaf names aren't similar text, but both are
    # numbers under the same "product_view" event namespace with no other
    # candidates, so the type-match signal alone should surface it.
    assert ("product_view.product.price", "product_view.product.pricing.amount") in renames or any(
        r.new_path == "product_view.product.pricing" for r in drift.possible_renames
    )


def test_similar_leaf_name_rename_is_detected_by_string_similarity():
    old = build_data_dictionary(
        [_snapshot("https://example.com/p", 1.0, [{"event": "add_to_cart", "product_identifier": "p1"}])]
    )
    new = build_data_dictionary(
        [_snapshot("https://example.com/p", 2.0, [{"event": "add_to_cart", "product_id": "p1"}])]
    )

    drift = diff_dictionaries(old, new)

    assert any(
        r.old_path == "add_to_cart.product_identifier" and r.new_path == "add_to_cart.product_id"
        for r in drift.possible_renames
    )


def test_unrelated_add_and_remove_across_different_events_is_not_a_rename():
    old = build_data_dictionary([_snapshot("https://example.com/p", 1.0, [{"event": "purchase", "total": 9.99}])])
    new = build_data_dictionary(
        [_snapshot("https://example.com/p", 2.0, [{"event": "signup", "plan_name": "pro"}])]
    )

    drift = diff_dictionaries(old, new)

    assert drift.possible_renames == []
    assert len(drift.added_variables) >= 1
    assert len(drift.removed_variables) >= 1


def test_no_changes_reports_no_drift():
    dictionary = build_data_dictionary(
        [_snapshot("https://example.com/a", 1.0, [{"event": "page_view"}])]
    )
    drift = diff_dictionaries(dictionary, dictionary)
    assert not drift.has_changes
    assert "No schema drift detected" in render_drift_report(drift)


def test_json_roundtrip_via_data_dictionary_from_json():
    original = build_data_dictionary(
        [_snapshot("https://example.com/a", 1.0, [{"event": "purchase", "transaction_id": "T1"}])]
    )
    payload = build_dictionary_json(original)
    reloaded = data_dictionary_from_json(payload)

    assert isinstance(reloaded, DataDictionary)
    assert reloaded.pages_total == original.pages_total
    assert {v.path for v in reloaded.variables} == {v.path for v in original.variables}

    drift = diff_dictionaries(reloaded, original)
    assert not drift.has_changes
