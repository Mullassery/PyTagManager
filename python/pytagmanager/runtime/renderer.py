"""Playwright-driven rendering (docs/ROADMAP.md Phase 1, item 1): fetch a
page the way a real browser sees it -- after JS has run -- instead of the
Rust crawler's raw HTTP response body. `_core.parse_html()` already accepts
arbitrary HTML from any source (its docstring says so explicitly), so the
rendered HTML flows through the exact same Rust DOM-graph engine the static
crawl uses; no Rust changes needed.

This is deliberately a thin, single-page primitive (mirrors
`perf.measure.measure_page_performance`'s one-purpose-per-module shape) --
`pytagmanager.discovery.crawl.crawl_site_rendered` is what composes this
with URL discovery, screenshots, sniffing, and interaction simulation into
a full render-mode crawl.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ConsoleLogEntry:
    level: str
    text: str


@dataclass(frozen=True)
class NetworkRequestEntry:
    url: str
    method: str
    resource_type: str
    status: int | None


@dataclass(frozen=True)
class RenderResult:
    url: str  # final URL after redirects, from the navigation response
    status: int
    html: str
    console_logs: tuple[ConsoleLogEntry, ...]
    network_requests: tuple[NetworkRequestEntry, ...]


def render_page(
    url: str,
    *,
    headless: bool = True,
    browser_name: str = "chromium",
    wait_until: str = "networkidle",
    wait_ms: int = 500,
    timeout_ms: int = 30000,
) -> RenderResult:
    """Loads `url` in a real browser, lets it settle (`wait_until`, then a
    fixed `wait_ms` for any post-load JS), and returns the live DOM's HTML
    (`page.content()` -- includes anything JS injected, unlike the raw HTTP
    body) plus every console message and network request observed along
    the way.

    `status` is the main-document navigation response's HTTP status;
    `network_requests[*].status` is `None` for a request whose response
    hadn't arrived by the time this returned (e.g. an abandoned
    prefetch) -- reported as absent, not guessed.
    """
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise RuntimeError(
            "Rendered-page fetching requires Playwright. Install with "
            "`pip install pytagmanager[diagnostics]` and run `playwright install chromium` once."
        ) from exc

    console_logs: list[ConsoleLogEntry] = []
    requests_by_url: dict[str, NetworkRequestEntry] = {}

    with sync_playwright() as playwright:
        browser_type = getattr(playwright, browser_name)
        browser = browser_type.launch(headless=headless)
        try:
            context = browser.new_context()
            try:
                page = context.new_page()
                page.on(
                    "console",
                    lambda msg: console_logs.append(ConsoleLogEntry(level=msg.type, text=msg.text)),
                )

                def _on_request(request):
                    requests_by_url[request.url] = NetworkRequestEntry(
                        url=request.url,
                        method=request.method,
                        resource_type=request.resource_type,
                        status=None,
                    )

                def _on_response(response):
                    entry = requests_by_url.get(response.url)
                    if entry is not None:
                        requests_by_url[response.url] = NetworkRequestEntry(
                            url=entry.url,
                            method=entry.method,
                            resource_type=entry.resource_type,
                            status=response.status,
                        )

                page.on("request", _on_request)
                page.on("response", _on_response)

                response = page.goto(url, wait_until=wait_until, timeout=timeout_ms)
                page.wait_for_timeout(wait_ms)
                html = page.content()
                final_url = page.url
                status = response.status if response is not None else 0
            finally:
                context.close()
        finally:
            browser.close()

    return RenderResult(
        url=final_url,
        status=status,
        html=html,
        console_logs=tuple(console_logs),
        network_requests=tuple(requests_by_url.values()),
    )
