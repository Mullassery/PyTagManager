"""Playwright-backed observation session: launches a real browser, injects
`agent.js` before any page script runs, optionally drives a `Scenario`'s
steps, and collects every raw signal into a flat `List[TrackingEvent]` for
`pytagmanager.correlation.journey` to correlate.

Playwright is optional (`pip install pytagmanager[diagnostics]`) -- imported
lazily inside `__enter__` so `import pytagmanager` stays dependency-free for
callers who only need crawl/recommend/export (spec section 22).
"""

from __future__ import annotations

import re
import time
from pathlib import Path
from typing import Dict, List, Optional, Sequence
from urllib.parse import parse_qsl, urlparse

from pytagmanager.observability.events import TrackingEvent, redact_payload
from pytagmanager.observability.scenario import ActionStep, Scenario
from pytagmanager.observability.state import RuntimeStateSnapshot, StateDiff, diff_state_snapshots

_AGENT_JS_PATH = Path(__file__).parent / "agent.js"

# Analytics/GTM endpoint patterns to watch on the network layer -- a small
# list rather than one hardcoded URL, since GA4 alone has several valid
# collect endpoints (classic gtag.js hits, Measurement Protocol, regional
# domains) and GTM's own loader/activity pings are separately useful signals.
#
# The last two entries are host-agnostic path-shape patterns, not anchored
# to a specific domain: a first-party server-side GTM proxy (Phase 1.85
# item 3, tagexec/server_side.py) commonly reuses GA4's own `/g/collect` /
# `/mp/collect` path shape on the site's own domain -- if this observer only
# ever captured known third-party hosts, a first-party-proxied collection
# request would be silently invisible to the network_request event stream,
# and server_side.py's first-party-endpoint detector would never have
# anything to analyze in a real run.
_ANALYTICS_URL_PATTERNS = [
    re.compile(r"google-analytics\.com/g/collect"),
    re.compile(r"google-analytics\.com/mp/collect"),
    re.compile(r"analytics\.google\.com/g/collect"),
    re.compile(r"googletagmanager\.com/gtm\.js"),
    re.compile(r"googletagmanager\.com/gtag/js"),
    re.compile(r"googletagmanager\.com/a\?"),
    re.compile(r"/g/collect(\?|$)"),
    re.compile(r"/mp/collect(\?|$)"),
]

_SOURCE_BY_EVENT_TYPE: Dict[str, str] = {
    "click": "browser",
    "submit": "browser",
    "change": "browser",
    "dom_insert": "mutation_observer",
    "dom_remove": "mutation_observer",
    "datalayer_push": "datalayer",
    "gtm_event": "gtm",
    "consent_change": "consent",
    "route_change": "browser",
    "js_error": "javascript",
    "api_call": "application_api",
    "visibility": "visibility",
    "scroll_depth": "browser",
}

_DEFAULT_SCROLL_DEPTH_MILESTONES = [25, 50, 75, 90, 100]


def _classify_network_url(url: str) -> Optional[str]:
    for pattern in _ANALYTICS_URL_PATTERNS:
        if pattern.search(url):
            return pattern.pattern
    return None


def _parse_query_params(url: str) -> dict:
    return dict(parse_qsl(urlparse(url).query))


