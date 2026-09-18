"""Performance measurement engine (docs/VISION.md §16, Phase 1.95 item 1):
LCP/CLS/FCP/TBT/INP and JS transfer/request-count metrics, aggregated
over repeated page loads.

**Every metric is a real browser-native measurement from the standard
Performance Timeline API** (`PerformanceObserver` + `performance.
getEntriesByType`), captured by `perf_agent.js` -- not a Lighthouse
wrapper, not CDP tracing, not an approximation dressed up as a
measurement. This is a real, disclosed trade-off: it's a subset of what
Lighthouse reports (no Speed Index, no lab-simulated CPU/network
throttling baked into the metric itself), not a hidden limitation.

**Never a single-run number.** `measure_page_performance()` always loads
the page in `runs` (default 3) fresh browser contexts -- never reusing a
warm cache/JS heap across runs, which would bias every metric -- and
returns a `PerformanceBaseline` whose `median_*` properties are what
callers should report or compare, per VISION.md §16's explicit
"median/percentile, never a single-run number."
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Sequence, Tuple

_PERF_AGENT_JS_PATH = Path(__file__).parent / "perf_agent.js"


@dataclass(frozen=True)
class PerformanceSnapshot:
    lcp_ms: Optional[float]
    lcp_url: Optional[str]
    cls: float
    fcp_ms: Optional[float]
    tbt_ms: float
    inp_ms: Optional[float]
    dom_content_loaded_ms: Optional[float]
    load_event_ms: Optional[float]
    transfer_bytes: float
    request_count: int
    long_task_count: int

    @classmethod
    def from_raw(cls, raw: dict) -> "PerformanceSnapshot":
        return cls(
            lcp_ms=raw.get("lcpMs"),
            lcp_url=raw.get("lcpUrl"),
            cls=raw.get("cls") or 0.0,
            fcp_ms=raw.get("fcpMs"),
            tbt_ms=raw.get("tbtMs") or 0.0,
            inp_ms=raw.get("inpMs"),
            dom_content_loaded_ms=raw.get("domContentLoadedMs"),
            load_event_ms=raw.get("loadEventMs"),
            transfer_bytes=raw.get("transferBytes") or 0.0,
            request_count=int(raw.get("requestCount") or 0),
            long_task_count=int(raw.get("longTaskCount") or 0),
        )


def _median(values: Sequence[Optional[float]]) -> Optional[float]:
    present = [v for v in values if v is not None]
    return statistics.median(present) if present else None


@dataclass(frozen=True)
class PerformanceBaseline:
    url: str
    runs: Tuple[PerformanceSnapshot, ...] = field(default_factory=tuple)

    @property
    def run_count(self) -> int:
        return len(self.runs)

    @property
    def median_lcp_ms(self) -> Optional[float]:
        return _median([r.lcp_ms for r in self.runs])

    @property
    def median_cls(self) -> Optional[float]:
        return _median([r.cls for r in self.runs])

    @property
    def median_fcp_ms(self) -> Optional[float]:
        return _median([r.fcp_ms for r in self.runs])

    @property
    def median_tbt_ms(self) -> Optional[float]:
        return _median([r.tbt_ms for r in self.runs])

    @property
    def median_inp_ms(self) -> Optional[float]:
        return _median([r.inp_ms for r in self.runs])

    @property
    def median_request_count(self) -> Optional[float]:
        return _median([float(r.request_count) for r in self.runs])

    @property
    def median_transfer_bytes(self) -> Optional[float]:
        return _median([r.transfer_bytes for r in self.runs])


def capture_performance_snapshot(page, wait_ms: int = 500) -> PerformanceSnapshot:
    """Reads `window.__ptm_perf.getSnapshot()` from an already-loaded
    page -- `perf_agent.js` must have been injected before load via
    `add_init_script` (see `measure_page_performance()`). `wait_ms` gives
    async paint/layout-shift/long-task entries a moment to settle before
    reading; these can fire slightly after the `load` event."""
    page.wait_for_timeout(wait_ms)
    raw = page.evaluate("() => window.__ptm_perf.getSnapshot()")
    return PerformanceSnapshot.from_raw(raw)


def measure_page_performance(
    url: str,
    *,
    runs: int = 3,
    headless: bool = True,
    browser_name: str = "chromium",
    wait_ms: int = 500,
    block_url_patterns: Optional[Sequence[str]] = None,
) -> PerformanceBaseline:
    """Loads `url` in `runs` fresh browser contexts (never reusing state
    across runs), capturing one `PerformanceSnapshot` per run.

    `block_url_patterns` (Playwright glob/regex route patterns) is the
    isolation-experiment hook `perf/experiments.py` (item 4) re-uses this
    function through, to block a script/group and re-measure against this
    same baseline logic -- when empty, this is the unmodified baseline.
    """
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise RuntimeError(
            "Performance measurement requires Playwright. Install with "
            "`pip install pytagmanager[diagnostics]` and run `playwright install chromium` once."
        ) from exc

    perf_agent_js = _PERF_AGENT_JS_PATH.read_text()
    snapshots: List[PerformanceSnapshot] = []

    with sync_playwright() as playwright:
        browser_type = getattr(playwright, browser_name)
        browser = browser_type.launch(headless=headless)
        try:
            for _ in range(runs):
                context = browser.new_context()
                try:
                    for pattern in block_url_patterns or ():
                        context.route(pattern, lambda route: route.abort())
                    page = context.new_page()
                    page.add_init_script(perf_agent_js)
                    page.goto(url, wait_until="networkidle")
                    snapshots.append(capture_performance_snapshot(page, wait_ms=wait_ms))
                finally:
                    context.close()
        finally:
            browser.close()

    return PerformanceBaseline(url=url, runs=tuple(snapshots))
