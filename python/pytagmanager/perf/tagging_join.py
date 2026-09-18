"""Tagging-vs-performance join (docs/VISION.md §16, Phase 1.95 item 5):
cross-reference a script's measured performance cost with what it's
already known to do from the tagging-intelligence side -- reusing
`perf/scripts.py`'s vendor/category classification (itself reusing
Phase 1.85's `tagexec.static_scan` signatures) rather than a second,
duplicate classifier, and, when a Phase 1.85 Tag Execution Graph is
available, the specific graph node the script corresponds to -- so cost
attributes to "GTM -> Vendor Loader -> Advertising SDK" instead of only
an isolated script in a flat ranking, per VISION.md §16's own example.

A script with no matching isolation-experiment result gets `None` cost
fields, not zero -- zero would falsely claim "measured no impact" when
nothing was actually measured for that script.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Sequence

from pytagmanager.perf.experiments import IsolationExperimentResult
from pytagmanager.perf.scripts import ScriptEntry, ScriptInventory
from pytagmanager.tagexec.graph import NODE_VENDOR_SCRIPT, TagExecutionGraph


@dataclass(frozen=True)
class TaggingPerformanceTradeoff:
    script_url: str
    vendor: Optional[str]
    category: Optional[str]
    tbt_delta_ms: Optional[float]
    lcp_delta_ms: Optional[float]
    transfer_bytes: Optional[float]
    graph_node_id: Optional[str]


def _match_graph_node(script: ScriptEntry, graph: Optional[TagExecutionGraph]) -> Optional[str]:
    if graph is None or not script.vendor:
        return None
    for node in graph.nodes:
        if node.kind == NODE_VENDOR_SCRIPT and node.label == script.vendor:
            return node.node_id
    return None


def _matching_result(script: ScriptEntry, results: Sequence[IsolationExperimentResult]) -> Optional[IsolationExperimentResult]:
    return next((r for r in results if script.url in r.blocked_urls), None)


def build_tagging_performance_tradeoffs(
    inventory: ScriptInventory,
    experiment_results: Sequence[IsolationExperimentResult] = (),
    graph: Optional[TagExecutionGraph] = None,
) -> List[TaggingPerformanceTradeoff]:
    """Only classified (tagging-relevant) scripts participate -- an
    unclassified first-party script has no known "tagging capability" to
    join against, so it's excluded rather than included with every field
    `None`. `experiment_results` is typically one `isolate_script()`/
    `isolate_group()` result per script/group actually tested; a script
    covered by more than one result (e.g. tested individually and as part
    of a group) matches whichever comes first in the sequence."""
    tradeoffs = []
    for script in inventory.scripts:
        if script.category is None:
            continue
        result = _matching_result(script, experiment_results)
        tradeoffs.append(
            TaggingPerformanceTradeoff(
                script_url=script.url,
                vendor=script.vendor,
                category=script.category,
                tbt_delta_ms=result.tbt_delta_ms if result else None,
                lcp_delta_ms=result.lcp_delta_ms if result else None,
                transfer_bytes=script.transfer_bytes,
                graph_node_id=_match_graph_node(script, graph),
            )
        )
    return tradeoffs
