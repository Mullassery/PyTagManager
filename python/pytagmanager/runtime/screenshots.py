"""Per-page screenshot capture (docs/ROADMAP.md Phase 1, item 3):
full-page and above-the-fold captures at both a desktop and a mobile
viewport, stored as real PNG files on disk so they're retrievable per
crawled page -- the phase's second exit criterion.

`DESKTOP_VIEWPORT`/`MOBILE_VIEWPORT` are fixed, disclosed sizes (a common
laptop size and a common phone size), not a device emulation profile
(no user-agent spoofing, no touch/DPR emulation) -- viewport dimensions
are what "above the fold" is measured against, and that's the only thing
this needs.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

DESKTOP_VIEWPORT = {"width": 1280, "height": 800}
MOBILE_VIEWPORT = {"width": 390, "height": 844}

_SLUG_UNSAFE = re.compile(r"[^a-zA-Z0-9._-]+")


def slug_for_url(url: str) -> str:
    """A filesystem-safe identifier for `url`, stable across repeated
    calls for the same URL -- used to name this page's screenshot files
    without needing a separately-tracked page id."""
    slug = _SLUG_UNSAFE.sub("_", url).strip("_")
    return slug[:200] or "page"


@dataclass(frozen=True)
class ScreenshotSet:
    page_id: str
    url: str
    desktop_above_fold: Path
    desktop_full_page: Path
    mobile_above_fold: Path
    mobile_full_page: Path


def capture_page_screenshots(
    url: str,
    output_dir: Path,
    *,
    headless: bool = True,
    browser_name: str = "chromium",
    wait_until: str = "networkidle",
) -> ScreenshotSet:
    """Loads `url` twice -- once per viewport -- and writes 4 PNGs
    (desktop/mobile x above-fold/full-page) under `output_dir`, named from
    `slug_for_url(url)`. Two separate page loads (not one page resized) so
    each capture reflects a real, freshly-rendered layout at that viewport,
    matching how `perf.measure` never reuses a warm context across
    measurements that need to be independently trustworthy.
    """
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise RuntimeError(
            "Screenshot capture requires Playwright. Install with "
            "`pip install pytagmanager[diagnostics]` and run `playwright install chromium` once."
        ) from exc

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    page_id = slug_for_url(url)

    paths = {
        "desktop_above_fold": output_dir / f"{page_id}.desktop.above_fold.png",
        "desktop_full_page": output_dir / f"{page_id}.desktop.full_page.png",
        "mobile_above_fold": output_dir / f"{page_id}.mobile.above_fold.png",
        "mobile_full_page": output_dir / f"{page_id}.mobile.full_page.png",
    }

    with sync_playwright() as playwright:
        browser_type = getattr(playwright, browser_name)
        browser = browser_type.launch(headless=headless)
        try:
            for viewport, above_fold_key, full_page_key in (
                (DESKTOP_VIEWPORT, "desktop_above_fold", "desktop_full_page"),
                (MOBILE_VIEWPORT, "mobile_above_fold", "mobile_full_page"),
            ):
                context = browser.new_context(viewport=viewport)
                try:
                    page = context.new_page()
                    page.goto(url, wait_until=wait_until)
                    page.screenshot(path=str(paths[above_fold_key]), full_page=False)
                    page.screenshot(path=str(paths[full_page_key]), full_page=True)
                finally:
                    context.close()
        finally:
            browser.close()

    return ScreenshotSet(page_id=page_id, url=url, **paths)
