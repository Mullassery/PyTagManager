"""Browser-backed CMP evidence collection.

The collector is deliberately read-only until an explicit, separate
authorization is supplied for a consent-choice interaction. It records what
the page exposed (markup, CMP globals, cookies, consent-mode calls, network
requests) and never submits a consent choice on its own.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Iterable, List, Optional, Sequence, Tuple
from urllib.parse import urlsplit

from pytagmanager.cmp.adapters import (
    ADAPTERS,
    CmpAdapter,
    adapter_for,
    cookie_presence_state,
    detect_adapters,
    extract_signals,
    merge_consent_states,
    parse_google_consent_mode,
    read_gpp_consent,
    read_tcf_consent,
    read_vendor_consent,
)
from pytagmanager.cmp.models import (
    CmpAuditReport,
    CmpDetection,
    ConsentLifecycle,
    ConsentState,
    CookieMetadata,
    RequestObservation,
    sanitize_url,
)
from pytagmanager.cmp.rules import analyze_cmp
from pytagmanager.observability.events import TrackingEvent
from pytagmanager.observability.session import ObservationSession

_CONSENT_ACTIONS = frozenset({"none", "accept", "reject"})

_ANALYTICS_HOSTS = (
    "google-analytics.com",
    "analytics.google.com",
    "segment.io",
    "segment.com",
    "amplitude.com",
    "mixpanel.com",
    "heap.io",
    "fullstory.com",
    "hotjar.com",
    "matomo.cloud",
    "plausible.io",
    "clarity.ms",
    "statcounter.com",
    "simpleanalytics.com",
    "umami.is",
)

_ADVERTISING_HOSTS = (
    "doubleclick.net",
    "googleadservices.com",
    "googlesyndication.com",
    "facebook.com",
    "connect.facebook.net",
    "tiktok.com",
    "linkedin.com",
    "snap.licdn.com",
    "pinterest.com",
    "criteo.com",
    "criteo.net",
    "taboola.com",
    "outbrain.com",
    "bing.com",
    "adnxs.com",
    "amazon-adsystem.com",
    "quantserve.com",
    "adsrvr.org",
    "rubiconproject.com",
    "pubmatic.com",
)

_CONSENT_HOSTS = (
    "cookiebot.com",
    "cookiebot.eu",
    "cookielaw.org",
    "usercentrics.eu",
    "usercentrics.com",
    "didomi.io",
    "privacy-center.org",
    "quantcast.mgr.consensu.org",
    "trustarc.com",
    "osano.com",
    "fundingchoicesmessages.google.com",
    "consentmanager.net",
    "sourcepoint.com",
    "sp-prod.net",
    "iubenda.com",
    "cookieyes.com",
    "termly.io",
)

_CMP_LIMITATIONS = (
    "This is an evidence report, not a legal compliance determination or legal advice.",
    "A visible consent banner is not proof that consent is enforced; no banner was treated as compliance.",
    "Server-side consent enforcement, logged-in states, and cross-device consent were not tested.",
    "Cookie values were not persisted; cookie presence alone does not prove which categories were granted.",
    "Only documented vendor, TCF v2, and GPP APIs are read directly; other vendor states are reported as cookie/markup evidence.",
    "TCF/GPP data is self-reported by the page or its CMP; raw TC/GPP strings and parsed GPP payloads are not retained.",
    "This run used a read-only observation session unless consent interaction was explicitly authorized.",
)


class CmpAuditAuthorizationError(RuntimeError):
    """Raised when a consent choice would be executed without explicit opt-in."""


@dataclass(frozen=True)
class CmpAuditOptions:
    headless: bool = True
    browser_name: str = "chromium"
    accept_selectors: Tuple[str, ...] = ()
    reject_selectors: Tuple[str, ...] = ()
    wait_seconds: float = 1.0
    selector_timeout_ms: int = 5000
    reload_after_consent: bool = False
    max_network_events: int = 500
    extra_adapters: Tuple[CmpAdapter, ...] = ()


class CmpAuditRunner:
    def __init__(self, options: Optional[CmpAuditOptions] = None):
        self.options = options or CmpAuditOptions()
        self.adapters = _adapter_registry(self.options.extra_adapters)

    def run(
        self,
        url: str,
        *,
        consent_action: str = "none",
        authorize_consent_interaction: bool = False,
    ) -> CmpAuditReport:
        if consent_action not in _CONSENT_ACTIONS:
            raise ValueError(f"consent_action must be one of {sorted(_CONSENT_ACTIONS)}")
        if consent_action != "none" and not authorize_consent_interaction:
            raise CmpAuditAuthorizationError(
                "Consent interaction requires explicit authorization. "
                "Pass authorize_consent_interaction=True only for a test environment you control."
            )

        started_at = time.time()
        lifecycle = ConsentLifecycle(
            requested_action=consent_action,
            authorized=authorize_consent_interaction,
            started_at=started_at,
        )
        action_timestamp: Optional[float] = None
        reload_timestamp: Optional[float] = None
        consent_after_action: Optional[ConsentState] = None
        consent_after_reload: Optional[ConsentState] = None
        reloaded = False

        with ObservationSession(
            headless=self.options.headless,
            browser_name=self.options.browser_name,
            capture_all_network=True,
            max_network_events=self.options.max_network_events,
        ) as session:
            session.load(url)
            initial_html = session.capture_html()
            initial_cookies = session.browser_cookies()
            globals_present = _present_globals(session, self.adapters)
            network_urls = _network_urls(session.events)
            signals = extract_signals(
                html=initial_html,
                cookie_names=[cookie.get("name", "") for cookie in initial_cookies],
                globals_present=globals_present,
                network_urls=network_urls,
            )
            detections = detect_adapters(signals, adapters=self.adapters)
            initial_timestamp = time.time()
            initial_state = _current_consent_state(
                session,
                detections,
                [cookie.get("name", "") for cookie in initial_cookies],
                session.events,
                initial_timestamp,
                self.adapters,
            )

            if consent_action != "none":
                action_timestamp = time.time()
                selectors = self._selectors_for(detections, consent_action)
                lifecycle, used_selector = self._perform_action(
                    session, lifecycle, selectors, action_timestamp
                )
                if lifecycle.performed:
                    session.wait(self.options.wait_seconds)
                    current_cookies = session.browser_cookies()
                    consent_after_action = _current_consent_state(
                        session,
                        detections,
                        [cookie.get("name", "") for cookie in current_cookies],
                        session.events,
                        time.time(),
                        self.adapters,
                    )
                    if self.options.reload_after_consent:
                        reload_timestamp = time.time()
                        session.reload()
                        session.wait(self.options.wait_seconds)
                        reloaded_events = [
                            event for event in session.events if event.timestamp >= reload_timestamp
                        ]
                        consent_after_reload = _current_consent_state(
                            session,
                            detections,
                            [cookie.get("name", "") for cookie in session.browser_cookies()],
                            reloaded_events,
                            time.time(),
                            self.adapters,
                        )
                        reloaded = True
                if not lifecycle.performed:
                    action_timestamp = None
                lifecycle = ConsentLifecycle(
                    requested_action=lifecycle.requested_action,
                    authorized=lifecycle.authorized,
                    performed=lifecycle.performed,
                    selector=used_selector,
                    failure_reason=lifecycle.failure_reason,
                    reloaded=reloaded,
                    started_at=lifecycle.started_at,
                    completed_at=time.time(),
                )
            else:
                lifecycle = ConsentLifecycle(
                    requested_action="none",
                    authorized=authorize_consent_interaction,
                    performed=False,
                    started_at=started_at,
                    completed_at=time.time(),
                )

            final_cookies = session.browser_cookies()
            final_html = session.capture_html()
            final_signals = extract_signals(
                html=final_html,
                cookie_names=[cookie.get("name", "") for cookie in final_cookies],
                globals_present=_present_globals(session, self.adapters),
                network_urls=_network_urls(session.events),
            )
            final_detections = _merge_detections(
                detections, detect_adapters(final_signals, adapters=self.adapters)
            )
            requests = _request_observations(
                session.events, action_timestamp, reload_timestamp
            )

        cookie_metadata = _cookie_metadata(final_cookies, final_detections, self.adapters)
        limitations = list(_CMP_LIMITATIONS)
        if consent_action == "none":
            limitations.append(
                "No consent choice was exercised; post-choice and withdrawal behavior was not tested."
            )
        elif not lifecycle.performed:
            limitations.append(
                "The requested consent interaction could not be performed, so post-choice behavior was not tested."
            )
        elif not reloaded:
            limitations.append("The page was not reloaded, so consent persistence was not tested.")
        if not final_detections:
            limitations.append(
                "No supported CMP signature was detected. Absence of detection is not evidence that consent management is absent."
            )
        if final_detections and not initial_state.has_categories:
            limitations.append(
                "The CMP was detected but its category state could not be read from a documented API or Consent Mode signal."
            )

        findings = analyze_cmp(
            url=url,
            detections=final_detections,
            initial_state=initial_state,
            after_action_state=consent_after_action,
            after_reload_state=consent_after_reload,
            lifecycle=lifecycle,
            requests=requests,
            cookies=cookie_metadata,
            adapters=self.adapters,
        )

        return CmpAuditReport(
            url=url,
            generated_at=time.time(),
            mode="browser",
            detections=final_detections,
            consent_initial=initial_state,
            consent_after_action=consent_after_action,
            consent_after_reload=consent_after_reload,
            lifecycle=lifecycle,
            cookies=cookie_metadata,
            requests=requests,
            findings=findings,
            limitations=tuple(limitations),
        )

    def _selectors_for(self, detections: Sequence[CmpDetection], action: str) -> Tuple[str, ...]:
        explicit = self.options.accept_selectors if action == "accept" else self.options.reject_selectors
        if explicit:
            return tuple(explicit)
        selectors: List[str] = []
        for detection in detections:
            values = detection.accept_selectors if action == "accept" else detection.reject_selectors
            selectors.extend(value for value in values if value not in selectors)
        return tuple(selectors)

    def _perform_action(
        self,
        session: ObservationSession,
        lifecycle: ConsentLifecycle,
        selectors: Sequence[str],
        started_at: float,
    ) -> Tuple[ConsentLifecycle, str]:
        if not selectors:
            return (
                ConsentLifecycle(
                    requested_action=lifecycle.requested_action,
                    authorized=lifecycle.authorized,
                    performed=False,
                    failure_reason="no_selector_available",
                    started_at=started_at,
                    completed_at=time.time(),
                ),
                "",
            )
        for selector in selectors:
            if session.click(selector, timeout_ms=self.options.selector_timeout_ms):
                return (
                    ConsentLifecycle(
                        requested_action=lifecycle.requested_action,
                        authorized=lifecycle.authorized,
                        performed=True,
                        selector=selector,
                        started_at=started_at,
                        completed_at=time.time(),
                    ),
                    selector,
                )
        return (
            ConsentLifecycle(
                requested_action=lifecycle.requested_action,
                authorized=lifecycle.authorized,
                performed=False,
                failure_reason="selector_not_found_or_unclickable",
                started_at=started_at,
                completed_at=time.time(),
            ),
            "",
        )


def _adapter_registry(extra_adapters: Sequence[CmpAdapter]) -> Tuple[CmpAdapter, ...]:
    registry = list(ADAPTERS)
    seen = {adapter.adapter_id for adapter in registry}
    for adapter in extra_adapters:
        if not adapter.adapter_id:
            raise ValueError("custom CMP adapter is missing adapter_id")
        if adapter.adapter_id in seen:
            raise ValueError(f"duplicate CMP adapter id: {adapter.adapter_id}")
        seen.add(adapter.adapter_id)
        registry.append(adapter)
    return tuple(registry)


def _present_globals(
    session: ObservationSession, adapters: Sequence[CmpAdapter]
) -> Tuple[str, ...]:
    names = sorted({name for adapter in adapters for name in adapter.global_names})
    script = """
    (names) => names.filter((name) => {
      try { return !!window[name]; } catch (error) { return false; }
    })
    """
    try:
        result = session.evaluate(script, names)
    except Exception:
        return ()
    return tuple(result or ())


def _network_urls(events: Iterable[TrackingEvent]) -> Tuple[str, ...]:
    urls = []
    for event in events:
        if event.event_type != "network_request" or not isinstance(event.payload, dict):
            continue
        url = event.payload.get("url")
        if isinstance(url, str) and url:
            urls.append(url)
    return tuple(urls)


def _current_consent_state(
    session: ObservationSession,
    detections: Sequence[CmpDetection],
    cookie_names: Sequence[str],
    events: Sequence[TrackingEvent],
    timestamp: float,
    adapters: Sequence[CmpAdapter],
) -> ConsentState:
    states = [
        read_vendor_consent(detections, session, timestamp=timestamp, adapters=adapters),
        read_tcf_consent(session, timestamp=timestamp),
        read_gpp_consent(session, timestamp=timestamp),
        parse_google_consent_mode(events, timestamp=timestamp),
        cookie_presence_state(
            detections, cookie_names, timestamp=timestamp, adapters=adapters
        ),
    ]
    return merge_consent_states([state for state in states if state is not None], timestamp=timestamp)


def _merge_detections(
    first: Sequence[CmpDetection], second: Sequence[CmpDetection]
) -> Tuple[CmpDetection, ...]:
    by_id = {item.adapter_id: item for item in first}
    order = [item.adapter_id for item in first]
    for item in second:
        if item.adapter_id not in by_id:
            by_id[item.adapter_id] = item
            order.append(item.adapter_id)
        elif _confidence_rank(item.confidence) > _confidence_rank(by_id[item.adapter_id].confidence):
            by_id[item.adapter_id] = item
    return tuple(by_id[adapter_id] for adapter_id in order)


def _confidence_rank(value: str) -> int:
    return {"unverified": 0, "suspected": 1, "high-confidence": 2, "confirmed": 3}.get(value, 0)


_NON_COLLECTION_RESOURCE_TYPES = frozenset(
    {"script", "stylesheet", "document", "font", "media", "manifest", "websocket", "eventsource", "texttrack"}
)
_COLLECTION_PATH_MARKERS = (
    "/g/collect",
    "/mp/collect",
    "/collect",
    "/tr",
    "/pixel",
    "/px",
    "/beacon",
    "/track",
    "/event",
    "/batch",
)


def _classify_request(url: str, resource_type: str = "") -> str:
    lowered = url.lower()
    parsed = urlsplit(lowered)
    host = parsed.netloc
    path = parsed.path
    if any(name in host for name in _CONSENT_HOSTS):
        return "consent"
    if path.endswith("/g/collect") or path.endswith("/mp/collect"):
        category = "analytics"
    elif any(name in host for name in _ADVERTISING_HOSTS):
        category = "advertising"
    elif any(name in host for name in _ANALYTICS_HOSTS):
        category = "analytics"
    else:
        return "other"
    resource = (resource_type or "").lower()
    if resource in _NON_COLLECTION_RESOURCE_TYPES and not any(
        marker in path for marker in _COLLECTION_PATH_MARKERS
    ):
        return "other"
    return category


def _request_observations(
    events: Sequence[TrackingEvent],
    action_timestamp: Optional[float],
    reload_timestamp: Optional[float],
) -> Tuple[RequestObservation, ...]:
    observations = []
    for event in events:
        if event.event_type != "network_request" or not isinstance(event.payload, dict):
            continue
        url = event.payload.get("url")
        if not isinstance(url, str) or not url:
            continue
        if reload_timestamp is not None and event.timestamp >= reload_timestamp:
            phase = "after_reload"
        elif action_timestamp is not None and event.timestamp >= action_timestamp:
            phase = "after_action"
        else:
            phase = "initial"
        resource_type = str(event.payload.get("resource_type", ""))
        observations.append(
            RequestObservation(
                url=sanitize_url(url),
                method=str(event.payload.get("method", "")),
                category=_classify_request(url, resource_type),
                phase=phase,
                host=urlsplit(url).netloc,
                timestamp=event.timestamp,
                network_pattern=str(event.payload.get("network_pattern", "")),
                resource_type=resource_type,
            )
        )
    return tuple(observations)


def _cookie_metadata(
    cookies: Sequence[dict],
    detections: Sequence[CmpDetection],
    adapters: Sequence[CmpAdapter],
) -> Tuple[CookieMetadata, ...]:
    cmp_names = set()
    cmp_prefixes = []
    for detection in detections:
        adapter = adapter_for(detection, adapters=adapters)
        if adapter is None:
            continue
        cmp_names.update(adapter.cookie_names)
        cmp_prefixes.extend(adapter.cookie_prefixes)
    result = []
    for cookie in sorted(cookies, key=lambda item: str(item.get("name", ""))):
        name = str(cookie.get("name", ""))
        if not name:
            continue
        related = name in cmp_names or any(
            name.lower().startswith(prefix.lower()) for prefix in cmp_prefixes
        )
        result.append(
            CookieMetadata(
                name=name,
                domain=str(cookie.get("domain", "")),
                path=str(cookie.get("path", "")),
                secure=bool(cookie.get("secure", False)),
                http_only=bool(cookie.get("httpOnly", False)),
                same_site=str(cookie.get("sameSite", "")),
                expires=float(cookie.get("expires", 0.0) or 0.0),
                cmp_related=related,
            )
        )
    return tuple(result)
