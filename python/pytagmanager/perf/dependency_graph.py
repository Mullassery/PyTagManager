"""Script dependency graph (docs/VISION.md §16, Phase 1.95 item 3):
script -> script relationships built from `perf/scripts.py`'s CDP-sourced
initiator data, so an isolation experiment (item 4) that blocks one script
can know everything downstream of it -- disabling GTM, for example,
should account for GA4/Meta Pixel/Floodlight/Hotjar it loads, not treat
their absence as separate, uncounted savings or double-count them against
GTM's own cost.

A script whose `initiator_type` is `"script"` is parented to the script
that triggered it (`initiator_url`, from CDP's `initiator.stack`); every
other script (`"parser"`, `"other"`, or a `"script"` initiator with no
resolvable URL -- e.g. an inline `<script>` block, which has no `src` and
so never appears as its own node in the inventory) is parented to the
page itself. This mirrors reality: a `<script src>` tag the HTML parser
discovered directly, or a request an inline script issued, both have the
document as their real root -- not a fabricated intermediate node.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from pytagmanager.perf.scripts import ScriptInventory

RELATIONSHIP_LOADED_BY_SCRIPT = "loaded_by_script"
RELATIONSHIP_LOADED_BY_PARSER = "loaded_by_parser"
RELATIONSHIP_LOADED_BY_OTHER = "loaded_by_other"


@dataclass(frozen=True)
class DependencyEdge:
    parent_url: str  # the initiating script's URL, or the page's own URL when not script-initiated
    child_url: str
    relationship: str


@dataclass(frozen=True)
class ScriptDependencyGraph:
    page_url: str
    edges: tuple[DependencyEdge, ...] = field(default_factory=tuple)

    def children_of(self, url: str) -> tuple[str, ...]:
        return tuple(sorted({e.child_url for e in self.edges if e.parent_url == url}))

    def downstream_of(self, url: str) -> frozenset[str]:
        """Transitive closure: every script that would stop loading if
        `url` were blocked -- direct children plus their children,
        recursively. This is the data an isolation experiment needs to
        avoid double-counting or missing downstream savings when it
        blocks one script."""
        children_by_parent: dict[str, list[str]] = {}
        for edge in self.edges:
            children_by_parent.setdefault(edge.parent_url, []).append(edge.child_url)

        visited: set[str] = set()
        frontier = list(children_by_parent.get(url, []))
        while frontier:
            child = frontier.pop()
            if child in visited:
                continue
            visited.add(child)
            frontier.extend(children_by_parent.get(child, []))
        return frozenset(visited)


def build_dependency_graph(inventory: ScriptInventory) -> ScriptDependencyGraph:
    edges = []
    for script in inventory.scripts:
        if script.initiator_type == "script" and script.initiator_url:
            parent, relationship = script.initiator_url, RELATIONSHIP_LOADED_BY_SCRIPT
        elif script.initiator_type == "parser":
            parent, relationship = inventory.page_url, RELATIONSHIP_LOADED_BY_PARSER
        else:
            parent, relationship = inventory.page_url, RELATIONSHIP_LOADED_BY_OTHER
        edges.append(
            DependencyEdge(parent_url=parent, child_url=script.url, relationship=relationship)
        )
    return ScriptDependencyGraph(page_url=inventory.page_url, edges=tuple(edges))
