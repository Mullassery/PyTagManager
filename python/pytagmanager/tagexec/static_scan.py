"""Static code intelligence (docs/VISION.md §17, Phase 1.85 item 1):
detect GTM container snippets and hard-coded vendor tracking
implementations from a page's HTML.

**Scans rendered HTML, not the raw server response.** `ObservationSession.
capture_html()` (a thin wrapper over Playwright's `page.content()`) is the
intended source: a GTM container's loader script inserts a real
`<script src="...gtm.js?id=...">` tag into the live DOM, so scanning the
*rendered* page catches both a container present in the original HTML
source and one injected later by JS -- the raw pre-render source can only
ever show the former. The tradeoff: from a single snapshot, this module
cannot tell *which* case it was. `detect_delayed_containers()` below
covers that by comparing two snapshots (e.g. "page_load" vs. after a
consent-accept interaction) instead of guessing from static source
context, which is why this module -- deliberately -- does not attempt to
regex-guess "is this GTM load wrapped in a consent/click/DOM-ready gate"
from source structure alone; that would be a confidence-free guess dressed
up as analysis.

The vendor signature list below is curated, not exhaustive -- it covers
the vendors `docs/VISION.md` §17 names by name (GA4, Google Ads,
Floodlight, Meta Pixel, Adobe Analytics/AEP) plus a handful of common
analytics/experimentation/chat/payment SDKs, matched on well-known
script-src/API-call patterns. A vendor absent from this list is simply not
detected -- never silently reported as "not present."

**Matches structurally, not by raw substring.** `_TagSourceExtractor`
(a stdlib `html.parser.HTMLParser`) extracts real `<script src>`/
`<iframe src>` attribute values and real inline `<script>` bodies; GTM
container detection matches only against the former (a container ID is
only "loaded" if an actual element with that src exists in the DOM right
now), while vendor detection also checks inline script text (a vendor
init call is real static evidence wherever it appears in a page's own
script source, even inside a conditionally-executed handler). Regexing
the raw HTML dump as one blob was tried first and rejected: it
false-positived on a container ID that appeared only as a string literal
inside an unrelated (not-yet-fired) event handler's source code, not an
element actually present in the DOM.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from html.parser import HTMLParser
from typing import List, Optional, Tuple

_GTM_LOADER_PATTERN = re.compile(r"googletagmanager\.com/gtm\.js\?id=(GTM-[A-Z0-9]+)")
_GTM_NOSCRIPT_PATTERN = re.compile(r"googletagmanager\.com/ns\.html\?id=(GTM-[A-Z0-9]+)")


class _TagSourceExtractor(HTMLParser):
    """Extracts only what's actually structurally present -- `src`
    attribute values of real `<script>`/`<iframe>` elements, and the text
    content of inline (no-`src`) `<script>` elements -- instead of
    substring-matching the raw HTML dump. Matching against raw text would
    false-positive on a URL/ID that merely appears as a string literal
    inside some *other* script's source (e.g. a consent-gated loader whose
    handler body contains the container ID it will inject *if* clicked,
    which is not the same as the container actually being loaded now)."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.script_srcs: List[str] = []
        self.iframe_srcs: List[str] = []
        self.inline_script_texts: List[str] = []
        self._in_inline_script = False
        self._current_inline_chunks: List[str] = []

    def handle_starttag(self, tag: str, attrs: List[Tuple[str, Optional[str]]]) -> None:
        attrs_dict = dict(attrs)
        if tag == "script":
            src = attrs_dict.get("src")
            if src:
                self.script_srcs.append(src)
                self._in_inline_script = False
            else:
                self._in_inline_script = True
                self._current_inline_chunks = []
        elif tag == "iframe":
            src = attrs_dict.get("src")
            if src:
                self.iframe_srcs.append(src)

    def handle_endtag(self, tag: str) -> None:
        if tag == "script" and self._in_inline_script:
            self.inline_script_texts.append("".join(self._current_inline_chunks))
            self._in_inline_script = False
            self._current_inline_chunks = []

    def handle_data(self, data: str) -> None:
        if self._in_inline_script:
            self._current_inline_chunks.append(data)


def _extract(html: str) -> _TagSourceExtractor:
    parser = _TagSourceExtractor()
    parser.feed(html)
    return parser

