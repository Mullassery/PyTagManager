"""The Tag Execution Graph (docs/VISION.md §17, Phase 1.85 items 5+6):
assembles static-scan nodes (item 1) + Interaction Traces (Phase 1.8) +
duplicate findings (item 2) + server-side indicators (item 3) into one
graph, with every edge labeled by evidence strength.

**The evidence vocabulary** (`EVIDENCE_LEVELS`) is this module's unified
schema (item 6) -- the same five labels docs/VISION.md §17 specifies:
`Observed` (this edge is a direct, captured `TrackingEvent`-to-
`TrackingEvent` transition within one Interaction Trace, or a static
scan's script/container detection), `Inferred` (a `server_side.py`
"Likely"-confidence indicator), `Suspected` (a `server_side.py`
"Possible"-confidence indicator, or a fan-out co-occurrence), `Unknown`
(reserved for future edge types this pass doesn't populate), and
`Not observed` (reserved for a future negative-evidence case, e.g. an
expected relay that a live GTM API check found isn't actually configured
-- Phase 1.9/1.95 territory, not populated here). No edge in this module
is ever labeled with a stronger claim than its source data supports --
`server_side.py`'s own hedging discipline (never "Confirmed") flows
straight through into `Inferred`/`Suspected` here, never upgraded to
`Observed`.

**Scope of this pass:** builds the graph from what items 1-3 already
produce. Phase 1.85 item 4 (background/post-load observer extensions)
and live GTM/GA4 config cross-referencing (which would upgrade some
`Suspected`/`Inferred` edges to `Observed` or add `Not observed` ones)
are not inputs here yet -- the graph is real and useful today, not a
placeholder waiting on those, but it will get more complete as those
land.
"""

from __future__ import annotations

import html
import json
from collections.abc import Sequence
from dataclasses import dataclass, field
from urllib.parse import urlparse

from pytagmanager.diagnostics.trace import InteractionTrace
from pytagmanager.tagexec.duplicates import DuplicateFinding
from pytagmanager.tagexec.server_side import ServerSideIndicator
from pytagmanager.tagexec.static_scan import StaticScanResult

EVIDENCE_OBSERVED = "Observed"
EVIDENCE_INFERRED = "Inferred"
EVIDENCE_SUSPECTED = "Suspected"
EVIDENCE_UNKNOWN = "Unknown"
EVIDENCE_NOT_OBSERVED = "Not observed"
EVIDENCE_LEVELS = (
    EVIDENCE_OBSERVED,
    EVIDENCE_INFERRED,
    EVIDENCE_SUSPECTED,
    EVIDENCE_UNKNOWN,
    EVIDENCE_NOT_OBSERVED,
)

NODE_GTM_CONTAINER = "gtm_container"
NODE_VENDOR_SCRIPT = "vendor_script"
NODE_INTERACTION = "interaction"
NODE_MUTATION = "mutation"
NODE_DATALAYER_EVENT = "datalayer_event"
NODE_GTM_EVENT = "gtm_event"
NODE_NETWORK_REQUEST = "network_request"
NODE_ENDPOINT = "endpoint"
NODE_SUSPECTED_VENDOR_RELAY = "suspected_vendor_relay"

_STAGE_TO_NODE_KIND = {
    "interaction": NODE_INTERACTION,
    "mutation": NODE_MUTATION,
    "datalayer": NODE_DATALAYER_EVENT,
    "gtm": NODE_GTM_EVENT,
    "network": NODE_NETWORK_REQUEST,
}


@dataclass(frozen=True)
class GraphNode:
    node_id: str
    kind: str
    label: str
    page_url: str
    metadata: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class GraphEdge:
    source_id: str
    target_id: str
    evidence: str  # one of EVIDENCE_LEVELS
    label: str


@dataclass(frozen=True)
class TagExecutionGraph:
    nodes: tuple[GraphNode, ...] = field(default_factory=tuple)
    edges: tuple[GraphEdge, ...] = field(default_factory=tuple)

    def node(self, node_id: str) -> GraphNode | None:
        return next((n for n in self.nodes if n.node_id == node_id), None)

    def outgoing(self, node_id: str) -> list[GraphEdge]:
        return [e for e in self.edges if e.source_id == node_id]

    def incoming(self, node_id: str) -> list[GraphEdge]:
        return [e for e in self.edges if e.target_id == node_id]


def _hostname(url: str) -> str:
    return (urlparse(url).hostname or "").lower()


