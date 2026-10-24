"""Real-browser end-to-end tests for Phase 1.95 item 2's script inventory
(docs/VISION.md §16): real CDP Network events + DOM script-tag attributes.
"""

from __future__ import annotations

from pytagmanager.perf.scripts import build_script_inventory

_PAGE = "perf_scripts.html"


def test_first_party_async_script_is_classified_correctly(fixture_server):
    inventory = build_script_inventory(f"{fixture_server}/{_PAGE}", headless=True)

    local_script = next(
        (s for s in inventory.scripts if s.url.endswith("local_first_party.js")), None
    )
    assert local_script is not None
    assert local_script.is_first_party is True
    assert local_script.load_mechanism == "async"
    assert local_script.initiator_type == "parser"
    assert local_script.resource_type == "Script"
    assert local_script.transfer_bytes is not None
    assert local_script.transfer_bytes > 0


def test_dynamically_injected_vendor_script_has_script_initiator_and_vendor_classification(
    fixture_server,
):
    inventory = build_script_inventory(f"{fixture_server}/{_PAGE}", headless=True, wait_ms=1500)

    vendor_script = next((s for s in inventory.scripts if "fbevents.js" in s.url), None)
    assert vendor_script is not None
    assert vendor_script.is_first_party is False
    assert vendor_script.initiator_type == "script"
    assert vendor_script.vendor == "Meta Pixel"
    assert vendor_script.category == "ads"


def test_unclassified_script_has_no_vendor_or_category(fixture_server):
    inventory = build_script_inventory(f"{fixture_server}/{_PAGE}", headless=True)
    local_script = next(
        (s for s in inventory.scripts if s.url.endswith("local_first_party.js")), None
    )
    assert local_script is not None
    assert local_script.vendor is None
    assert local_script.category is None


def test_third_party_scripts_property_excludes_first_party(fixture_server):
    inventory = build_script_inventory(f"{fixture_server}/{_PAGE}", headless=True, wait_ms=1500)
    third_party_urls = {s.url for s in inventory.third_party_scripts}
    assert all("local_first_party.js" not in u for u in third_party_urls)
    assert any("fbevents.js" in u for u in third_party_urls)