# (vendor, category, regex) -- category taxonomy per docs/VISION.md §17:
# analytics/ads/experimentation/personalization/heatmap/chat/payment/video.
_VENDOR_SIGNATURES: List[Tuple[str, str, "re.Pattern[str]"]] = [
    ("GA4", "analytics", re.compile(r"googletagmanager\.com/gtag/js\?id=(G-[A-Z0-9]+)")),
    ("GA4", "analytics", re.compile(r"gtag\(\s*['\"]config['\"]\s*,\s*['\"](G-[A-Z0-9]+)")),
    ("Google Ads", "ads", re.compile(r"googleadservices\.com/pagead/conversion")),
    ("Google Ads", "ads", re.compile(r"gtag\(\s*['\"]config['\"]\s*,\s*['\"](AW-[0-9]+)")),
    ("Floodlight", "ads", re.compile(r"[a-z0-9.-]*\bfls\.doubleclick\.net")),
    ("Meta Pixel", "ads", re.compile(r"connect\.facebook\.net/[^\"'\s]+/fbevents\.js")),
    ("Meta Pixel", "ads", re.compile(r"fbq\(\s*['\"]init['\"]")),
    ("Adobe Analytics", "analytics", re.compile(r"AppMeasurement\.js")),
    ("Adobe Analytics", "analytics", re.compile(r"\.sc\.omtrdc\.net")),
    ("Adobe Experience Platform", "analytics", re.compile(r"edge\.adobedc\.net")),
    ("Adobe Launch/DTM", "analytics", re.compile(r"assets\.adobedtm\.com")),
    ("Segment", "analytics", re.compile(r"cdn\.segment\.com/analytics\.js")),
    ("Mixpanel", "analytics", re.compile(r"cdn\.mxpnl\.com")),
    ("Amplitude", "analytics", re.compile(r"cdn\.amplitude\.com")),
    ("Hotjar", "heatmap", re.compile(r"static\.hotjar\.com")),
    ("Microsoft Clarity", "heatmap", re.compile(r"www\.clarity\.ms/tag")),
    ("Optimizely", "experimentation", re.compile(r"cdn\.optimizely\.com")),
    ("VWO", "experimentation", re.compile(r"dev\.visualwebsiteoptimizer\.com")),
    ("Intercom", "chat", re.compile(r"widget\.intercom\.io")),
    ("Drift", "chat", re.compile(r"js\.driftt\.com")),
    ("Zendesk Chat", "chat", re.compile(r"static\.zdassets\.com")),
    ("Stripe", "payment", re.compile(r"js\.stripe\.com")),
    ("PayPal", "payment", re.compile(r"www\.paypal\.com/sdk/js")),
    ("YouTube Embed API", "video", re.compile(r"www\.youtube\.com/iframe_api")),
    ("Vimeo Player API", "video", re.compile(r"player\.vimeo\.com/api/player\.js")),
    ("TikTok Pixel", "ads", re.compile(r"analytics\.tiktok\.com/i18n/pixel")),
    ("LinkedIn Insight Tag", "ads", re.compile(r"snap\.licdn\.com/li\.lms-analytics")),
]

_EVIDENCE_SNIPPET_MAX_LEN = 200


@dataclass(frozen=True)
class GtmContainerDetection:
    container_id: str
    load_mechanism: str  # "script_tag" | "noscript_iframe"


@dataclass(frozen=True)
class VendorDetection:
    vendor: str
    category: str
    evidence: str  # matched snippet, length-capped -- not raw page content

    @property
    def identity_key(self) -> Tuple[str, str]:
        """(vendor, evidence) rather than just vendor -- the same vendor
        can legitimately appear more than once with different container/
        pixel IDs (e.g. two GA4 measurement IDs), which is itself a
        duplicate-implementation signal `tagexec/duplicates.py` consumes,
        not noise to collapse away."""
        return (self.vendor, self.evidence)


@dataclass(frozen=True)
class StaticScanResult:
    page_url: str
    gtm_containers: Tuple[GtmContainerDetection, ...]
    vendors: Tuple[VendorDetection, ...]

    @property
    def gtm_container_ids(self) -> Tuple[str, ...]:
        return tuple(sorted({c.container_id for c in self.gtm_containers}))

    @property
    def has_multiple_gtm_containers(self) -> bool:
        return len(self.gtm_container_ids) > 1


def _snippet(match: "re.Match[str]") -> str:
    return match.group(0)[:_EVIDENCE_SNIPPET_MAX_LEN]