class _GraphBuilder:
    def __init__(self) -> None:
        self._nodes: dict[str, GraphNode] = {}
        self._edges: list[GraphEdge] = []

    def add_node(
        self, node_id: str, kind: str, label: str, page_url: str, **metadata: object
    ) -> str:
        if node_id not in self._nodes:
            self._nodes[node_id] = GraphNode(
                node_id=node_id,
                kind=kind,
                label=label,
                page_url=page_url,
                metadata=dict(metadata),
            )
        return node_id

    def add_edge(self, source_id: str, target_id: str, evidence: str, label: str) -> None:
        key = (source_id, target_id, label)
        if any((e.source_id, e.target_id, e.label) == key for e in self._edges):
            return  # dedupe identical repeated edges (e.g. the same container seen on multiple pages)
        self._edges.append(
            GraphEdge(source_id=source_id, target_id=target_id, evidence=evidence, label=label)
        )

    def find_node_id(self, kind: str, label: str) -> str | None:
        """First node matching (kind, label) -- used to resolve a
        `DuplicateCandidate.involved` name (a plain container ID or vendor
        name, not a full node_id) back to its graph node. Picks the first
        match when a vendor name has more than one distinct evidence
        string on the page; a genuine ambiguity this heuristic doesn't try
        to resolve further."""
        return next(
            (n.node_id for n in self._nodes.values() if n.kind == kind and n.label == label),
            None,
        )

    def build(self) -> TagExecutionGraph:
        return TagExecutionGraph(nodes=tuple(self._nodes.values()), edges=tuple(self._edges))


def _add_static_scan_nodes(builder: _GraphBuilder, scan: StaticScanResult) -> None:
    for container in scan.gtm_containers:
        builder.add_node(
            f"gtm:{container.container_id}",
            NODE_GTM_CONTAINER,
            container.container_id,
            scan.page_url,
            load_mechanism=container.load_mechanism,
        )
    for vendor in scan.vendors:
        node_id = f"vendor:{vendor.vendor}:{vendor.evidence}"
        builder.add_node(
            node_id,
            NODE_VENDOR_SCRIPT,
            vendor.vendor,
            scan.page_url,
            category=vendor.category,
            evidence=vendor.evidence,
        )


def _add_trace_chain(builder: _GraphBuilder, trace: InteractionTrace) -> dict[int, str]:
    """One node per observed step, chained in temporal order with
    `Observed` edges -- every step in an `InteractionTrace` is a real,
    captured `TrackingEvent`, so this is the one part of the graph that's
    never hedged. Returns step-index -> node_id for endpoint linking."""
    node_ids: dict[int, str] = {}
    previous_id: str | None = None
    for index, step in enumerate(trace.steps):
        kind = _STAGE_TO_NODE_KIND.get(step.stage, "other")
        node_id = f"trace:{trace.journey_id}:step:{index}"
        label = step.event_name or step.event_type
        builder.add_node(
            node_id,
            kind,
            label,
            trace.page_url,
            event_type=step.event_type,
            timestamp=step.timestamp,
        )
        node_ids[index] = node_id
        if previous_id is not None:
            builder.add_edge(
                previous_id,
                node_id,
                EVIDENCE_OBSERVED,
                f"{trace.business_event}: next observed step",
            )
        previous_id = node_id
    return node_ids


def _add_endpoint_nodes(
    builder: _GraphBuilder, trace: InteractionTrace, step_node_ids: dict[int, str]
) -> dict[str, str]:
    """Endpoint nodes (one per distinct hostname) linked from the network
    step(s) that hit them -- `Observed`, since the request itself was
    captured. Returns hostname -> endpoint node_id for server-side linking."""
    endpoint_ids: dict[str, str] = {}
    for index, step in enumerate(trace.steps):
        if step.event_type != "network_request" or not isinstance(step.payload, dict):
            continue
        url = step.payload.get("url", "")
        host = _hostname(url)
        if not host:
            continue
        endpoint_id = f"endpoint:{host}"
        builder.add_node(endpoint_id, NODE_ENDPOINT, host, trace.page_url)
        endpoint_ids[host] = endpoint_id
        builder.add_edge(step_node_ids[index], endpoint_id, EVIDENCE_OBSERVED, "request sent to")
    return endpoint_ids


def _add_server_side_edges(
    builder: _GraphBuilder,
    indicator: ServerSideIndicator,
    endpoint_ids_by_page: dict[str, dict[str, str]],
) -> None:
    endpoint_ids = endpoint_ids_by_page.get(indicator.page_url, {})
    evidence = EVIDENCE_INFERRED if indicator.confidence == "Likely" else EVIDENCE_SUSPECTED

    if indicator.kind == "first_party_collection_endpoint":
        source_host = _hostname(indicator.evidence)
        source_id = endpoint_ids.get(source_host)
        if source_id is None:
            return
        relay_id = f"relay:{indicator.page_url}:{indicator.business_event}"
        builder.add_node(
            relay_id,
            NODE_SUSPECTED_VENDOR_RELAY,
            "possible vendor relay",
            indicator.page_url,
        )
        builder.add_edge(source_id, relay_id, evidence, indicator.message)

    elif indicator.kind == "fanout_to_multiple_destinations":
        hosts = [h for h in indicator.evidence.split(", ") if h]
        endpoint_node_ids = [endpoint_ids[h] for h in hosts if h in endpoint_ids]
        for i, source_id in enumerate(endpoint_node_ids):
            for target_id in endpoint_node_ids[i + 1 :]:
                builder.add_edge(source_id, target_id, evidence, indicator.message)


