"""Hedged server-side GTM/tagging indicator detection (docs/VISION.md §17,
Phase 1.85 item 3): first-party collection/proxy endpoints, one browser
event fanning out to multiple vendor destinations, and known
tagging-endpoint request shapes proxied through a first-party domain.

**Every output here is hedged, by construction.** Server-side tagging is,
almost by definition, invisible to client-side observation -- what a
browser sees is a first-party network request; whether that request is
relayed to a vendor by a real server-side GTM container, a homegrown
proxy, or nothing at all downstream is not something this module (or any
purely client-side tool) can confirm. `CONFIDENCE_LEVELS` deliberately
excludes "Confirmed": the strongest claim this module ever makes is
"Likely", and every `ServerSideIndicator.message` is worded as a
possibility, never a fact. `test_tagexec_server_side.py` asserts this
directly -- no indicator's confidence or message ever reads as an
unhedged claim.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from urllib.parse import parse_qs, urlparse

from pytagmanager.diagnostics.trace import InteractionTrace, InteractionTraceStep

# Deliberately does not include "Confirmed" -- see module docstring.
CONFIDENCE_LEVELS = ("Likely", "Possible")

KIND_FIRST_PARTY_COLLECTION_ENDPOINT = "first_party_collection_endpoint"
KIND_FANOUT_TO_MULTIPLE_DESTINATIONS = "fanout_to_multiple_destinations"


@dataclass(frozen=True)
class ServerSideIndicator:
    kind: str
    page_url: str
    business_event: str
    evidence: str
    confidence: str  # one of CONFIDENCE_LEVELS
    message: str


def _hostname(url: str) -> str:
    return (urlparse(url).hostname or "").lower()


def _registrable_domain(hostname: str) -> str:
    """Naive eTLD+1 approximation (last two dot-separated labels) -- does
    not correctly handle multi-part public suffixes like `co.uk`. Good
    enough to tell "same site" from "different site" for the vendor
    domains this module cares about (all plain `.com`/`.net`/etc.), not
    intended as a general-purpose public-suffix implementation."""
    labels = hostname.split(".")
    return ".".join(labels[-2:]) if len(labels) >= 2 else hostname


def _is_first_party(request_url: str, page_url: str) -> bool:
    request_host = _hostname(request_url)
    page_host = _hostname(page_url)
    if not request_host or not page_host:
        return False
    return _registrable_domain(request_host) == _registrable_domain(page_host)


def _looks_like_ga4_measurement_protocol(params: dict) -> bool:
    """GA4's Measurement Protocol / gtag.js hit shape: a `tid` (tracking
    ID, `G-XXXXXXX`) plus a `v`ersion and either `en` (event name) or `t`
    (hit type) parameter. First-party-hosted but shaped like this is the
    single strongest (still hedged) signal of a server-side relay."""
    tid = params.get("tid", [""])[0] if "tid" in params else ""
    has_version = "v" in params
    has_event_marker = "en" in params or "t" in params
    return bool(tid) and tid.startswith(("G-", "UA-")) and has_version and has_event_marker


def _network_steps(trace: InteractionTrace) -> list[InteractionTraceStep]:
    return [s for s in trace.steps if s.event_type == "network_request"]


def detect_first_party_collection_endpoints(
    trace: InteractionTrace,
) -> list[ServerSideIndicator]:
    indicators = []
    for step in _network_steps(trace):
        url = step.payload.get("url", "") if isinstance(step.payload, dict) else ""
        if not url or not _is_first_party(url, trace.page_url):
            continue
        params = parse_qs(urlparse(url).query)
        if _looks_like_ga4_measurement_protocol(params):
            indicators.append(
                ServerSideIndicator(
                    kind=KIND_FIRST_PARTY_COLLECTION_ENDPOINT,
                    page_url=trace.page_url,
                    business_event=trace.business_event,
                    evidence=url,
                    confidence="Likely",
                    message=(
                        f"Likely server-side tagging endpoint: a first-party request to {_hostname(url)} "
                        "carries a GA4 Measurement Protocol-shaped payload (tid/v/en). Not confirmed -- "
                        "this could also be a first-party analytics implementation that happens to reuse "
                        "the same parameter names, and whether anything relays this request onward to a "
                        "vendor server-side is not observable from the browser."
                    ),
                )
            )
    return indicators


def detect_fanout(trace: InteractionTrace) -> ServerSideIndicator | None:
    """More than one *distinct external* (non-first-party) host receiving
    a network request for the same interaction is consistent with -- not
    proof of -- one first-party event being fanned out server-side to
    multiple vendor destinations. It's equally consistent with the page
    simply having multiple independent client-side tags installed, which
    is why this is "Possible", the weaker of the two confidence levels."""
    external_hosts = {
        _hostname(step.payload.get("url", ""))
        for step in _network_steps(trace)
        if isinstance(step.payload, dict)
        and step.payload.get("url")
        and not _is_first_party(step.payload["url"], trace.page_url)
    }
    external_hosts.discard("")
    if len(external_hosts) < 2:
        return None
    return ServerSideIndicator(
        kind=KIND_FANOUT_TO_MULTIPLE_DESTINATIONS,
        page_url=trace.page_url,
        business_event=trace.business_event,
        evidence=", ".join(sorted(external_hosts)),
        confidence="Possible",
        message=(
            f"Possible fan-out to multiple vendor destinations: '{trace.business_event}' produced "
            f"requests to {len(external_hosts)} distinct external hosts ({', '.join(sorted(external_hosts))}). "
            "Not confirmed -- this is equally consistent with several independent client-side tags "
            "installed on the page as it is with one event being relayed server-side to multiple "
            "destinations; this module cannot distinguish the two from network traffic alone."
        ),
    )


def analyze_server_side_indicators(
    traces: Sequence[InteractionTrace],
) -> list[ServerSideIndicator]:
    indicators: list[ServerSideIndicator] = []
    for trace in traces:
        indicators.extend(detect_first_party_collection_endpoints(trace))
        fanout = detect_fanout(trace)
        if fanout is not None:
            indicators.append(fanout)
    return indicators
