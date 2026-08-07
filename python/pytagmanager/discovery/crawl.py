from __future__ import annotations

from typing import List

from pytagmanager import _core


def crawl_site(
    url: str,
    max_pages: int = 50,
    concurrency: int = 10,
    respect_robots: bool = True,
) -> List["_core.Page"]:
    """Crawl a site starting at `url`, returning one Page (URL, status, and
    semantic DOM graph) per visited page. Thin wrapper over the Rust
    extension -- all crawl logic (frontier, robots.txt, sitemap, fetching,
    DOM parsing) lives in Rust.
    """
    return _core.crawl(
        url,
        max_pages=max_pages,
        concurrency=concurrency,
        respect_robots=respect_robots,
    )
