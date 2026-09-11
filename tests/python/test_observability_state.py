"""Tests for Phase 1.6 (Runtime State Capture): the `RuntimeStateSnapshot`/
`StateDiff` data model (unit, no browser) and the real end-to-end capture
through `ObservationSession` + `agent.js` (integration, real Chromium via
`fixture_server`).
"""

from __future__ import annotations

from pytagmanager.observability.events import is_sensitive_key, redact_payload
from pytagmanager.observability.scenario import ActionStep, Scenario
from pytagmanager.observability.session import ObservationSession
from pytagmanager.observability.state import (
    RuntimeStateSnapshot,
    StorageEntry,
    diff_state_snapshots,
)

_PAGE = "runtime_state.html"


def _snapshot(**overrides) -> RuntimeStateSnapshot:
    defaults = dict(page_url="https://example.com", timestamp=0.0, label="test")
    defaults.update(overrides)
    return RuntimeStateSnapshot(**defaults)


# ---- Unit tests: StateDiff, no browser ----


def test_diff_detects_added_removed_and_modified_keys():
    before = _snapshot(
        local_storage={
            "cart_id": StorageEntry(key="cart_id", value_type="string", length=2, value="c1"),
            "stale_key": StorageEntry(key="stale_key", value_type="string", length=1, value="x"),
        }
    )
    after = _snapshot(
        local_storage={
            "cart_id": StorageEntry(key="cart_id", value_type="json_array", length=10, value='["p1","p2"]'),
            "new_key": StorageEntry(key="new_key", value_type="string", length=1, value="y"),
        }
    )

    diff = diff_state_snapshots(before, after)

    assert diff.local_storage_added == ["new_key"]
    assert diff.local_storage_removed == ["stale_key"]
    assert diff.local_storage_modified == ["cart_id"]
    assert not diff.is_empty


def test_diff_is_empty_when_nothing_changed():
    snap = _snapshot(
        cookies={"visitor_id": StorageEntry(key="visitor_id", value_type="string", length=4, value="v123")}
    )
    diff = diff_state_snapshots(snap, snap)
    assert diff.is_empty


def test_diff_finds_new_data_layer_events_regardless_of_order():
    before = _snapshot(data_layer=[{"event": "page_view"}])
    after = _snapshot(data_layer=[{"event": "add_to_cart", "product_id": "p2"}, {"event": "page_view"}])

    diff = diff_state_snapshots(before, after)

    assert diff.new_data_layer_events == ["add_to_cart"]


def test_from_raw_redacts_sensitive_storage_keys_by_default():
    js_state = {
        "localStorage": {
            "session_token": {"type": "string", "length": 20, "value": "should-not-appear"},
            "cart_id": {"type": "string", "length": 2, "value": "c1"},
        },
        "sessionStorage": {},
        "dataLayer": [],
    }
    snapshot = RuntimeStateSnapshot.from_raw(
        js_state,
        cookies=[{"name": "session_id", "value": "leaked-if-not-redacted"}],
        page_url="https://example.com",
        timestamp=0.0,
        label="test",
    )

    assert snapshot.local_storage["session_token"].value == "[REDACTED]"
    assert snapshot.local_storage["cart_id"].value == "c1"
    assert snapshot.cookies["session_id"].value == "[REDACTED]"


def test_is_sensitive_key_matches_session_and_csrf_markers():
    # Added specifically for Phase 1.6 -- cookies/storage commonly carry
    # session identifiers and CSRF tokens that the pre-existing marker
    # list (password/token/secret/auth/...) didn't yet cover.
    assert is_sensitive_key("session_id")
    assert is_sensitive_key("csrf_token")
    assert not is_sensitive_key("cart_id")


def test_redact_payload_still_works_for_dict_payloads():
    # Regression check: refactoring redact_payload to share is_sensitive_key
    # must not change its existing behavior.
    assert redact_payload({"auth_token": "x", "url": "/a"}) == {"auth_token": "[REDACTED]", "url": "/a"}


# ---- Integration tests: real Chromium via ObservationSession ----


def test_page_load_snapshot_captures_cookie_and_local_storage(fixture_server):
    with ObservationSession(headless=True) as session:
        session.load(f"{fixture_server}/{_PAGE}")
        snapshots = session.state_snapshots

    assert len(snapshots) == 1
    load_snapshot = snapshots[0]
    assert load_snapshot.label == "page_load"
    assert "visitor_id" in load_snapshot.cookies
    assert load_snapshot.local_storage["cart_id"].value_type == "string"
    # Values are not captured by default (capture_storage_values=False).
    assert load_snapshot.local_storage["cart_id"].value is None


def test_capture_storage_values_opt_in_reveals_values_except_sensitive_keys(fixture_server):
    with ObservationSession(headless=True, capture_storage_values=True) as session:
        session.load(f"{fixture_server}/{_PAGE}")
        load_snapshot = session.state_snapshots[0]

    assert load_snapshot.local_storage["cart_id"].value == "c1"
    assert load_snapshot.cookies["visitor_id"].value == "v123"


def test_interaction_diff_captures_new_cookie_storage_and_datalayer_event(fixture_server):
    scenario = Scenario(name="add to cart", steps=[ActionStep(action="click", selector='[data-testid="add-to-cart"]')])
    with ObservationSession(headless=True, capture_storage_values=True) as session:
        session.load(f"{fixture_server}/{_PAGE}")
        session.run_scenario(scenario)
        diffs = session.state_diffs

    assert len(diffs) == 1
    diff = diffs[0]
    assert diff.cookies_added == ["session_id"]
    assert diff.local_storage_modified == ["cart_id"]
    assert diff.session_storage_added == ["checkout_step"]
    assert diff.new_data_layer_events == ["add_to_cart"]


def test_session_cookie_value_is_redacted_even_with_capture_values_on(fixture_server):
    # The whole point of Phase 1.6's privacy discipline: even with the
    # opt-in on, a key that looks like a live session credential never
    # surfaces its raw value.
    scenario = Scenario(name="add to cart", steps=[ActionStep(action="click", selector='[data-testid="add-to-cart"]')])
    with ObservationSession(headless=True, capture_storage_values=True) as session:
        session.load(f"{fixture_server}/{_PAGE}")
        session.run_scenario(scenario)
        after_snapshot = session.state_snapshots[-1]

    assert after_snapshot.cookies["session_id"].value == "[REDACTED]"


def test_data_layer_snapshot_reflects_full_object_not_just_the_pushed_event(fixture_server):
    scenario = Scenario(name="add to cart", steps=[ActionStep(action="click", selector='[data-testid="add-to-cart"]')])
    with ObservationSession(headless=True) as session:
        session.load(f"{fixture_server}/{_PAGE}")
        session.run_scenario(scenario)
        after_snapshot = session.state_snapshots[-1]

    events = [item.get("event") for item in after_snapshot.data_layer]
    assert "add_to_cart" in events
