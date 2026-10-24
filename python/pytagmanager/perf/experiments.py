"""Isolation experiments (docs/VISION.md §16, Phase 1.95 item 4): block
one script, one group, or every classifiable non-essential script, and
re-measure against a baseline. This is the pillar's actual differentiator
-- per VISION.md §16, "the differentiator is the isolation-experiment
layer Lighthouse doesn't have."

**Groups are a disclosed subset of VISION's full list.** VISION.md §16
names analytics/ads/personalization/chat/social/consent/tag-management/
heatmaps/A-B-testing. This module can only group by what's actually
classifiable today: `tagexec.static_scan`'s vendor categories (analytics/
ads/heatmap ["heatmaps"]/experimentation ["A-B-testing"]/chat/payment/
video) plus a `tag_management` group matched directly by GTM loader URL
(GTM containers aren't in the vendor signature list -- they're tracked
separately in `tagexec.static_scan` -- so this one group is matched by
pattern here instead of by `ScriptEntry.category`). `personalization`,
`social`, and `consent` have no existing detector to group by and are not
fabricated groups with nothing in them.

**"All non-essential" means "every script this product can currently
classify as tagging/marketing-adjacent"** -- every script with a
`ScriptEntry.category` plus every GTM loader -- not a guess at which
arbitrary first-party scripts are "inessential" to the business. A
first-party, unclassified script is never auto-blocked; that's a real
scope boundary of what this pass can safely automate, not an oversight.

**Every result reports *observed experimental impact*, never claimed
causality beyond what the isolation run itself supports** -- per
VISION.md §16's own framing: blocking a script and observing a metric
delta is real, controlled evidence for *that specific script on that
specific run*, worded as an observation, not a general causal law.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass, field

from pytagmanager.perf.dependency_graph import (
    ScriptDependencyGraph,
    build_dependency_graph,
)
from pytagmanager.perf.measure import PerformanceBaseline, measure_page_performance
from pytagmanager.perf.scripts import (
    ScriptEntry,
    ScriptInventory,
    build_script_inventory,
)

GROUP_TAG_MANAGEMENT = "tag_management"
_GTM_LOADER_PATTERN = re.compile(r"googletagmanager\.com/gtm\.js")


def _script_group(script: ScriptEntry) -> str | None:
    if _GTM_LOADER_PATTERN.search(script.url):
        return GROUP_TAG_MANAGEMENT
    return script.category


def available_groups(inventory: ScriptInventory) -> tuple[str, ...]:
    """Every group actually present in this inventory -- not VISION's
    full aspirational list, which would misrepresent what a caller can
    actually isolate on this page."""
    return tuple(sorted({g for s in inventory.scripts if (g := _script_group(s)) is not None}))


def _closure(urls: Iterable[str], graph: ScriptDependencyGraph) -> set[str]:
    blocked: set[str] = set(urls)
    for target_url in list(blocked):
        blocked |= graph.downstream_of(target_url)
    return blocked


@dataclass(frozen=True)
class IsolationExperimentResult:
    target_description: str
    blocked_urls: tuple[str, ...] = field(default_factory=tuple)
    baseline: PerformanceBaseline | None = None
    experiment: PerformanceBaseline | None = None

    def _delta(self, metric: str) -> float | None:
        if self.baseline is None or self.experiment is None:
            return None
        before = getattr(self.baseline, metric)
        after = getattr(self.experiment, metric)
        if before is None or after is None:
            return None
        return before - after

    @property
    def lcp_delta_ms(self) -> float | None:
        return self._delta("median_lcp_ms")

    @property
    def tbt_delta_ms(self) -> float | None:
        return self._delta("median_tbt_ms")

    @property
    def cls_delta(self) -> float | None:
        return self._delta("median_cls")

    @property
    def inp_delta_ms(self) -> float | None:
        return self._delta("median_inp_ms")

    @property
    def transfer_bytes_delta(self) -> float | None:
        return self._delta("median_transfer_bytes")

    @property
    def request_count_delta(self) -> float | None:
        return self._delta("median_request_count")

    @property
    def message(self) -> str:
        parts = []
        for label, delta, unit in (
            ("LCP", self.lcp_delta_ms, "ms"),
            ("TBT", self.tbt_delta_ms, "ms"),
            ("INP", self.inp_delta_ms, "ms"),
            ("CLS", self.cls_delta, ""),
        ):
            if delta is not None and abs(delta) > 0:
                direction = "improved" if delta > 0 else "worsened"
                parts.append(f"{label} {direction} by {abs(delta):.1f}{unit}")
        observed = ", ".join(parts) if parts else "no measurable change"
        return (
            f"Blocking {self.target_description} ({len(self.blocked_urls)} script(s)): observed {observed} "
            f"across {self.experiment.run_count if self.experiment else 0} controlled run(s) vs. baseline. "
            "This is the observed experimental impact of blocking these specific scripts on this run -- "
            "not a general claim about the script's cost on every page or every visitor."
        )


def _run(
    url: str,
    target_description: str,
    blocked_urls: set[str],
    *,
    baseline: PerformanceBaseline | None,
    runs: int,
    headless: bool,
    browser_name: str,
) -> IsolationExperimentResult:
    if baseline is None:
        baseline = measure_page_performance(
            url, runs=runs, headless=headless, browser_name=browser_name
        )
    experiment = measure_page_performance(
        url,
        runs=runs,
        headless=headless,
        browser_name=browser_name,
        block_url_patterns=tuple(sorted(blocked_urls)),
    )
    return IsolationExperimentResult(
        target_description=target_description,
        blocked_urls=tuple(sorted(blocked_urls)),
        baseline=baseline,
        experiment=experiment,
    )


def isolate_script(
    url: str,
    script_url: str,
    *,
    inventory: ScriptInventory | None = None,
    baseline: PerformanceBaseline | None = None,
    runs: int = 3,
    headless: bool = True,
    browser_name: str = "chromium",
) -> IsolationExperimentResult:
    """Blocks `script_url` and everything downstream of it (per the
    dependency graph, item 3) -- so blocking GTM correctly stops its
    GA4/Meta Pixel/etc. children too, not just the GTM loader itself."""
    inventory = inventory or build_script_inventory(
        url, headless=headless, browser_name=browser_name
    )
    graph = build_dependency_graph(inventory)
    blocked = _closure([script_url], graph)
    return _run(
        url,
        f"script {script_url}",
        blocked,
        baseline=baseline,
        runs=runs,
        headless=headless,
        browser_name=browser_name,
    )


def isolate_group(
    url: str,
    group: str,
    *,
    inventory: ScriptInventory | None = None,
    baseline: PerformanceBaseline | None = None,
    runs: int = 3,
    headless: bool = True,
    browser_name: str = "chromium",
) -> IsolationExperimentResult:
    inventory = inventory or build_script_inventory(
        url, headless=headless, browser_name=browser_name
    )
    graph = build_dependency_graph(inventory)
    matching = [s.url for s in inventory.scripts if _script_group(s) == group]
    blocked = _closure(matching, graph)
    return _run(
        url,
        f"group '{group}'",
        blocked,
        baseline=baseline,
        runs=runs,
        headless=headless,
        browser_name=browser_name,
    )


def isolate_all_non_essential(
    url: str,
    *,
    inventory: ScriptInventory | None = None,
    baseline: PerformanceBaseline | None = None,
    runs: int = 3,
    headless: bool = True,
    browser_name: str = "chromium",
) -> IsolationExperimentResult:
    inventory = inventory or build_script_inventory(
        url, headless=headless, browser_name=browser_name
    )
    graph = build_dependency_graph(inventory)
    matching = [s.url for s in inventory.scripts if _script_group(s) is not None]
    blocked = _closure(matching, graph)
    return _run(
        url,
        "all non-essential (classified) scripts",
        blocked,
        baseline=baseline,
        runs=runs,
        headless=headless,
        browser_name=browser_name,
    )
