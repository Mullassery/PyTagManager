"""CMP detection adapters and documented consent-signal readers.

An adapter is a *declaration of what was observed*, not a claim that the
vendor's consent enforcement is correct. Detection can come from a vendor
script, a vendor global, a known cookie name, or a consent-platform network
request. Only Cookiebot exposes a documented enough client-side consent
object to be read directly here; other adapters report cookie presence
without decoding it.
"""

from __future__ import annotations

from dataclasses import dataclass
from html.parser import HTMLParser
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

from pytagmanager.cmp.models import (
    CATEGORIES,
    CmpDetection,
    CmpEvidence,
    ConsentState,
    sanitize_url,
)
from pytagmanager.observability.events import TrackingEvent

_GCM_KEYS = (
    "ad_storage",
    "ad_user_data",
    "ad_personalization",
    "analytics_storage",
    "functionality_storage",
    "personalization_storage",
    "security_storage",
    "region",
    "wait_for_update",
)


class _ScriptExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.script_sources: List[str] = []
        self.inline_scripts: List[str] = []
        self._in_script = False
        self._current: List[str] = []

    def handle_starttag(self, tag: str, attrs) -> None:
        if tag.lower() != "script":
            return
        attributes = {name.lower(): value or "" for name, value in attrs}
        if attributes.get("src"):
            self.script_sources.append(attributes["src"])
        self._in_script = True
        self._current = []

    def handle_data(self, data: str) -> None:
        if self._in_script:
            self._current.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() == "script" and self._in_script:
            self.inline_scripts.append("".join(self._current))
            self._current = []
            self._in_script = False


@dataclass(frozen=True)
class DetectionSignals:
    html: str = ""
    script_sources: Tuple[str, ...] = ()
    inline_scripts: Tuple[str, ...] = ()
    cookie_names: Tuple[str, ...] = ()
    globals: Tuple[str, ...] = ()
    network_urls: Tuple[str, ...] = ()


def extract_signals(
    *,
    html: str,
    cookie_names: Sequence[str] = (),
    globals_present: Sequence[str] = (),
    network_urls: Sequence[str] = (),
) -> DetectionSignals:
    parser = _ScriptExtractor()
    try:
        parser.feed(html or "")
        parser.close()
    except Exception:
        pass
    return DetectionSignals(
        html=html or "",
        script_sources=tuple(parser.script_sources),
        inline_scripts=tuple(parser.inline_scripts),
        cookie_names=tuple(sorted(set(cookie_names))),
        globals=tuple(sorted(set(globals_present))),
        network_urls=tuple(sorted(set(network_urls))),
    )


class CmpAdapter:
    adapter_id = ""
    vendor = ""
    contract_version = "1"
    script_markers: Tuple[str, ...] = ()
    url_markers: Tuple[str, ...] = ()
    markup_markers: Tuple[str, ...] = ()
    global_names: Tuple[str, ...] = ()
    cookie_names: Tuple[str, ...] = ()
    cookie_prefixes: Tuple[str, ...] = ()
    accept_selectors: Tuple[str, ...] = ()
    reject_selectors: Tuple[str, ...] = ()
    notes: Tuple[str, ...] = ()
    supports_consent_api = False

    def detect(self, signals: DetectionSignals) -> Optional[CmpDetection]:
        evidence: List[CmpEvidence] = []
        strong = False
        medium = False

        for source in signals.script_sources:
            lowered = source.lower()
            if any(marker in lowered for marker in self.script_markers):
                strong = True
                evidence.append(
                    CmpEvidence(
                        kind="script",
                        source="html",
                        summary=f"{self.vendor} script tag referenced",
                        value=sanitize_url(source),
                    )
                )
        for url in signals.network_urls:
            lowered = url.lower()
            if any(marker in lowered for marker in self.url_markers):
                medium = True
                evidence.append(
                    CmpEvidence(
                        kind="network",
                        source="network",
                        summary=f"{self.vendor} network endpoint observed",
                        value=sanitize_url(url),
                    )
                )
        for name in signals.globals:
            if name in self.global_names:
                strong = True
                evidence.append(
                    CmpEvidence(
                        kind="global",
                        source="javascript",
                        summary=f"{self.vendor} global present: window.{name}",
                        value=name,
                    )
                )
        for cookie in signals.cookie_names:
            if cookie in self.cookie_names or any(
                cookie.lower().startswith(prefix.lower()) for prefix in self.cookie_prefixes
            ):
                medium = True
                evidence.append(
                    CmpEvidence(
                        kind="cookie",
                        source="cookie",
                        summary=f"{self.vendor} consent cookie present: {cookie}",
                        value=cookie,
                    )
                )
        inline = "\n".join(signals.inline_scripts).lower()
        for marker in self.markup_markers:
            if marker.lower() in inline:
                evidence.append(
                    CmpEvidence(
                        kind="markup",
                        source="html",
                        summary=f"{self.vendor} marker present in inline script",
                        value=marker,
                    )
                )
                break

        if not evidence:
            return None
        if strong:
            confidence = "confirmed"
        elif medium:
            confidence = "high-confidence"
        else:
            confidence = "suspected"

        capabilities = ["detection"]
        if self.accept_selectors or self.reject_selectors:
            capabilities.append("consent_controls")
        if self.cookie_names or self.cookie_prefixes:
            capabilities.append("consent_cookie")
        if self.supports_consent_api:
            capabilities.append("consent_api")

        return CmpDetection(
            adapter_id=self.adapter_id,
            vendor=self.vendor,
            adapter_contract_version=self.contract_version,
            confidence=confidence,
            evidence=tuple(evidence),
            capabilities=tuple(capabilities),
            accept_selectors=self.accept_selectors,
            reject_selectors=self.reject_selectors,
            notes=self.notes,
        )

    def read_consent(self, session, timestamp: float = 0.0) -> Optional[ConsentState]:
        return None


