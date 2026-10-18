"""Dry-run planner for importing a generated GTM container export.

PyTagManager can generate a container JSON for recommendations, but importing
it into GTM is still a manual step. This planner compares the generated
resources (tags/triggers/variables) with the live container and reports what
would be created, what already exists, and what conflicts by name/type. It does
not write to GTM.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Tuple


@dataclass
class GtmResourcePlan:
    added: List[Dict[str, str]] = field(default_factory=list)
    existing: List[Dict[str, str]] = field(default_factory=list)
    conflicts: List[Dict[str, str]] = field(default_factory=list)


@dataclass
class GtmImportPlan:
    tags: GtmResourcePlan = field(default_factory=GtmResourcePlan)
    triggers: GtmResourcePlan = field(default_factory=GtmResourcePlan)
    variables: GtmResourcePlan = field(default_factory=GtmResourcePlan)

    @property
    def has_conflicts(self) -> bool:
        return bool(self.tags.conflicts or self.triggers.conflicts or self.variables.conflicts)

    def to_dict(self) -> Dict[str, Any]:
        def dump(plan: GtmResourcePlan) -> Dict[str, Any]:
            return {
                "added": plan.added,
                "existing": plan.existing,
                "conflicts": plan.conflicts,
            }

        return {
            "has_conflicts": self.has_conflicts,
            "tags": dump(self.tags),
            "triggers": dump(self.triggers),
            "variables": dump(self.variables),
        }


def _container_version(document: Dict[str, Any]) -> Dict[str, Any]:
    version = document.get("containerVersion")
    return version if isinstance(version, dict) else document


def _resources(document: Dict[str, Any], key: str) -> Dict[str, Dict[str, Any]]:
    version = _container_version(document)
    values = version.get(key) or []
    result: Dict[str, Dict[str, Any]] = {}
    for value in values:
        if isinstance(value, dict) and isinstance(value.get("name"), str):
            result[value["name"]] = value
    return result


def _plan(generated: Dict[str, Dict[str, Any]], live: Dict[str, Dict[str, Any]]) -> GtmResourcePlan:
    plan = GtmResourcePlan()
    for name, resource in sorted(generated.items()):
        existing = live.get(name)
        row = {"name": name, "type": str(resource.get("type", ""))}
        if existing is None:
            plan.added.append(row)
        elif str(existing.get("type", "")) != row["type"]:
            plan.conflicts.append(
                {
                    **row,
                    "existing_type": str(existing.get("type", "")),
                    "reason": "same name, different resource type",
                }
            )
        else:
            plan.existing.append(row)
    return plan


def plan_import(generated: Dict[str, Any], live: Dict[str, Any]) -> GtmImportPlan:
    """Compare generated vs live GTM resources. No network or writes."""
    return GtmImportPlan(
        tags=_plan(_resources(generated, "tag"), _resources(live, "tag")),
        triggers=_plan(_resources(generated, "trigger"), _resources(live, "trigger")),
        variables=_plan(_resources(generated, "variable"), _resources(live, "variable")),
    )


def render_plan(plan: GtmImportPlan) -> str:
    lines = ["PyTagManager GTM import plan (dry run)", "=" * 38, ""]

    def render(kind: str, resource: GtmResourcePlan) -> None:
        lines.append(
            f"{kind}: {len(resource.added)} add, {len(resource.existing)} existing, "
            f"{len(resource.conflicts)} conflict(s)"
        )
        for row in resource.added:
            lines.append(f"  + {row['name']} ({row['type']})")
        for row in resource.conflicts:
            lines.append(
                f"  ! {row['name']} ({row['type']} -> existing {row['existing_type']}): {row['reason']}"
            )
        lines.append("")

    render("Tags", plan.tags)
    render("Triggers", plan.triggers)
    render("Variables", plan.variables)
    if plan.has_conflicts:
        lines.append("Resolve conflicts by renaming or updating the existing GTM resource before importing.")
    return "\n".join(lines).rstrip()