def _add_duplicate_edges(builder: _GraphBuilder, finding: DuplicateFinding) -> None:
    """Runtime-corroborated duplicate implementations, linked pairwise --
    `Observed`, since `analyze_duplicates()` only ever returns findings
    backed by real runtime evidence (see that module's docstring). Each
    `involved` name is resolved back to its node by kind+label lookup
    (a GTM container ID has an unambiguous node; a vendor name resolves to
    its first-detected node when the same vendor has more than one
    distinct evidence string on the page)."""
    node_ids = []
    for name in finding.candidate.involved:
        if name.startswith("GTM-"):
            node_id = builder.find_node_id(NODE_GTM_CONTAINER, name)
        else:
            node_id = builder.find_node_id(NODE_VENDOR_SCRIPT, name)
        if node_id is not None:
            node_ids.append(node_id)
    for i, source_id in enumerate(node_ids):
        for target_id in node_ids[i + 1 :]:
            builder.add_edge(source_id, target_id, EVIDENCE_OBSERVED, finding.message)


def build_tag_execution_graph(
    scans: Sequence[StaticScanResult],
    traces: Sequence[InteractionTrace],
    duplicate_findings: Sequence[DuplicateFinding] = (),
    server_side_indicators: Sequence[ServerSideIndicator] = (),
) -> TagExecutionGraph:
    """`scans` and `traces` are typically one-per-page (item 1's
    `scan_html()` result and Phase 1.8's `build_interaction_traces()`
    output for that page); `duplicate_findings`/`server_side_indicators`
    are `analyze_duplicates()`/`analyze_server_side_indicators()`'s
    output, aggregated across however many pages a `diagnose` run
    covered."""
    builder = _GraphBuilder()

    for scan in scans:
        _add_static_scan_nodes(builder, scan)

    endpoint_ids_by_page: dict[str, dict[str, str]] = {}
    for trace in traces:
        step_node_ids = _add_trace_chain(builder, trace)
        endpoint_ids = _add_endpoint_nodes(builder, trace, step_node_ids)
        endpoint_ids_by_page.setdefault(trace.page_url, {}).update(endpoint_ids)

    for indicator in server_side_indicators:
        _add_server_side_edges(builder, indicator, endpoint_ids_by_page)

    for finding in duplicate_findings:
        _add_duplicate_edges(builder, finding)

    return builder.build()


def build_graph_json(graph: TagExecutionGraph) -> dict:
    """The "unified finding/evidence schema" (item 6) in its walkable,
    serializable form -- every node and edge, with evidence labels never
    stronger than what produced them."""
    return {
        "nodes": [
            {
                "id": n.node_id,
                "kind": n.kind,
                "label": n.label,
                "page_url": n.page_url,
                "metadata": n.metadata,
            }
            for n in graph.nodes
        ],
        "edges": [
            {
                "source": e.source_id,
                "target": e.target_id,
                "evidence": e.evidence,
                "label": e.label,
            }
            for e in graph.edges
        ],
    }


_NODE_KIND_COLORS = {
    NODE_GTM_CONTAINER: "#1f77b4",
    NODE_VENDOR_SCRIPT: "#ff7f0e",
    NODE_INTERACTION: "#2ca02c",
    NODE_MUTATION: "#9467bd",
    NODE_DATALAYER_EVENT: "#17becf",
    NODE_GTM_EVENT: "#8c564b",
    NODE_NETWORK_REQUEST: "#7f7f7f",
}
_EVIDENCE_DASH = {
    EVIDENCE_OBSERVED: "",
    EVIDENCE_INFERRED: "6 4",
    EVIDENCE_SUSPECTED: "2 4",
    EVIDENCE_UNKNOWN: "1 6",
    EVIDENCE_NOT_OBSERVED: "1 3",
}