def _detect_gtm_containers(extractor: _TagSourceExtractor) -> Tuple[GtmContainerDetection, ...]:
    # Only real script/iframe `src` attribute values -- never inline script
    # text -- so a container ID that merely appears as a string literal
    # inside some *other* (e.g. not-yet-fired event handler) script isn't
    # mistaken for a container that's actually loaded right now. Note:
    # when `html` came from Playwright's rendered `page.content()`, a
    # `<noscript>` element's children are never part of the live DOM in a
    # JS-enabled browser (browsers don't parse noscript content when
    # scripting is enabled) -- the noscript_iframe path only fires when
    # `scan_html()` is given pre-render/raw source HTML instead.
    seen: dict = {}
    for src in extractor.script_srcs:
        match = _GTM_LOADER_PATTERN.search(src)
        if match:
            seen.setdefault(match.group(1), "script_tag")
    for src in extractor.iframe_srcs:
        match = _GTM_NOSCRIPT_PATTERN.search(src)
        if match:
            seen.setdefault(match.group(1), "noscript_iframe")
    return tuple(
        GtmContainerDetection(container_id=container_id, load_mechanism=mechanism)
        for container_id, mechanism in sorted(seen.items())
    )


def _detect_vendors(extractor: _TagSourceExtractor) -> Tuple[VendorDetection, ...]:
    # Checked against both real src attribute values and inline script
    # bodies: unlike GTM container detection (which is about "is this
    # actively loaded right now"), a vendor SDK init call appearing
    # anywhere in a page's own script source -- even inside a
    # conditionally-executed handler -- is still real "hard-coded vendor
    # implementation" evidence per docs/VISION.md §17, not a false
    # positive to filter out.
    haystacks = list(extractor.script_srcs) + list(extractor.iframe_srcs) + list(extractor.inline_script_texts)
    detections = []
    for vendor, category, pattern in _VENDOR_SIGNATURES:
        for haystack in haystacks:
            for match in pattern.finditer(haystack):
                detections.append(VendorDetection(vendor=vendor, category=category, evidence=_snippet(match)))
    # Dedupe identical (vendor, evidence) pairs -- the same script tag can
    # be matched by more than one signature pass in rare cases, and a
    # vendor script referenced twice in markup is not two findings.
    unique = {d.identity_key: d for d in detections}
    return tuple(sorted(unique.values(), key=lambda d: (d.vendor, d.evidence)))


def scan_html(html: str, page_url: str) -> StaticScanResult:
    """Single-snapshot scan: every GTM container and vendor SDK reference
    findable in `html` right now. Call again on a later snapshot (e.g.
    after a consent interaction) and compare with
    `detect_delayed_containers()`/`detect_delayed_vendors()` to find
    implementations that weren't present yet at this snapshot."""
    extractor = _extract(html)
    return StaticScanResult(
        page_url=page_url,
        gtm_containers=_detect_gtm_containers(extractor),
        vendors=_detect_vendors(extractor),
    )


def classify_vendor_url(url: str) -> Optional[Tuple[str, str]]:
    """(vendor, category) for a single URL (e.g. a script `src`), reusing
    the same curated `_VENDOR_SIGNATURES` list `scan_html()` matches
    against -- a public entry point so other modules (`perf/scripts.py`'s
    script inventory, Phase 1.95 item 2) can classify one URL at a time
    without reaching into this module's private internals. Returns None
    if no signature matches, same "absent, not fabricated" discipline as
    the rest of this module."""
    for vendor, category, pattern in _VENDOR_SIGNATURES:
        if pattern.search(url):
            return (vendor, category)
    return None


def detect_delayed_containers(baseline: StaticScanResult, later: StaticScanResult) -> Tuple[str, ...]:
    """GTM container IDs present in `later` but absent from `baseline` --
    evidence the container loaded sometime between the two snapshots
    (consent-gated, interaction-gated, or just slow), not present at the
    baseline's point in time. Order-independent identity (container ID),
    not `GtmContainerDetection` equality, since the same container can
    legitimately change `load_mechanism` between snapshots."""
    baseline_ids = set(baseline.gtm_container_ids)
    return tuple(cid for cid in later.gtm_container_ids if cid not in baseline_ids)


def detect_delayed_vendors(baseline: StaticScanResult, later: StaticScanResult) -> Tuple[VendorDetection, ...]:
    baseline_keys = {v.identity_key for v in baseline.vendors}
    return tuple(v for v in later.vendors if v.identity_key not in baseline_keys)
