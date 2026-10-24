"""Tests for Phase 1.85 item 1's static code intelligence
(docs/VISION.md §17): GTM container + vendor SDK detection from HTML."""

from __future__ import annotations

from pytagmanager.tagexec.static_scan import (
    detect_delayed_containers,
    detect_delayed_vendors,
    scan_html,
)

_GTM_SNIPPET = """
<script>(function(w,d,s,l,i){w[l]=w[l]||[];w[l].push({'gtm.start':
new Date().getTime(),event:'gtm.js'});var f=d.getElementsByTagName(s)[0],
j=d.createElement(s),dl=l!='dataLayer'?'&l='+l:'';j.async=true;j.src=
'https://www.googletagmanager.com/gtm.js?id='+i+dl;f.parentNode.insertBefore(j,f);
})(window,document,'script','dataLayer','GTM-ABC1234');</script>
"""
# What Playwright's page.content() actually shows post-render: the loader
# above dynamically inserts a real <script src="..."> tag into the DOM.
_RENDERED_GTM_SCRIPT_TAG = '<script async src="https://www.googletagmanager.com/gtm.js?id=GTM-ABC1234&l=dataLayer"></script>'

_NOSCRIPT_SNIPPET = """
<noscript><iframe src="https://www.googletagmanager.com/ns.html?id=GTM-XYZ9999"
height="0" width="0" style="display:none;visibility:hidden"></iframe></noscript>
"""


def test_detects_gtm_container_from_rendered_script_tag():
    html = f"<html><head>{_RENDERED_GTM_SCRIPT_TAG}</head><body></body></html>"
    result = scan_html(html, "https://example.com/")
    assert result.gtm_container_ids == ("GTM-ABC1234",)
    assert result.gtm_containers[0].load_mechanism == "script_tag"


def test_detects_gtm_container_from_noscript_iframe():
    html = f"<html><body>{_NOSCRIPT_SNIPPET}</body></html>"
    result = scan_html(html, "https://example.com/")
    assert result.gtm_container_ids == ("GTM-XYZ9999",)
    assert result.gtm_containers[0].load_mechanism == "noscript_iframe"


def test_detects_multiple_distinct_gtm_containers():
    html = (
        "<html><head>"
        + _RENDERED_GTM_SCRIPT_TAG
        + '<script async src="https://www.googletagmanager.com/gtm.js?id=GTM-SECOND1"></script>'
        + "</head></html>"
    )
    result = scan_html(html, "https://example.com/")
    assert set(result.gtm_container_ids) == {"GTM-ABC1234", "GTM-SECOND1"}
    assert result.has_multiple_gtm_containers is True


def test_no_gtm_containers_found_returns_empty_tuple():
    result = scan_html("<html><body>Hello</body></html>", "https://example.com/")
    assert result.gtm_containers == ()
    assert result.has_multiple_gtm_containers is False


def test_detects_ga4_via_gtag_config():
    html = "<script>gtag('config', 'G-ABCDE12345');</script>"
    result = scan_html(html, "https://example.com/")
    vendors = {v.vendor for v in result.vendors}
    assert "GA4" in vendors


def test_detects_meta_pixel_via_fbevents_script():
    html = '<script src="https://connect.facebook.net/en_US/fbevents.js"></script>'
    result = scan_html(html, "https://example.com/")
    vendors = {v.vendor for v in result.vendors}
    assert "Meta Pixel" in vendors


def test_detects_adobe_analytics_via_appmeasurement():
    html = '<script src="/scripts/AppMeasurement.js"></script>'
    result = scan_html(html, "https://example.com/")
    vendors = {v.vendor for v in result.vendors}
    assert "Adobe Analytics" in vendors


def test_detects_multiple_distinct_vendors():
    html = (
        '<script src="https://connect.facebook.net/en_US/fbevents.js"></script>'
        "<script>gtag('config', 'G-ABCDE12345');</script>"
        '<script src="https://static.hotjar.com/c/hotjar-123.js"></script>'
    )
    result = scan_html(html, "https://example.com/")
    vendors = {v.vendor for v in result.vendors}
    assert vendors == {"Meta Pixel", "GA4", "Hotjar"}


def test_vendor_detection_dedupes_identical_evidence():
    html = "<script>gtag('config', 'G-ABCDE12345');</script>" * 3
    result = scan_html(html, "https://example.com/")
    ga4 = [v for v in result.vendors if v.vendor == "GA4"]
    assert len(ga4) == 1


def test_unrecognized_vendor_produces_no_detection():
    html = '<script src="https://cdn.example-unknown-vendor.com/tracker.js"></script>'
    result = scan_html(html, "https://example.com/")
    assert result.vendors == ()


def test_detect_delayed_containers_finds_new_container_in_later_snapshot():
    baseline = scan_html("<html><body>no gtm yet</body></html>", "https://example.com/")
    later = scan_html(
        f"<html><head>{_RENDERED_GTM_SCRIPT_TAG}</head></html>", "https://example.com/"
    )

    delayed = detect_delayed_containers(baseline, later)
    assert delayed == ("GTM-ABC1234",)


def test_detect_delayed_containers_empty_when_present_in_both():
    html = f"<html><head>{_RENDERED_GTM_SCRIPT_TAG}</head></html>"
    baseline = scan_html(html, "https://example.com/")
    later = scan_html(html, "https://example.com/")

    assert detect_delayed_containers(baseline, later) == ()


def test_detect_delayed_vendors_finds_new_vendor_in_later_snapshot():
    baseline = scan_html("<html><body>nothing yet</body></html>", "https://example.com/")
    later = scan_html("<script>gtag('config', 'G-ABCDE12345');</script>", "https://example.com/")

    delayed = detect_delayed_vendors(baseline, later)
    assert len(delayed) == 1
    assert delayed[0].vendor == "GA4"