class CookiebotAdapter(CmpAdapter):
    adapter_id = "cookiebot"
    vendor = "Cookiebot"
    script_markers = ("consent.cookiebot.com", "consent.cookiebot.eu", "cookiebot.com/uc.js")
    url_markers = ("consent.cookiebot.com", "consent.cookiebot.eu")
    markup_markers = ("cookiebot", "cookieconsent")
    global_names = ("Cookiebot",)
    cookie_names = ("CookieConsent",)
    accept_selectors = (
        "#CybotCookiebotDialogBodyLevelButtonLevelOptinAllowAll",
        "#CybotCookiebotDialogBodyButtonAccept",
    )
    reject_selectors = ("#CybotCookiebotDialogBodyButtonDecline",)
    notes = ("Consent object read via the documented window.Cookiebot.consent API.",)
    supports_consent_api = True

    def read_consent(self, session, timestamp: float = 0.0) -> Optional[ConsentState]:
        script = """
        () => {
          const consent = window.Cookiebot && window.Cookiebot.consent;
          if (!consent) return null;
          return {
            necessary: consent.necessary,
            preferences: consent.preferences,
            statistics: consent.statistics,
            marketing: consent.marketing
          };
        }
        """
        try:
            raw = session.evaluate(script)
        except Exception:
            return None
        if not isinstance(raw, dict):
            return None
        categories = {
            "necessary": True if raw.get("necessary") is not False else False,
            "preferences": _as_bool(raw.get("preferences")),
            "analytics": _as_bool(raw.get("statistics")),
            "advertising": _as_bool(raw.get("marketing")),
            "other": None,
        }
        if all(value is None for value in categories.values()):
            return None
        evidence = (
            CmpEvidence(
                kind="consent_api",
                source="javascript",
                summary="Cookiebot consent object read",
                value="window.Cookiebot.consent",
                timestamp=timestamp,
            ),
        )
        return ConsentState(
            sources=("cookiebot_consent",),
            categories=categories,
            confidence="confirmed",
            timestamp=timestamp,
            evidence=evidence,
        )


class OneTrustAdapter(CmpAdapter):
    adapter_id = "onetrust"
    vendor = "OneTrust"
    script_markers = ("cdn.cookielaw.org", "onetrust.com")
    url_markers = ("cdn.cookielaw.org", "onetrust.com")
    markup_markers = ("onetrust", "optanon")
    global_names = ("OneTrust", "OnetrustActiveGroups")
    cookie_names = ("OptanonConsent", "OptanonAlertBoxClosed")
    cookie_prefixes = ("Optanon",)
    accept_selectors = ("#onetrust-accept-btn-handler",)
    reject_selectors = ("#onetrust-reject-all-handler", ".ot-pc-refuse-all-handler")
    notes = ("Cookie presence is reported; OneTrust categories are not decoded.",)


