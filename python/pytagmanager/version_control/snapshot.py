"""On-disk crawl snapshot format for version control / change detection
across crawls (docs/ARCHITECTURE.md's "Version control / change detection"
capability).

A snapshot is a plain JSON document capturing everything `diff.py` needs to
compare two crawls of the same (or a related) site over time: per page, the
DOM elements PyTagManager's semantic graph extracted (a reduced,
JSON-serializable view of `pytagmanager._core.SemanticNode` -- selectors,
text, ARIA metadata) and the tracking recommendations generated for it. No
external infra is involved; it's just `json.dump`/`json.load` of
dataclasses, designed to be diffed by `diff.py` or committed to source
control by the caller (e.g. as a baseline checked into a repo) like any
other text artifact.
"""

from __future__ import annotations

import datetime
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, List, Sequence

from pytagmanager.recommend.models import TrackingRecommendation

SNAPSHOT_FORMAT_VERSION = 1


@dataclass(frozen=True)
class SnapshotNode:
    tag: str
    text: str
    stable_selector: str | None
    css_selector: str
    xpath: str
    aria_label: str | None
    aria_role: str | None
    classes: List[str]
    attributes: Dict[str, str]

    @property
    def identity_key(self) -> str:
        """Best-effort stable identity for this element across crawls of the
        same page: prefer the resilient stable_selector (data-testid /
        data-* / aria-label / id, per dom/selectors.rs's own priority
        order), falling back to the positional css_selector when no stable
        attribute exists. This is what `diff.py` matches old vs. new
        elements on."""
        return self.stable_selector or self.css_selector

    @classmethod
    def from_semantic_node(cls, node: Any) -> "SnapshotNode":
        return cls(
            tag=node.tag,
            text=node.text,
            stable_selector=node.stable_selector,
            css_selector=node.css_selector,
            xpath=node.xpath,
            aria_label=node.aria_label,
            aria_role=node.aria_role,
            classes=list(node.classes),
            attributes=dict(node.attributes),
        )

    @classmethod
    def from_dict(cls, data: dict) -> "SnapshotNode":
        return cls(
            tag=data["tag"],
            text=data["text"],
            stable_selector=data.get("stable_selector"),
            css_selector=data["css_selector"],
            xpath=data["xpath"],
            aria_label=data.get("aria_label"),
            aria_role=data.get("aria_role"),
            classes=list(data.get("classes", [])),
            attributes=dict(data.get("attributes", {})),
        )


@dataclass(frozen=True)
class SnapshotRecommendation:
    event_name: str
    trigger_type: str
    selector: str
    business_objective: str
    confidence: float
    rationale: str

    @property
    def identity_key(self) -> str:
        """Recommendations are matched old vs. new on (event_name, selector)
        -- the pair that determines what a generated tag/trigger actually
        does, not the exact confidence score or rationale text (those are
        expected to fluctuate as heuristics/wording evolve without the
        underlying recommendation being a meaningfully different one)."""
        return f"{self.event_name}@{self.selector}"

    @classmethod
    def from_recommendation(cls, rec: TrackingRecommendation) -> "SnapshotRecommendation":
        return cls(
            event_name=rec.event_name,
            trigger_type=rec.trigger_type,
            selector=rec.selector,
            business_objective=rec.business_objective,
            confidence=rec.confidence,
            rationale=rec.rationale,
        )

    @classmethod
    def from_dict(cls, data: dict) -> "SnapshotRecommendation":
        return cls(**data)


@dataclass(frozen=True)
class SnapshotPage:
    url: str
    status: int
    nodes: List[SnapshotNode]
    recommendations: List[SnapshotRecommendation]

    @classmethod
    def from_dict(cls, data: dict) -> "SnapshotPage":
        return cls(
            url=data["url"],
            status=data["status"],
            nodes=[SnapshotNode.from_dict(n) for n in data.get("nodes", [])],
            recommendations=[SnapshotRecommendation.from_dict(r) for r in data.get("recommendations", [])],
        )


@dataclass(frozen=True)
class CrawlSnapshot:
    format_version: int
    created_at: str
    root_url: str
    pages: List[SnapshotPage]

    @classmethod
    def from_dict(cls, data: dict) -> "CrawlSnapshot":
        return cls(
            format_version=data.get("format_version", SNAPSHOT_FORMAT_VERSION),
            created_at=data["created_at"],
            root_url=data["root_url"],
            pages=[SnapshotPage.from_dict(p) for p in data.get("pages", [])],
        )


def build_snapshot(
    pages: Sequence[Any],
    recommendations_by_url: Dict[str, Sequence[TrackingRecommendation]],
    root_url: str,
) -> CrawlSnapshot:
    """Build a `CrawlSnapshot` from a completed crawl: `pages` is whatever
    `crawl_site()`/`pytagmanager._core.crawl()` returned (real `_core.Page`
    objects, or anything duck-typing `.url`/`.status`/`.graph.nodes` --
    tests use this to snapshot fake pages too), `recommendations_by_url`
    maps each page's URL to the `recommend_for_graph()` output for that
    page.
    """
    snapshot_pages = []
    for page in pages:
        recs = recommendations_by_url.get(page.url, [])
        snapshot_pages.append(
            SnapshotPage(
                url=page.url,
                status=page.status,
                nodes=[SnapshotNode.from_semantic_node(n) for n in page.graph.nodes],
                recommendations=[SnapshotRecommendation.from_recommendation(r) for r in recs],
            )
        )

    return CrawlSnapshot(
        format_version=SNAPSHOT_FORMAT_VERSION,
        created_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
        root_url=root_url,
        pages=snapshot_pages,
    )


def save_snapshot(snapshot: CrawlSnapshot, path: str) -> None:
    Path(path).write_text(json.dumps(asdict(snapshot), indent=2))


def load_snapshot(path: str) -> CrawlSnapshot:
    data = json.loads(Path(path).read_text())
    return CrawlSnapshot.from_dict(data)