class ObservationSession:
    """One Playwright session observing one page."""

    def __init__(
        self,
        headless: bool = True,
        browser_name: str = "chromium",
        mutation_selectors: Optional[Sequence[str]] = None,
        visibility_selectors: Optional[Sequence[str]] = None,
        capture_storage_values: bool = False,
        track_scroll_depth: bool = False,
        scroll_depth_milestones: Optional[Sequence[int]] = None,
    ):
        self.headless = headless
        self.browser_name = browser_name
        self.mutation_selectors = list(mutation_selectors or [])
        self.visibility_selectors = list(visibility_selectors or [])
        self.track_scroll_depth = track_scroll_depth
        self.scroll_depth_milestones = list(scroll_depth_milestones or _DEFAULT_SCROLL_DEPTH_MILESTONES)
        # Runtime State Capture (Phase 1.6): off by default for raw cookie/
        # storage *values* -- see the privacy note in observability/state.py.
        # Keys/type/length are always captured regardless of this flag.
        self.capture_storage_values = capture_storage_values
        self._events: List[TrackingEvent] = []
        self._state_snapshots: List[RuntimeStateSnapshot] = []
        self._state_diffs: List[StateDiff] = []
        self._playwright = None
        self._browser = None
        self._page = None

    def __enter__(self) -> "ObservationSession":
        try:
            from playwright.sync_api import sync_playwright
        except ImportError as exc:
            raise RuntimeError(
                "Tracking Observability requires Playwright. Install with "
                "`pip install pytagmanager[diagnostics]` and run `playwright install chromium` once."
            ) from exc

        self._playwright = sync_playwright().start()
        browser_type = getattr(self._playwright, self.browser_name)
        self._browser = browser_type.launch(headless=self.headless)
        self._page = self._browser.new_page()
        self._page.expose_function("__ptm_emit", self._on_agent_event)
        self._page.add_init_script(_AGENT_JS_PATH.read_text())
        self._page.on("request", self._on_network_request)
        return self

    def __exit__(self, *exc_info) -> None:
        if self._browser is not None:
            self._browser.close()
        if self._playwright is not None:
            self._playwright.stop()

    def _on_agent_event(self, raw: dict) -> None:
        event_type = raw.get("type", "")
        self._events.append(
            TrackingEvent.create(
                source=_SOURCE_BY_EVENT_TYPE.get(event_type, "browser"),
                event_type=event_type,
                event_name=raw.get("name", ""),
                page_url=raw.get("page_url", ""),
                selector=raw.get("selector"),
                payload=raw.get("payload", {}),
                timestamp=raw.get("ts"),
            )
        )

    def _on_network_request(self, request) -> None:
        if _classify_network_url(request.url) is None:
            return
        params = redact_payload(_parse_query_params(request.url))
        self._events.append(
            TrackingEvent.create(
                source="network",
                event_type="network_request",
                event_name=params.get("en", ""),
                page_url=self._page.url if self._page else "",
                payload={"url": request.url, "method": request.method, "params": params},
            )
        )

    def add_route(self, url_pattern: str, handler) -> None:
        """Expose Playwright's request interception for callers that need
        to stand in for a real analytics endpoint -- primarily test fixtures
        faking a GA4/GTM network response without real network access.
        Production `diagnose` runs never call this; real analytics traffic
        is only ever observed, never intercepted.
        """
        self._page.route(url_pattern, handler)

    def load(self, url: str) -> None:
        self._page.goto(url, wait_until="networkidle")
        self._page.evaluate(
            "(selectors) => window.__ptm.startMutationObserver(selectors, false)",
            self.mutation_selectors,
        )
        if self.visibility_selectors:
            self._page.evaluate(
                "(selectors) => window.__ptm.startVisibilityObserver(selectors, 0.5)",
                self.visibility_selectors,
            )
        if self.track_scroll_depth:
            self._page.evaluate(
                "(milestones) => window.__ptm.startScrollDepthObserver(milestones)",
                self.scroll_depth_milestones,
            )
        self.capture_state("page_load")

    def capture_state(self, label: str) -> RuntimeStateSnapshot:
        """Snapshot cookies/localStorage/sessionStorage/dataLayer right now,
        record it, and return it. `label` identifies this point in the page
        visit (e.g. "page_load", "before:step_0_click",
        "after:step_0_click") -- see `state_diffs` for the before/after
        comparison this feeds.
        """
        js_state = self._page.evaluate(
            "(includeValues) => window.__ptm.captureState(includeValues)",
            self.capture_storage_values,
        )
        # Cookies go through Playwright's CDP-backed API, not agent.js's
        # document.cookie -- the former sees HttpOnly cookies, the latter
        # can't (see observability/state.py's module docstring).
        cookies = self._page.context.cookies()
        snapshot = RuntimeStateSnapshot.from_raw(
            js_state,
            cookies=cookies,
            page_url=self._page.url,
            timestamp=time.time(),
            label=label,
        )
        self._state_snapshots.append(snapshot)
        return snapshot

    def run_scenario(self, scenario: Scenario, step_timeout_ms: int = 5000) -> None:
        for index, step in enumerate(scenario.steps):
            self._run_step(index, step, step_timeout_ms)

    def _run_step(self, index: int, step: ActionStep, timeout_ms: int) -> None:
        step_id = f"step_{index}_{step.action}"
        before = self.capture_state(f"before:{step_id}")
        locator = self._page.locator(step.selector).first
        try:
            if step.action == "click":
                locator.click(timeout=timeout_ms)
            elif step.action == "submit":
                locator.evaluate("(el) => el.requestSubmit ? el.requestSubmit() : el.submit()")
            elif step.action == "change":
                locator.fill(step.value, timeout=timeout_ms)
        except Exception as exc:
            self._events.append(
                TrackingEvent.create(
                    source="browser",
                    event_type="js_error",
                    event_name="scenario_step_failed",
                    selector=step.selector,
                    payload={"action": step.action, "error": str(exc)[:300]},
                )
            )
        after = self.capture_state(f"after:{step_id}")
        self._state_diffs.append(diff_state_snapshots(before, after, selector=step.selector))

    def scroll_into_view(self, selector: str) -> None:
        self._page.locator(selector).first.scroll_into_view_if_needed()

    def capture_html(self) -> str:
        """The live, rendered DOM's HTML right now (Playwright's
        `page.content()`) -- includes anything JS has injected since load,
        unlike the crawler's pre-render source. See
        `pytagmanager.tagexec.static_scan`'s module docstring for why this
        matters for GTM/vendor-snippet detection."""
        return self._page.content()

    def wait(self, seconds: float) -> None:
        self._page.wait_for_timeout(int(seconds * 1000))

    @property
    def events(self) -> List[TrackingEvent]:
        return list(self._events)

    @property
    def state_snapshots(self) -> List[RuntimeStateSnapshot]:
        return list(self._state_snapshots)

    @property
    def state_diffs(self) -> List[StateDiff]:
        """One `StateDiff` per scenario step, in step order -- what changed
        in cookies/localStorage/sessionStorage/dataLayer as a direct result
        of that interaction."""
        return list(self._state_diffs)