class UsercentricsAdapter(CmpAdapter):
    adapter_id = "usercentrics"
    vendor = "Usercentrics"
    script_markers = ("usercentrics.eu", "usercentrics.com", "app.usercentrics.eu")
    url_markers = ("usercentrics.eu", "usercentrics.com")
    markup_markers = ("usercentrics", "uc-ui")
    global_names = ("UC_UI",)
    cookie_names = ("uc_user_interaction", "uc_settings")
    cookie_prefixes = ()
    accept_selectors = ('[data-testid="uc-accept-all-button"]',)
    reject_selectors = ('[data-testid="uc-deny-all-button"]',)
    notes = ("Cookie presence is reported; Usercentrics categories are not decoded.",)


class DidomiAdapter(CmpAdapter):
    adapter_id = "didomi"
    vendor = "Didomi"
    script_markers = ("didomi.io", "sdk.privacy-center.org")
    url_markers = ("didomi.io", "privacy-center.org")
    markup_markers = ("didomi",)
    global_names = ("Didomi",)
    cookie_names = ("didomi_token", "didomi_id")
    cookie_prefixes = ("didomi_",)
    accept_selectors = ("#didomi-notice-agree-button",)
    reject_selectors = ("#didomi-notice-disagree-button",)
    notes = ("Cookie presence is reported; Didomi categories are not decoded.",)


class QuantcastAdapter(CmpAdapter):
    adapter_id = "quantcast"
    vendor = "Quantcast Choice"
    script_markers = ("quantcast.mgr.consensu.org", "quantcast.com/choice")
    url_markers = ("quantcast.mgr.consensu.org", "quantcast.com")
    markup_markers = ("qc-cmp2", "quantcast")
    global_names = ("__qc", "__cmp")
    cookie_names = ("__cmpConsent", "__cmpConsentx", "__cmpLocator", "__cmpTCLocator")
    cookie_prefixes = ("__cmp",)
    accept_selectors = ('.qc-cmp2-summary-buttons button[mode="primary"]',)
    reject_selectors = ('.qc-cmp2-summary-buttons button[mode="secondary"]',)
    notes = ("Selectors are best-effort; verify against the deployed CMP version.",)


class TrustArcAdapter(CmpAdapter):
    adapter_id = "trustarc"
    vendor = "TrustArc"
    script_markers = ("consent.trustarc.com", "trustarc.com")
    url_markers = ("consent.trustarc.com", "trustarc.com")
    markup_markers = ("trustarc", "truste")
    global_names = ("truste", "TrustArc")
    cookie_names = ("notice_preferences", "notice_gdpr_prefs", "cmapi_cookie_privacy", "cmapi_gtm_bl")
    cookie_prefixes = ("notice_", "cmapi_")
    accept_selectors = ("#truste-consent-button",)
    reject_selectors = ("#truste-consent-required",)
    notes = ("Selectors are best-effort; verify against the deployed CMP version.",)


class OsanoAdapter(CmpAdapter):
    adapter_id = "osano"
    vendor = "Osano"
    script_markers = ("cmp.osano.com", "osano.com")
    url_markers = ("cmp.osano.com", "osano.com")
    markup_markers = ("osano",)
    global_names = ("Osano",)
    cookie_names = ("osano_consentmanager", "osano_consentmanager_uuid")
    cookie_prefixes = ("osano_",)
    accept_selectors = (".osano-cm-accept-all",)
    reject_selectors = (".osano-cm-deny-all",)
    notes = ("Cookie presence is reported; Osano categories are not decoded.",)


class GoogleFundingChoicesAdapter(CmpAdapter):
    adapter_id = "google-funding-choices"
    vendor = "Google Funding Choices"
    script_markers = ("fundingchoicesmessages.google.com",)
    url_markers = ("fundingchoicesmessages.google.com",)
    markup_markers = ("fundingchoices",)
    global_names = ("googlefc",)
    cookie_names = ("FCCDCF", "FCNEC")
    notes = ("Cookie presence is reported; Funding Choices categories are not decoded.",)


ADAPTERS: Tuple[CmpAdapter, ...] = (
    CookiebotAdapter(),
    OneTrustAdapter(),
    UsercentricsAdapter(),
    DidomiAdapter(),
    QuantcastAdapter(),
    TrustArcAdapter(),
    OsanoAdapter(),
    GoogleFundingChoicesAdapter(),
)


def detect_adapters(signals: DetectionSignals) -> Tuple[CmpDetection, ...]:
    detections = [adapter.detect(signals) for adapter in ADAPTERS]
    return tuple(item for item in detections if item is not None)


def adapter_for(detection: CmpDetection) -> Optional[CmpAdapter]:
    for adapter in ADAPTERS:
        if adapter.adapter_id == detection.adapter_id:
            return adapter
    return None


