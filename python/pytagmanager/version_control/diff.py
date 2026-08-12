"""Diffing engine for `CrawlSnapshot`s: given two crawl snapshots (e.g. a
saved baseline and a fresh crawl of the same site), report added/removed
pages, added/removed/changed DOM elements within pages present in both, and
added/removed tracking recommendations -- docs/ARCHITECTURE.md's "Version
control / change detection across crawls" capability. Pure in-memory
comparison of `snapshot.py`'s dataclasses; no crawling or I/O happens here.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List

from pytagmanager.version_control.snapshot import (
    CrawlSnapshot,
    SnapshotNode,
    SnapshotPage,
    SnapshotRecommendation,
)

# Node fields compared to decide whether a same-identity element "changed"
# (text/attribute edits) rather than being added/removed outright.
_TRACKED_NODE_FIELDS = ("tag", "text", "css_selector", "xpath", "aria_label", "aria_role", "classes", "attributes")


@dataclass
class ElementFieldChange:
    field: str
    old: object
    new: object


@dataclass
class ElementChange:
    identity_key: str
    field_changes: List[ElementFieldChange]


@dataclass
class PageDiff:
    url: str
    added_elements: List[SnapshotNode] = field(default_factory=list)
    removed_elements: List[SnapshotNode] = field(default_factory=list)
    changed_elements: List[ElementChange] = field(default_factory=list)
    added_recommendations: List[SnapshotRecommendation] = field(default_factory=list)
    removed_recommendations: List[SnapshotRecommendation] = field(default_factory=list)

    @property
    def has_changes(self) -> bool:
        return bool(
            self.added_elements
            or self.removed_elements
            or self.changed_elements
            or self.added_recommendations
            or self.removed_recommendations
        )


@dataclass
class CrawlDiff:
    old_root_url: str
    new_root_url: str
    added_pages: List[str] = field(default_factory=list)
    removed_pages: List[str] = field(default_factory=list)
    changed_pages: List[PageDiff] = field(default_factory=list)
    unchanged_page_count: int = 0


def _diff_page(old_page: SnapshotPage, new_page: SnapshotPage) -> PageDiff:
    old_nodes = {n.identity_key: n for n in old_page.nodes}
    new_nodes = {n.identity_key: n for n in new_page.nodes}

    added_elements = [new_nodes[k] for k in new_nodes.keys() - old_nodes.keys()]
    removed_elements = [old_nodes[k] for k in old_nodes.keys() - new_nodes.keys()]

    changed_elements = []
    for key in old_nodes.keys() & new_nodes.keys():
        old_node, new_node = old_nodes[key], new_nodes[key]
        field_changes = [
            ElementFieldChange(field=f, old=getattr(old_node, f), new=getattr(new_node, f))
            for f in _TRACKED_NODE_FIELDS
            if getattr(old_node, f) != getattr(new_node, f)
        ]
        if field_changes:
            changed_elements.append(ElementChange(identity_key=key, field_changes=field_changes))

    old_recs = {r.identity_key: r for r in old_page.recommendations}
    new_recs = {r.identity_key: r for r in new_page.recommendations}
    added_recommendations = [new_recs[k] for k in new_recs.keys() - old_recs.keys()]
    removed_recommendations = [old_recs[k] for k in old_recs.keys() - new_recs.keys()]

    return PageDiff(
        url=new_page.url,
        added_elements=added_elements,
        removed_elements=removed_elements,
        changed_elements=changed_elements,
        added_recommendations=added_recommendations,
        removed_recommendations=removed_recommendations,
    )


def diff_snapshots(old: CrawlSnapshot, new: CrawlSnapshot) -> CrawlDiff:
    """Compare two `CrawlSnapshot`s and report added/removed pages plus,
    for every page present in both, added/removed/changed DOM elements and
    tracking recommendations. Pages are matched by URL; elements within a
    page are matched by `SnapshotNode.identity_key`
    (stable_selector-preferred); recommendations by
    `SnapshotRecommendation.identity_key` (event_name + selector).
    """
    old_pages = {p.url: p for p in old.pages}
    new_pages = {p.url: p for p in new.pages}

    added_pages = sorted(new_pages.keys() - old_pages.keys())
    removed_pages = sorted(old_pages.keys() - new_pages.keys())

    changed_pages = []
    unchanged_count = 0
    for url in sorted(old_pages.keys() & new_pages.keys()):
        page_diff = _diff_page(old_pages[url], new_pages[url])
        if page_diff.has_changes:
            changed_pages.append(page_diff)
        else:
            unchanged_count += 1

    return CrawlDiff(
        old_root_url=old.root_url,
        new_root_url=new.root_url,
        added_pages=added_pages,
        removed_pages=removed_pages,
        changed_pages=changed_pages,
        unchanged_page_count=unchanged_count,
    )


def format_diff_report(diff: CrawlDiff) -> str:
    """Render a `CrawlDiff` as a human-readable text report (used by the
    `pytagmanager diff` CLI command)."""
    lines = [f"Crawl diff: {diff.old_root_url} -> {diff.new_root_url}"]

    if diff.added_pages:
        lines.append(f"\nAdded pages ({len(diff.added_pages)}):")
        lines.extend(f"  + {url}" for url in diff.added_pages)

    if diff.removed_pages:
        lines.append(f"\nRemoved pages ({len(diff.removed_pages)}):")
        lines.extend(f"  - {url}" for url in diff.removed_pages)

    if diff.changed_pages:
        lines.append(f"\nChanged pages ({len(diff.changed_pages)}):")
        for page_diff in diff.changed_pages:
            lines.append(f"  ~ {page_diff.url}")
            for node in page_diff.added_elements:
                lines.append(f"      + element {node.identity_key} (<{node.tag}>)")
            for node in page_diff.removed_elements:
                lines.append(f"      - element {node.identity_key} (<{node.tag}>)")
            for change in page_diff.changed_elements:
                for fc in change.field_changes:
                    lines.append(f"      ~ element {change.identity_key}: {fc.field} {fc.old!r} -> {fc.new!r}")
            for rec in page_diff.added_recommendations:
                lines.append(f"      + recommendation {rec.event_name} via {rec.selector}")
            for rec in page_diff.removed_recommendations:
                lines.append(f"      - recommendation {rec.event_name} via {rec.selector}")

    lines.append(
        f"\n{diff.unchanged_page_count} unchanged page(s), "
        f"{len(diff.changed_pages)} changed page(s), "
        f"{len(diff.added_pages)} added, {len(diff.removed_pages)} removed."
    )

    return "\n".join(lines)
