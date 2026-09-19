"""Bounded runtime interaction simulation (docs/ROADMAP.md Phase 1, item 4):
click/hover/scroll a small, heuristic-ranked set of candidate elements and
observe what actually happens -- DOM mutations and network requests fired
-- rather than assuming a recommended selector does anything at runtime.

Deliberately bounded to `top_n` candidates (a real cost control, not a
placeholder): every interaction opens a fresh browser context (never reused
across candidates, so one candidate's DOM changes/network traffic can't
leak into the next one's observation), which is real browser-launch cost
per candidate.

**Disclosed, not implemented**: mutation counting here is a raw
`MutationObserver` record count, not `observability/agent.js`'s
selector-scoped, deduplicated `dom_insert`/`dom_remove` event stream --
that agent is built for known-selector visibility tracking during a
scripted `Scenario`, not for "did anything change" on an arbitrary,
not-yet-known candidate element. A raw count is the right tool for this
narrower, exploratory question.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Sequence, Tuple

_MUTATION_COUNTER_JS = """() => {
    window.__ptm_mutation_count = 0;
    new MutationObserver((records) => {
        window.__ptm_mutation_count += records.length;
    }).observe(document.documentElement, { childList: true, subtree: true, attributes: true, characterData: true });
}"""

_VALID_ACTIONS = ("click", "hover", "scroll")


@dataclass(frozen=True)
class InteractionObservation:
    selector: str
    action: str
    mutation_count: int
    network_requests_fired: Tuple[str, ...]
    error: Optional[str]


def simulate_interactions(
    url: str,
    selectors: Sequence[str],
    *,
    top_n: int = 5,
    action: str = "click",
    headless: bool = True,
    browser_name: str = "chromium",
    wait_ms: int = 500,
    timeout_ms: int = 5000,
) -> Tuple[InteractionObservation, ...]:
    """For each of the first `top_n` (deduplicated, order-preserving)
    `selectors`, load `url` fresh, perform `action` on that selector, and
    report the DOM mutations and new network requests observed in the
    `wait_ms` after. A selector that can't be found/interacted with
    (timeout, detached element, etc.) is reported with a non-None `error`
    and zeroed observations rather than aborting the whole batch -- one bad
    candidate shouldn't hide results for the rest.
    """
    if action not in _VALID_ACTIONS:
        raise ValueError(f"action must be one of {_VALID_ACTIONS}, got {action!r}")

    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise RuntimeError(
            "Interaction simulation requires Playwright. Install with "
            "`pip install pytagmanager[diagnostics]` and run `playwright install chromium` once."
        ) from exc

    deduped: List[str] = []
    for selector in selectors:
        if selector not in deduped:
            deduped.append(selector)
    targets = deduped[:top_n]

    observations: List[InteractionObservation] = []

    with sync_playwright() as playwright:
        browser_type = getattr(playwright, browser_name)
        browser = browser_type.launch(headless=headless)
        try:
            for selector in targets:
                context = browser.new_context()
                try:
                    page = context.new_page()
                    requests: List[str] = []
                    page.on("request", lambda request: requests.append(request.url))
                    page.goto(url, wait_until="networkidle")
                    page.evaluate(_MUTATION_COUNTER_JS)
                    baseline_request_count = len(requests)
                    error: Optional[str] = None
                    try:
                        locator = page.locator(selector).first
                        if action == "click":
                            locator.click(timeout=timeout_ms)
                        elif action == "hover":
                            locator.hover(timeout=timeout_ms)
                        elif action == "scroll":
                            locator.scroll_into_view_if_needed(timeout=timeout_ms)
                    except Exception as exc:  # noqa: BLE001 -- reported per-candidate, not raised
                        error = str(exc)[:300]
                    page.wait_for_timeout(wait_ms)
                    mutation_count = page.evaluate("() => window.__ptm_mutation_count || 0")
                    new_requests = tuple(requests[baseline_request_count:])
                    observations.append(
                        InteractionObservation(
                            selector=selector,
                            action=action,
                            mutation_count=mutation_count,
                            network_requests_fired=new_requests,
                            error=error,
                        )
                    )
                finally:
                    context.close()
        finally:
            browser.close()

    return tuple(observations)
