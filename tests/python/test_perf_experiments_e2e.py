"""Real-browser end-to-end tests for Phase 1.95 item 4's isolation
experiments (docs/VISION.md §16): blocking a script/group actually
changes what's measured, against a real fixture page.

Builds one shared inventory + baseline for all three isolation calls
(rather than 3 independent baseline+experiment pairs) to keep real
page-load count -- and test runtime -- bounded.
"""

from __future__ import annotations

from pytagmanager.perf.experiments import (
    available_groups,
    isolate_all_non_essential,
    isolate_group,
    isolate_script,
)
from pytagmanager.perf.measure import measure_page_performance
from pytagmanager.perf.scripts import build_script_inventory

_PAGE = "perf_isolate.html"


def test_isolation_experiments_against_a_real_fixture(fixture_server):
    page_url = f"{fixture_server}/{_PAGE}"
    inventory = build_script_inventory(page_url, headless=True, wait_ms=1500)
    heavy_script_url = next(
        s.url for s in inventory.scripts if s.url.endswith("heavy_first_party.js")
    )
    vendor_script_url = next(s.url for s in inventory.scripts if "fbevents.js" in s.url)

    assert "ads" in available_groups(inventory)

    baseline = measure_page_performance(page_url, runs=1, headless=True)

    # --- isolate_script: blocking the heavy first-party script removes
    # its busy-wait cost -- a real, deterministic TBT signal.
    script_result = isolate_script(
        page_url,
        heavy_script_url,
        inventory=inventory,
        baseline=baseline,
        runs=1,
        headless=True,
    )
    assert heavy_script_url in script_result.blocked_urls
    assert script_result.tbt_delta_ms is not None
    assert script_result.tbt_delta_ms > 0  # TBT improved (dropped) once the busy-wait was blocked
    assert "observed" in script_result.message.lower()

    # --- isolate_group: "ads" should block the vendor script, not the
    # unrelated first-party heavy script.
    group_result = isolate_group(
        page_url, "ads", inventory=inventory, baseline=baseline, runs=1, headless=True
    )
    assert vendor_script_url in group_result.blocked_urls
    assert heavy_script_url not in group_result.blocked_urls

    # --- isolate_all_non_essential: blocks the classified vendor script,
    # never the unclassified first-party one.
    all_result = isolate_all_non_essential(
        page_url, inventory=inventory, baseline=baseline, runs=1, headless=True
    )
    assert vendor_script_url in all_result.blocked_urls
    assert heavy_script_url not in all_result.blocked_urls
