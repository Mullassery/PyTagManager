from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Sequence, Tuple

from pytagmanager import _core


def crawl_site(
    url: str,
    max_pages: int = 50,
    concurrency: int = 10,
    respect_robots: bool = True,
    rate_limit: float | None = None,
    headers: List[tuple[str, str]] | None = None,
) -> List["_core.Page"]:
    """Crawl a site starting at `url`, returning one Page (URL, status, and
    semantic DOM graph) per visited page. Thin wrapper over the Rust
    extension -- all crawl logic (frontier, robots.txt, sitemap, fetching,
    DOM parsing) lives in Rust.

    `rate_limit` (requests/second) is unset by default, matching prior
    behavior; pass it when crawling a production site you don't control, to
    avoid tripping a WAF or getting rate-limited/blocked mid-crawl.
    `headers` (e.g. `[("Cookie", "session=...")]`) lets the crawler reach
    pages that require auth (staging basic-auth, a logged-in session).
    """
    return _core.crawl(
        url,
        max_pages=max_pages,
        concurrency=concurrency,
        respect_robots=respect_robots,
        rate_limit_per_sec=rate_limit,
        headers=headers or [],
    )


@dataclass(frozen=True)
class RenderedPage:
    """A `Page`-shaped result (`url`/`status`/`graph` -- duck-types with
    `_core.Page` for `recommend_for_graph`/`version_control.snapshot.
    build_snapshot`, which is all either one needs) built from a real
    browser render instead of the crawler's raw HTTP fetch, plus whatever
    optional render-mode observations (item 3/4/5) were requested."""

    url: str
    status: int
    graph: "_core.SemanticGraph"
    console_logs: tuple = ()
    network_requests: tuple = ()
    screenshots: Optional[object] = None
    sniff: Optional[object] = None
    interactions: Tuple[object, ...] = ()


def crawl_site_rendered(
    start_url: str,
    max_pages: int = 50,
    concurrency: int = 10,
    respect_robots: bool = True,
    rate_limit: float | None = None,
    headers: List[tuple[str, str]] | None = None,
    *,
    headless: bool = True,
    browser_name: str = "chromium",
    screenshot_dir: Optional[str] = None,
    sniff_analytics: bool = False,
    simulate_interactions: bool = False,
    interaction_top_n: int = 5,
) -> List[RenderedPage]:
    """Render-mode crawl (docs/ROADMAP.md Phase 1): uses the real Rust
    crawler purely for URL discovery (fast, robots/sitemap-aware -- exactly
    `crawl_site()` above), then re-fetches each discovered URL through a
    real browser (`runtime.renderer.render_page`) and rebuilds its semantic
    graph from the *rendered* HTML via `_core.parse_html()`, so
    client-rendered content that never appears in the raw HTTP response is
    visible to recommendations/export/diagnostics the same way it's visible
    to a real visitor.

    **Disclosed trade-off**: every discovered page is fetched twice (once
    by the Rust crawler for discovery, once by the browser for rendering).
    That's real, deliberate scope for this pass -- the alternative (a
    Rust-side "discover URLs without fetching bodies" mode) needs Rust
    changes explicitly deferred per `docs/ROADMAP.md`, which calls for
    reusing the Rust crawler as-is.

    `screenshot_dir`/`sniff_analytics`/`simulate_interactions` are each
    independently optional -- set none of them and this is just a rendered
    re-crawl; each one adds one more real browser pass per page when
    enabled, so cost scales with what's actually requested.
    """
    from pytagmanager.recommend.heuristics import recommend_for_graph
    from pytagmanager.runtime.interactions import simulate_interactions as _simulate_interactions
    from pytagmanager.runtime.renderer import render_page
    from pytagmanager.runtime.screenshots import capture_page_screenshots
    from pytagmanager.runtime.sniffer import sniff_page

    discovered = crawl_site(
        start_url,
        max_pages=max_pages,
        concurrency=concurrency,
        respect_robots=respect_robots,
        rate_limit=rate_limit,
        headers=headers,
    )

    rendered_pages: List[RenderedPage] = []
    for page in discovered:
        result = render_page(page.url, headless=headless, browser_name=browser_name)
        graph = _core.parse_html(result.html, result.url)

        screenshots = None
        if screenshot_dir is not None:
            screenshots = capture_page_screenshots(
                result.url, Path(screenshot_dir), headless=headless, browser_name=browser_name
            )

        sniff = None
        if sniff_analytics:
            sniff = sniff_page(result.url, headless=headless, browser_name=browser_name)

        interactions: Tuple[object, ...] = ()
        if simulate_interactions:
            candidates = _top_selectors(recommend_for_graph(graph), interaction_top_n)
            if candidates:
                interactions = _simulate_interactions(
                    result.url,
                    candidates,
                    top_n=interaction_top_n,
                    headless=headless,
                    browser_name=browser_name,
                )

        rendered_pages.append(
            RenderedPage(
                url=result.url,
                status=result.status,
                graph=graph,
                console_logs=result.console_logs,
                network_requests=result.network_requests,
                screenshots=screenshots,
                sniff=sniff,
                interactions=interactions,
            )
        )

    return rendered_pages


def _top_selectors(recommendations: Sequence, top_n: int) -> List[str]:
    """The `top_n` highest-confidence recommendation selectors,
    deduplicated, order-preserving -- the "top-N heuristic candidates"
    `simulate_interactions` is bounded to per `docs/ROADMAP.md`."""
    ranked = sorted(recommendations, key=lambda rec: rec.confidence, reverse=True)
    selectors: List[str] = []
    for rec in ranked:
        if rec.selector not in selectors:
            selectors.append(rec.selector)
        if len(selectors) >= top_n:
            break
    return selectors
