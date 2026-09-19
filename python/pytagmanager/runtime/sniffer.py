"""Existing-instrumentation sniffing (docs/ROADMAP.md Phase 1, item 5):
what analytics is already firing on a page, observed at runtime rather than
guessed from source. This is what makes the differently-numbered Phase 5
audit engine possible later -- "you can't find gaps without knowing what's
already firing."

Reuses `tagexec.static_scan.classify_vendor_url()` (the same curated
vendor-signature list `scan-tags` and `perf/scripts.py` already match
against) instead of a second, divergent set of analytics-endpoint patterns
-- one vendor list for the whole codebase.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Tuple

from pytagmanager.tagexec.static_scan import classify_vendor_url


@dataclass(frozen=True)
class VendorHit:
    vendor: str
    category: str
    url: str


@dataclass(frozen=True)
class SniffResult:
    url: str
    vendor_hits: Tuple[VendorHit, ...]
    data_layer_present: bool
    data_layer: Optional[list]

    @property
    def vendors(self) -> Tuple[str, ...]:
        seen: List[str] = []
        for hit in self.vendor_hits:
            if hit.vendor not in seen:
                seen.append(hit.vendor)
        return tuple(seen)


def sniff_page(
    url: str,
    *,
    headless: bool = True,
    browser_name: str = "chromium",
    wait_until: str = "networkidle",
    wait_ms: int = 500,
) -> SniffResult:
    """Loads `url`, classifies every outgoing network request against the
    shared vendor-signature list, and reads `window.dataLayer` (present or
    not, and its current contents when it is) via `page.evaluate` -- both
    real runtime observations, not static-source guesses.
    """
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise RuntimeError(
            "Analytics sniffing requires Playwright. Install with "
            "`pip install pytagmanager[diagnostics]` and run `playwright install chromium` once."
        ) from exc

    vendor_hits: List[VendorHit] = []
    seen_urls: set = set()

    def _on_request(request) -> None:
        if request.url in seen_urls:
            return
        match = classify_vendor_url(request.url)
        if match is None:
            return
        seen_urls.add(request.url)
        vendor, category = match
        vendor_hits.append(VendorHit(vendor=vendor, category=category, url=request.url))

    with sync_playwright() as playwright:
        browser_type = getattr(playwright, browser_name)
        browser = browser_type.launch(headless=headless)
        try:
            context = browser.new_context()
            try:
                page = context.new_page()
                page.on("request", _on_request)
                page.goto(url, wait_until=wait_until)
                page.wait_for_timeout(wait_ms)
                data_layer = page.evaluate("() => (window.dataLayer !== undefined ? window.dataLayer : null)")
            finally:
                context.close()
        finally:
            browser.close()

    return SniffResult(
        url=url,
        vendor_hits=tuple(vendor_hits),
        data_layer_present=data_layer is not None,
        data_layer=data_layer,
    )
