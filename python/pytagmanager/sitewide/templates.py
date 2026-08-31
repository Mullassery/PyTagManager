"""Page-type/template detection for site-wide grouping (spec section 14).

Clusters crawled pages into logical templates (Homepage, Product, Cart,
...) so `sitewide.aggregation` can distinguish "this one page is broken"
from "this template/component version is broken across 51 pages" instead
of treating every crawled page as an independent, unrelated data point.

This is a heuristic, not ground truth: it exists to group *likely*-related
pages for cross-page consistency reporting, not to authoritatively name a
site's information architecture. Two signals, in priority order:

1. URL path pattern -- numeric/UUID/slug segments generalized to a
   placeholder (`/products/123` and `/products/456` -> `/products/{param}`).
2. DOM class-fingerprint similarity -- merges groups that share a
   structure (same "template" classes) but whose URLs don't reveal it
   (e.g. `/deals` and `/new-arrivals` both rendering the same component).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Sequence
from urllib.parse import urlparse

_ID_LIKE = re.compile(
    r"^[0-9]+$|^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$|^[0-9a-f]{12,}$",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class PageTemplate:
    template_id: str
    label: str
    page_urls: List[str] = field(default_factory=list)


def _is_dynamic_segment(segment: str, is_last: bool, depth: int) -> bool:
    if _ID_LIKE.match(segment):
        return True
    # A deep path's final segment (e.g. /products/blue-running-shoes) is
    # usually a per-item slug even without digits -- but only past depth 1,
    # so top-level static pages like /cart or /about aren't misclassified.
    return bool(is_last and depth >= 2 and "-" in segment)


def url_template(url: str) -> str:
    path = urlparse(url).path.strip("/")
    if not path:
        return "/"
    segments = path.split("/")
    templated = [
        "{param}" if _is_dynamic_segment(seg, i == len(segments) - 1, len(segments)) else seg
        for i, seg in enumerate(segments)
    ]
    return "/" + "/".join(templated)


def dom_fingerprint(graph: Any) -> frozenset:
    """CSS classes appearing on >= 2 elements -- "template/component"
    classes, filtering out one-off content classes that wouldn't recur
    across pages sharing the same template."""
    class_counts: Dict[str, int] = {}
    for node in graph.nodes:
        for cls in node.classes:
            class_counts[cls] = class_counts.get(cls, 0) + 1
    return frozenset(cls for cls, count in class_counts.items() if count >= 2)


def _jaccard(a: frozenset, b: frozenset) -> float:
    # Two empty fingerprints are an absence of evidence, not evidence of
    # similarity -- treat as dissimilar so pages with no repeated-class
    # signal (e.g. sparse fixtures/tests) don't spuriously merge.
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def _label_for(template_key: str) -> str:
    if template_key == "/":
        return "Homepage"
    segments = [s for s in template_key.strip("/").split("/") if s and s != "{param}"]
    if not segments:
        return "Homepage"
    return segments[0].replace("-", " ").replace("_", " ").title()


def detect_templates(pages: Sequence[Any], similarity_threshold: float = 0.6) -> List[PageTemplate]:
    """`pages` is whatever `discovery.crawl_site()` returns (real
    `_core.Page` objects, or anything duck-typing `.url`/`.graph.nodes`).
    Returns templates ordered largest-first.
    """
    groups: Dict[str, List[Any]] = {}
    for page in pages:
        groups.setdefault(url_template(page.url), []).append(page)

    fingerprints = {key: dom_fingerprint(group[0].graph) for key, group in groups.items()}
    merged_into: Dict[str, str] = {key: key for key in groups}
    keys = list(groups.keys())
    for i in range(len(keys)):
        for j in range(i + 1, len(keys)):
            a, b = keys[i], keys[j]
            if merged_into[a] == merged_into[b]:
                continue
            if _jaccard(fingerprints[a], fingerprints[b]) >= similarity_threshold:
                target, source = merged_into[a], merged_into[b]
                for key in merged_into:
                    if merged_into[key] == source:
                        merged_into[key] = target

    final_groups: Dict[str, List[Any]] = {}
    for key, group in groups.items():
        final_groups.setdefault(merged_into[key], []).extend(group)

    ordered = sorted(final_groups.items(), key=lambda kv: -len(kv[1]))
    return [
        PageTemplate(template_id=f"template_{i + 1}", label=_label_for(key), page_urls=[p.url for p in group])
        for i, (key, group) in enumerate(ordered)
    ]