def read_vendor_consent(
    detections: Sequence[CmpDetection], session, timestamp: float = 0.0
) -> Optional[ConsentState]:
    for detection in detections:
        adapter = adapter_for(detection)
        if adapter is None:
            continue
        state = adapter.read_consent(session, timestamp=timestamp)
        if state is not None:
            return state
    return None


def cookie_presence_state(
    detections: Sequence[CmpDetection], cookie_names: Sequence[str], timestamp: float = 0.0
) -> Optional[ConsentState]:
    if not detections:
        return None
    related = []
    for detection in detections:
        adapter = adapter_for(detection)
        if adapter is None:
            continue
        for cookie in cookie_names:
            if cookie in adapter.cookie_names or any(
                cookie.lower().startswith(prefix.lower()) for prefix in adapter.cookie_prefixes
            ):
                related.append(cookie)
    if not related:
        return None
    categories = {name: None for name in CATEGORIES}
    evidence = tuple(
        CmpEvidence(
            kind="cookie",
            source="cookie",
            summary=f"CMP-related cookie present: {name}",
            value=name,
            timestamp=timestamp,
        )
        for name in sorted(set(related))
    )
    return ConsentState(
        sources=("cookie_presence",),
        categories=categories,
        confidence="unverified",
        timestamp=timestamp,
        evidence=evidence,
    )


def parse_google_consent_mode(
    events: Iterable[TrackingEvent], timestamp: float = 0.0
) -> Optional[ConsentState]:
    mode: Dict[str, str] = {}
    evidence = []
    for event in events:
        if event.event_type != "consent_change":
            continue
        if not isinstance(event.payload, dict):
            continue
        values = {
            str(key): str(value).lower()
            for key, value in event.payload.items()
            if key in _GCM_KEYS and isinstance(value, (str, bool, int, float))
        }
        if not values:
            continue
        mode.update(values)
        evidence.append(
            CmpEvidence(
                kind="consent_mode",
                source="datalayer",
                summary=f"gtag consent {event.event_name or 'signal'} observed",
                value=", ".join(f"{key}={value}" for key, value in sorted(values.items())),
                page_url=event.page_url,
                timestamp=event.timestamp,
            )
        )
    if not mode:
        return None
    return ConsentState(
        sources=("google_consent_mode",),
        categories=google_categories_from_mode(mode),
        google_mode=dict(mode),
        confidence="confirmed",
        timestamp=timestamp or (evidence[-1].timestamp if evidence else 0.0),
        evidence=tuple(evidence),
    )


def google_categories_from_mode(mode: Dict[str, str]) -> Dict[str, Optional[bool]]:
    categories = {name: None for name in CATEGORIES}
    categories["necessary"] = True
    categories["analytics"] = _tri_state([mode.get("analytics_storage")])
    categories["advertising"] = _tri_state(
        [mode.get("ad_storage"), mode.get("ad_user_data"), mode.get("ad_personalization")]
    )
    categories["preferences"] = _tri_state([mode.get("personalization_storage")])
    return categories


def merge_consent_states(
    states: Sequence[ConsentState], timestamp: float = 0.0
) -> ConsentState:
    usable = [state for state in states if state is not None]
    if not usable:
        return ConsentState(timestamp=timestamp)
    sources: List[str] = []
    categories = {name: None for name in CATEGORIES}
    google_mode: Dict[str, str] = {}
    evidence: List[CmpEvidence] = []
    confidence = "unverified"
    for state in usable:
        sources.extend(source for source in state.sources if source not in sources)
        for name, value in state.categories.items():
            if categories.get(name) is None and value is not None:
                categories[name] = value
        google_mode.update(state.google_mode)
        evidence.extend(state.evidence)
        if _confidence_rank(state.confidence) > _confidence_rank(confidence):
            confidence = state.confidence
    return ConsentState(
        sources=tuple(sources),
        categories=categories,
        google_mode=google_mode,
        confidence=confidence,
        timestamp=timestamp or max((state.timestamp for state in usable), default=0.0),
        evidence=tuple(evidence),
    )


def _as_bool(value) -> Optional[bool]:
    return value if isinstance(value, bool) else None


def _tri_state(values: Sequence[Optional[str]]) -> Optional[bool]:
    known = [str(value).lower() for value in values if value is not None]
    if not known:
        return None
    if all(value == "granted" for value in known):
        return True
    if all(value == "denied" for value in known):
        return False
    return None


def _confidence_rank(value: str) -> int:
    order = {name: index for index, name in enumerate(("unverified", "suspected", "high-confidence", "confirmed"))}
    return order.get(value, 0)
