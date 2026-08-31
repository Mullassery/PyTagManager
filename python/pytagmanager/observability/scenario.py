"""Tracking-journey test scenarios (spec section 12): named sequences of
browser actions plus the tracking behavior expected to result from them.

A `Scenario` is the explicit, hand-authored counterpart to
`auto_scenario_from_recommendations()`, which derives the same shape
automatically from `recommend.recommend_for_graph()`'s static analysis --
this is the "scan the site" default path `diagnose` uses when the caller
doesn't supply `--scenario`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import List

import yaml

from pytagmanager.recommend.models import TrackingRecommendation

ACTIONS = frozenset({"click", "change", "submit"})
# "datalayer_event" is a hand-authored, exact-name assertion (the caller
# knows what the site is supposed to push). "any_datalayer_event" is the
# weaker claim auto_scenario_from_recommendations() below makes: recommend
# .heuristics invents a generic label like "purchase_intent" for a CTA,
# which is PyTagManager's own taxonomy, not a prediction of what name a
# real site will actually push -- asserting an exact match there would
# flag "event_name_mismatch" on essentially every real site.
EXPECTATION_KINDS = frozenset({"datalayer_event", "any_datalayer_event", "gtm_tag", "analytics_event"})


@dataclass(frozen=True)
class ActionStep:
    action: str  # one of ACTIONS
    selector: str
    value: str = ""  # only meaningful for action == "change"


@dataclass(frozen=True)
class Expectation:
    kind: str  # one of EXPECTATION_KINDS
    value: str


@dataclass(frozen=True)
class Scenario:
    name: str
    steps: List[ActionStep] = field(default_factory=list)
    expectations: List[Expectation] = field(default_factory=list)
    business_event: str = ""

    @classmethod
    def from_dict(cls, data: dict) -> "Scenario":
        journey = data.get("journey", data)
        steps: List[ActionStep] = []
        expectations: List[Expectation] = []
        for raw_step in journey.get("steps", []):
            if "action" in raw_step:
                steps.append(
                    ActionStep(
                        action=raw_step["action"],
                        selector=raw_step["selector"],
                        value=raw_step.get("value", ""),
                    )
                )
            elif "expect" in raw_step:
                for kind, value in raw_step["expect"].items():
                    expectations.append(Expectation(kind=kind, value=value))
        return cls(
            name=journey["name"],
            steps=steps,
            expectations=expectations,
            business_event=journey.get("business_event", journey["name"]),
        )


def load_scenario(path: str) -> Scenario:
    data = yaml.safe_load(Path(path).read_text())
    return Scenario.from_dict(data)


def load_scenarios_dir(path: str) -> List[Scenario]:
    return [load_scenario(str(p)) for p in sorted(Path(path).glob("*.yml")) + sorted(Path(path).glob("*.yaml"))]


def auto_scenario_from_recommendations(
    recommendations: List[TrackingRecommendation],
    page_url: str = "",
) -> List[Scenario]:
    """Build one Scenario per statically-detected `TrackingRecommendation`
    (recommend.recommend_for_graph output) so `diagnose` can verify runtime
    behavior for a page without requiring a hand-authored journey file --
    this is the crawl-and-verify default path.

    Uses `any_datalayer_event`, not `datalayer_event`: `rec.event_name` is
    a label recommend.heuristics invented (e.g. "purchase_intent"), not a
    prediction of the literal event name a real site pushes (which is
    almost always something else, e.g. "add_to_cart"). The claim this
    scenario makes is "clicking this recommended element should produce
    *some* dataLayer event," not "...an event with exactly this name" --
    the latter would falsely flag a mismatch on essentially every real site.
    """
    scenarios = []
    for rec in recommendations:
        action = "submit" if rec.trigger_type == "submit" else "click"
        scenarios.append(
            Scenario(
                name=f"{rec.event_name} @ {rec.selector}",
                steps=[ActionStep(action=action, selector=rec.selector)],
                expectations=[Expectation(kind="any_datalayer_event", value=rec.event_name)],
                business_event=rec.event_name,
            )
        )
    return scenarios