def build_graph_html(graph: TagExecutionGraph) -> str:
    """Render the Tag Execution Graph as a standalone, interactive HTML/SVG page.

    The JSON form (`build_graph_json`) is walkable but not meant to be read as
    flat text; this produces a single self-contained ``.html`` file with an
    inline SVG (one column per node kind, edges dashed by evidence strength),
    hover tooltips, and click-to-highlight of a node's neighbourhood. No
    external assets or network calls -- open the file directly.
    """
    nodes = list(graph.nodes)
    width = max(360, 180 + 220 * max(1, len({n.kind for n in nodes})))
    height = max(
        240,
        120
        + 70
        * max(
            1,
            max(
                (sum(1 for n in nodes if n.kind == k) for k in {n.kind for n in nodes}),
                default=1,
            ),
        ),
    )

    kinds = sorted({n.kind for n in nodes})
    positions: dict[str, tuple[float, float]] = {}
    for col, kind in enumerate(kinds):
        for row, node in enumerate(n for n in nodes if n.kind == kind):
            positions[node.node_id] = (140 + col * 220, 80 + row * 70)

    parts: list[str] = []
    for edge in graph.edges:
        if edge.source_id not in positions or edge.target_id not in positions:
            continue
        x1, y1 = positions[edge.source_id]
        x2, y2 = positions[edge.target_id]
        dash = _EVIDENCE_DASH.get(edge.evidence, "2 4")
        dash_attr = f' stroke-dasharray="{dash}"' if dash else ""
        parts.append(
            f'<line class="edge" data-source="{html.escape(edge.source_id)}" '
            f'data-target="{html.escape(edge.target_id)}" x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}"'
            f"{dash_attr}><title>{html.escape(edge.evidence)}: {html.escape(edge.label)}</title></line>"
        )
    for node in nodes:
        if node.node_id not in positions:
            continue
        x, y = positions[node.node_id]
        color = _NODE_KIND_COLORS.get(node.kind, "#555555")
        parts.append(
            f'<g class="node" data-id="{html.escape(node.node_id)}">'
            f'<circle cx="{x}" cy="{y}" r="10" fill="{color}"><title>'
            f"{html.escape(node.kind)}: {html.escape(node.label)}\n{html.escape(node.page_url)}</title></circle>"
            f'<text x="{x + 16}" y="{y + 4}">{html.escape(node.label)}</text></g>'
        )

    legend = "".join(
        '<span class="legend-item"><svg width="24" height="8"><line x1="0" y1="4" x2="24" y2="4" '
        'stroke="#333" stroke-width="1.5"'
        + (f' stroke-dasharray="{_EVIDENCE_DASH[e]}"' if _EVIDENCE_DASH.get(e) else "")
        + f"/></svg>{html.escape(e)}</span>"
        for e in EVIDENCE_LEVELS
    )

    data_json = (
        json.dumps(build_graph_json(graph))
        .replace("<", "\\u003c")
        .replace(">", "\\u003e")
        .replace("&", "\\u0026")
    )

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Tag Execution Graph</title>
<style>
  body {{ font-family: -apple-system, Segoe UI, Roboto, sans-serif; margin: 1.5rem; }}
  svg {{ border: 1px solid #ddd; }}
  .edge {{ stroke: #999; stroke-width: 1.2; }}
  .edge.hot {{ stroke: #d62728; stroke-width: 2.2; }}
  .node text {{ font-size: 11px; fill: #222; }}
  .node.dim {{ opacity: 0.25; }}
  .legend-item {{ margin-right: 1rem; font-size: 12px; display: inline-flex; align-items: center; gap: 4px; }}
</style>
</head>
<body>
<h1>Tag Execution Graph</h1>
<p>{len(nodes)} node(s), {len(graph.edges)} edge(s). Click a node to highlight its edges; click the background to reset.</p>
<p class="legend">{legend}</p>
<svg id="graph" width="{width}" height="{height}" viewBox="0 0 {width} {height}">
{chr(10).join(parts)}
</svg>
<script id="graph-data" type="application/json">{data_json}</script>
<script>
(function () {{
  var svg = document.getElementById('graph');
  var selected = null;
  function highlight(id) {{
    var nodes = svg.querySelectorAll('.node');
    var edges = svg.querySelectorAll('.edge');
    if (!id) {{
      nodes.forEach(function (n) {{ n.classList.remove('dim'); }});
      edges.forEach(function (e) {{ e.classList.remove('hot'); }});
      return;
    }}
    var keep = new Set([id]);
    edges.forEach(function (e) {{
      var s = e.getAttribute('data-source'), t = e.getAttribute('data-target');
      if (s === id || t === id) {{ e.classList.add('hot'); keep.add(s); keep.add(t); }}
      else {{ e.classList.remove('hot'); }}
    }});
    nodes.forEach(function (n) {{
      n.classList.toggle('dim', !keep.has(n.getAttribute('data-id')));
    }});
  }}
  svg.querySelectorAll('.node').forEach(function (n) {{
    n.addEventListener('click', function (ev) {{
      ev.stopPropagation();
      selected = selected === n.getAttribute('data-id') ? null : n.getAttribute('data-id');
      highlight(selected);
    }});
  }});
  svg.addEventListener('click', function () {{ selected = null; highlight(null); }});
}})();
</script>
</body>
</html>
"""
