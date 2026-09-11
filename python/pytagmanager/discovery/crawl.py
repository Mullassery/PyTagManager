from __future__ import annotations

from typing import List

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
