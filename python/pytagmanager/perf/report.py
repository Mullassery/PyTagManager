"""Script ranking, Web-Vitals-with-evidence reporting, and per-template
aggregation (docs/VISION.md §16, Phase 1.95 item 6).

Per-template aggregation reuses `sitewide/templates.py`'s existing
page-type clustering *conceptually* -- this module accepts an
already-clustered `template_label` (a caller, e.g. the CLI, derives it via
`sitewide.templates.detect_templates()` the same way `diagnose --site-wide`
already does) and a per-template `PerformanceBaseline`, rather than
re-implementing clustering here. A full multi-page perf crawl orchestrator
that runs `detect_templates()` itself is CLI/integration surface, not
report-building logic, and stays out of this module on purpose.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Sequence, Tuple

from pytagmanager.perf.measure import PerformanceBaseline
from pytagmanager.perf.tagging_join import TaggingPerformanceTradeoff

JSON_SCHEMA_VERSION = 1


def rank_scripts_by_cost(tradeoffs: Sequence[TaggingPerformanceTradeoff]) -> List[TaggingPerformanceTradeoff]:
    """Highest measured TBT cost first. A script with no measured cost
    (never isolation-tested) sorts last, not first or zero -- "untested"
    and "measured zero impact" are different claims, and conflating them
    would misrepresent an untested script as harmless."""

    def sort_key(t: TaggingPerformanceTradeoff) -> Tuple[bool, float]:
        return (t.tbt_delta_ms is None, -(t.tbt_delta_ms or 0.0))

    return sorted(tradeoffs, key=sort_key)


@dataclass(frozen=True)
class TemplatePerformanceSummary:
    template_label: str
    median_lcp_ms: "float | None"
    median_tbt_ms: "float | None"
    top_contributors: Tuple[str, ...] = field(default_factory=tuple)


def summarize_template_performance(
    template_label: str,
    baseline: PerformanceBaseline,
    tradeoffs: Sequence[TaggingPerformanceTradeoff],
    top_n: int = 5,
) -> TemplatePerformanceSummary:
    ranked = rank_scripts_by_cost([t for t in tradeoffs if t.tbt_delta_ms is not None])
    contributors = tuple(t.vendor or t.script_url for t in ranked[:top_n])
    return TemplatePerformanceSummary(
        template_label=template_label,
        median_lcp_ms=baseline.median_lcp_ms,
        median_tbt_ms=baseline.median_tbt_ms,
        top_contributors=contributors,
    )


def render_performance_report(
    baseline: PerformanceBaseline, tradeoffs: Sequence[TaggingPerformanceTradeoff]
) -> List[str]:
    """Rendered as a list of lines, matching `tagexec.report`'s convention
    -- callers splice this into a larger report."""
    lines = [f"PERFORMANCE: {baseline.url}", "-" * (14 + len(baseline.url))]
    lines.append(f"  Runs: {baseline.run_count}")
    lines.append(f"  Median LCP: {baseline.median_lcp_ms}ms")
    lines.append(f"  Median TBT: {baseline.median_tbt_ms}ms")
    lines.append(f"  Median CLS: {baseline.median_cls}")
    lines.append(f"  Median INP: {baseline.median_inp_ms}ms")
    ranked = rank_scripts_by_cost(tradeoffs)
    if ranked:
        lines.append("")
        lines.append("  Script cost ranking (tagging-relevant scripts, by measured TBT impact):")
        for t in ranked:
            cost = f"{t.tbt_delta_ms:.1f}ms TBT" if t.tbt_delta_ms is not None else "not isolation-tested"
            lines.append(f"    - {t.vendor or t.script_url} ({t.category}): {cost}")
    lines.append("")
    return lines


def build_performance_report_json(baseline: PerformanceBaseline, tradeoffs: Sequence[TaggingPerformanceTradeoff]) -> dict:
    return {
        "schema_version": JSON_SCHEMA_VERSION,
        "url": baseline.url,
        "run_count": baseline.run_count,
        "median_lcp_ms": baseline.median_lcp_ms,
        "median_tbt_ms": baseline.median_tbt_ms,
        "median_cls": baseline.median_cls,
        "median_inp_ms": baseline.median_inp_ms,
        "median_fcp_ms": baseline.median_fcp_ms,
        "median_request_count": baseline.median_request_count,
        "median_transfer_bytes": baseline.median_transfer_bytes,
        "script_ranking": [
            {
                "script_url": t.script_url,
                "vendor": t.vendor,
                "category": t.category,
                "tbt_delta_ms": t.tbt_delta_ms,
                "lcp_delta_ms": t.lcp_delta_ms,
                "transfer_bytes": t.transfer_bytes,
                "graph_node_id": t.graph_node_id,
            }
            for t in rank_scripts_by_cost(tradeoffs)
        ],
    }
