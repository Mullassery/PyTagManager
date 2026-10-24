"""Script inventory (docs/VISION.md §16, Phase 1.95 item 2): per-script
URL, domain, first/third-party, initiator (which script/parser triggered
this request), load mechanism (async/defer/sync), transfer size, network
load timing, and inferred business purpose -- from a real page load's CDP
`Network.*` events plus a DOM query for `<script>` tag attributes.

**Uses CDP here, unlike `perf/measure.py`.** The standard
`PerformanceResourceTiming`/Performance Timeline API (what `measure.py`
uses) has no notion of "which script triggered this request" -- that
initiator-chain information only exists in Chrome DevTools Protocol's
`Network.requestWillBeSent` event (`initiator.type`/`initiator.stack`).
Without it, neither the initiator column here nor
`perf/dependency_graph.py` (item 3, which consumes it) would be possible.

**What's genuinely not measured here, disclosed rather than faked**:
per-script CPU execution time and per-script long-task attribution. The
standard Long Tasks API's `attribution` field (captured by
`perf_agent.js`) does not reliably identify which same-frame script
caused a long task -- it's primarily useful for cross-origin iframe
attribution, not this. Accurately measuring per-script execution time
needs CDP's JS Profiler domain (sampling + call-tree self-time
attribution per URL), a substantial separate undertaking not built in
this pass. `load_duration_ms` here is network fetch time (CDP
`requestWillBeSent` to `loadingFinished`), reported honestly under that
name -- it is not JS execution/parse time.

Business-purpose classification reuses `tagexec.static_scan.
classify_vendor_url()` (Phase 1.85's curated vendor signature list) rather
than a second, duplicate classifier.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from urllib.parse import urlparse

from pytagmanager.tagexec.static_scan import classify_vendor_url

_SCRIPT_TAG_QUERY_JS = """() => Array.from(document.querySelectorAll('script[src]')).map(function (s) {
    return { src: s.src, async: s.async, defer: s.defer };
})"""


def _hostname(url: str) -> str:
    return (urlparse(url).hostname or "").lower()


def _registrable_domain(hostname: str) -> str:
    """Naive eTLD+1 approximation -- see tagexec/server_side.py's same
    helper for why this simplification is acceptable here (plain
    `.com`/`.net`/etc. vendor domains, not multi-part public suffixes)."""
    labels = hostname.split(".")
    return ".".join(labels[-2:]) if len(labels) >= 2 else hostname


def _is_first_party(url: str, page_url: str) -> bool:
    request_host = _hostname(url)
    page_host = _hostname(page_url)
    if not request_host or not page_host:
        return False
    return _registrable_domain(request_host) == _registrable_domain(page_host)


@dataclass(frozen=True)
class ScriptEntry:
    url: str
    domain: str
    is_first_party: bool
    resource_type: str  # CDP resourceType, e.g. "Script", "XHR", "Fetch", "Stylesheet", "Image"
    initiator_type: str  # CDP initiator.type: "parser" | "script" | "other" | "preload" | ...
    initiator_url: str | None  # the script/document that triggered this request, when known
    load_mechanism: (
        str | None
    )  # "async" | "defer" | "sync" for a <script src> element; None otherwise
    transfer_bytes: float | None
    load_duration_ms: (
        float | None
    )  # network fetch time (requestWillBeSent -> loadingFinished), not execution time
    vendor: str | None
    category: str | None


@dataclass(frozen=True)
class ScriptInventory:
    page_url: str
    scripts: tuple[ScriptEntry, ...] = field(default_factory=tuple)

    def by_category(self, category: str) -> tuple[ScriptEntry, ...]:
        return tuple(s for s in self.scripts if s.category == category)

    @property
    def third_party_scripts(self) -> tuple[ScriptEntry, ...]:
        return tuple(
            s for s in self.scripts if not s.is_first_party and s.resource_type == "Script"
        )

    @property
    def total_transfer_bytes(self) -> float:
        return sum(s.transfer_bytes or 0.0 for s in self.scripts)


def _initiator_url_from(initiator: dict) -> str | None:
    if initiator.get("type") == "script":
        stack = initiator.get("stack") or {}
        frames = stack.get("callFrames") or []
        if frames and frames[0].get("url"):
            return frames[0]["url"]
    return initiator.get("url")


def build_script_inventory(
    url: str,
    *,
    headless: bool = True,
    browser_name: str = "chromium",
    wait_ms: int = 500,
) -> ScriptInventory:
    """Loads `url` once (an inventory is a structural listing of what
    loaded, not a statistical metric -- unlike `measure.py`'s aggregated
    runs, one real load is the right unit here) and returns every network
    request CDP observed, classified and cross-referenced with DOM
    `<script>` attributes."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise RuntimeError(
            "Script inventory requires Playwright. Install with "
            "`pip install pytagmanager[diagnostics]` and run `playwright install chromium` once."
        ) from exc

    requests: dict[str, dict] = {}
    finished: dict[str, dict] = {}

    def on_request_will_be_sent(params: dict) -> None:
        requests[params["requestId"]] = {
            "url": params["request"]["url"],
            "resourceType": params.get("type", "Other"),
            "initiator": params.get("initiator") or {},
            "timestamp": params.get("timestamp"),
        }

    def on_loading_finished(params: dict) -> None:
        finished[params["requestId"]] = {
            "encodedDataLength": params.get("encodedDataLength"),
            "timestamp": params.get("timestamp"),
        }

    with sync_playwright() as playwright:
        browser_type = getattr(playwright, browser_name)
        browser = browser_type.launch(headless=headless)
        try:
            context = browser.new_context()
            try:
                page = context.new_page()
                cdp = context.new_cdp_session(page)
                cdp.send("Network.enable")
                cdp.on("Network.requestWillBeSent", on_request_will_be_sent)
                cdp.on("Network.loadingFinished", on_loading_finished)
                page.goto(url, wait_until="networkidle")
                page.wait_for_timeout(wait_ms)
                script_attrs = page.evaluate(_SCRIPT_TAG_QUERY_JS)
            finally:
                context.close()
        finally:
            browser.close()

    script_attrs_by_url = {s["src"]: s for s in script_attrs}

    entries: list[ScriptEntry] = []
    for request_id, req in requests.items():
        finish = finished.get(request_id, {})
        initiator = req["initiator"]
        initiator_type = initiator.get("type", "other")
        initiator_url = _initiator_url_from(initiator)

        req_url = req["url"]
        dom_attrs = script_attrs_by_url.get(req_url)
        load_mechanism = None
        if dom_attrs is not None:
            load_mechanism = (
                "async" if dom_attrs["async"] else ("defer" if dom_attrs["defer"] else "sync")
            )

        vendor_category = classify_vendor_url(req_url)
        transfer_bytes = finish.get("encodedDataLength")
        load_duration_ms = None
        if finish.get("timestamp") is not None and req.get("timestamp") is not None:
            load_duration_ms = max(0.0, (finish["timestamp"] - req["timestamp"]) * 1000.0)

        entries.append(
            ScriptEntry(
                url=req_url,
                domain=_hostname(req_url),
                is_first_party=_is_first_party(req_url, url),
                resource_type=req["resourceType"],
                initiator_type=initiator_type,
                initiator_url=initiator_url,
                load_mechanism=load_mechanism,
                transfer_bytes=transfer_bytes,
                load_duration_ms=load_duration_ms,
                vendor=vendor_category[0] if vendor_category else None,
                category=vendor_category[1] if vendor_category else None,
            )
        )

    return ScriptInventory(page_url=url, scripts=tuple(sorted(entries, key=lambda e: e.url)))
