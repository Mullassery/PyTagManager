"""Tests for Phase 1.85 item 3's hedged server-side tagging indicators
(docs/VISION.md §17). Every indicator must be hedged -- this file
specifically asserts no indicator's confidence or message ever reads as
an unhedged claim."""

from __future__ import annotations

from pytagmanager.diagnostics.trace import InteractionTrace, InteractionTraceStep
from pytagmanager.tagexec.server_side import (
    CONFIDENCE_LEVELS,
    KIND_FANOUT_TO_MULTIPLE_DESTINATIONS,
    KIND_FIRST_PARTY_COLLECTION_ENDPOINT,
    analyze_server_side_indicators,
    detect_fanout,
    detect_first_party_collection_endpoints,
)

# "confirmed" is deliberately not in this list -- the hedge phrase itself
# is "not confirmed", so banning the substring would reject the hedge.
_UNHEDGED_WORDS = ("definitely", "certainly", "proven", "guaranteed", "is confirmed")


def _network_step(url, timestamp=1.0):
    return InteractionTraceStep(
        stage="network",
        event_type="network_request",
        event_name="",
        timestamp=timestamp,
        source="network",
        selector=None,
        payload={"url": url},
    )


def _trace(steps, page_url="https://shop.example.com/product", business_event="add_to_cart"):
    return InteractionTrace(
        journey_id="j1",
        business_event=business_event,
        page_url=page_url,
        element_selector="#buy",
        start_time=0.0,
        end_time=1.0,
        status="healthy",
        steps=tuple(steps),
    )


# ---- first-party collection endpoint detection ----


def test_first_party_ga4_shaped_request_is_flagged():
    trace = _trace(
        [_network_step("https://shop.example.com/g/collect?v=2&tid=G-ABCDEFG&en=add_to_cart&cid=123")]
    )
    indicators = detect_first_party_collection_endpoints(trace)
    assert len(indicators) == 1
    assert indicators[0].kind == KIND_FIRST_PARTY_COLLECTION_ENDPOINT
    assert indicators[0].confidence == "Likely"


def test_third_party_ga4_request_is_not_flagged_as_first_party():
    # A request straight to Google's own domain is normal client-side GA4,
    # not evidence of a first-party server-side relay.
    trace = _trace([_network_step("https://www.google-analytics.com/g/collect?v=2&tid=G-ABCDEFG&en=add_to_cart")])
    assert detect_first_party_collection_endpoints(trace) == []


def test_first_party_request_without_ga4_shape_is_not_flagged():
    trace = _trace([_network_step("https://shop.example.com/api/cart")])
    assert detect_first_party_collection_endpoints(trace) == []


def test_first_party_subdomain_still_counts_as_first_party():
    trace = _trace(
        [_network_step("https://sgtm.example.com/g/collect?v=2&tid=G-ABCDEFG&en=add_to_cart")],
        page_url="https://shop.example.com/product",
    )
    indicators = detect_first_party_collection_endpoints(trace)
    assert len(indicators) == 1


# ---- fan-out detection ----


def test_fanout_to_two_distinct_external_hosts_is_flagged():
    trace = _trace(
        [
            _network_step("https://connect.facebook.net/tr?ev=Purchase"),
            _network_step("https://ads.tiktok.com/i18n/pixel/events.js"),
        ]
    )
    indicator = detect_fanout(trace)
    assert indicator is not None
    assert indicator.kind == KIND_FANOUT_TO_MULTIPLE_DESTINATIONS
    assert indicator.confidence == "Possible"


def test_single_external_host_is_not_a_fanout():
    trace = _trace([_network_step("https://connect.facebook.net/tr?ev=Purchase")])
    assert detect_fanout(trace) is None


def test_multiple_requests_to_the_same_external_host_is_not_a_fanout():
    trace = _trace(
        [
            _network_step("https://connect.facebook.net/tr?ev=Purchase&id=1"),
            _network_step("https://connect.facebook.net/tr?ev=Purchase&id=2"),
        ]
    )
    assert detect_fanout(trace) is None


def test_first_party_requests_do_not_count_toward_fanout():
    trace = _trace(
        [
            _network_step("https://shop.example.com/api/cart"),
            _network_step("https://shop.example.com/g/collect?v=2&tid=G-X&en=x"),
        ]
    )
    assert detect_fanout(trace) is None


# ---- aggregate ----


def test_analyze_server_side_indicators_across_multiple_traces():
    trace_a = _trace([_network_step("https://shop.example.com/g/collect?v=2&tid=G-ABCDEFG&en=add_to_cart")])
    trace_b = _trace(
        [
            _network_step("https://connect.facebook.net/tr?ev=Purchase"),
            _network_step("https://ads.tiktok.com/i18n/pixel/events.js"),
        ],
        business_event="purchase",
    )
    indicators = analyze_server_side_indicators([trace_a, trace_b])
    kinds = {i.kind for i in indicators}
    assert kinds == {KIND_FIRST_PARTY_COLLECTION_ENDPOINT, KIND_FANOUT_TO_MULTIPLE_DESTINATIONS}


def test_no_indicators_for_a_page_with_no_network_activity():
    trace = _trace([])
    assert analyze_server_side_indicators([trace]) == []


# ---- the hedging discipline itself ----


def test_confidence_levels_never_include_confirmed():
    assert "Confirmed" not in CONFIDENCE_LEVELS
    assert set(CONFIDENCE_LEVELS) == {"Likely", "Possible"}


def test_no_indicator_ever_emits_an_unhedged_claim():
    traces = [
        _trace([_network_step("https://shop.example.com/g/collect?v=2&tid=G-ABCDEFG&en=add_to_cart")]),
        _trace(
            [
                _network_step("https://connect.facebook.net/tr?ev=Purchase"),
                _network_step("https://ads.tiktok.com/i18n/pixel/events.js"),
            ]
        ),
    ]
    indicators = analyze_server_side_indicators(traces)
    assert indicators, "test setup should have produced at least one indicator to check"
    for indicator in indicators:
        assert indicator.confidence in CONFIDENCE_LEVELS
        assert indicator.confidence != "Confirmed"
        lowered = indicator.message.lower()
        for word in _UNHEDGED_WORDS:
            assert word not in lowered, f"unhedged word {word!r} found in: {indicator.message}"
        assert "not confirmed" in lowered or "not observable" in lowered
