"""Real-browser end-to-end test for Phase 1.85 item 1's static scan:
`ObservationSession.capture_html()` against a real headless Chromium
session, feeding `tagexec.static_scan.scan_html()`.
"""

from __future__ import annotations

from pytagmanager.observability.scenario import ActionStep, Scenario
from pytagmanager.observability.session import ObservationSession
from pytagmanager.tagexec.static_scan import detect_delayed_containers, scan_html

_PAGE = "tagexec_static.html"


def test_static_scan_detects_gtm_container_and_vendor_from_real_page(fixture_server):
    with ObservationSession(headless=True) as session:
        session.load(f"{fixture_server}/{_PAGE}")
        html = session.capture_html()

    result = scan_html(html, f"{fixture_server}/{_PAGE}")

    assert "GTM-TEST1234" in result.gtm_container_ids
    vendors = {v.vendor for v in result.vendors}
    assert "Meta Pixel" in vendors


def test_static_scan_detects_delayed_gtm_container_after_interaction(fixture_server):
    scenario = Scenario(name="accept consent", steps=[ActionStep(action="click", selector='[data-testid="accept-consent"]')])
    with ObservationSession(headless=True) as session:
        session.load(f"{fixture_server}/{_PAGE}")
        baseline_html = session.capture_html()
        session.run_scenario(scenario)
        session.wait(0.5)
        later_html = session.capture_html()

    baseline = scan_html(baseline_html, f"{fixture_server}/{_PAGE}")
    later = scan_html(later_html, f"{fixture_server}/{_PAGE}")

    assert "GTM-DELAYED9" not in baseline.gtm_container_ids
    assert "GTM-DELAYED9" in later.gtm_container_ids

    delayed = detect_delayed_containers(baseline, later)
    assert delayed == ("GTM-DELAYED9",)
