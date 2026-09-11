"""Cross-page consistency for the *same business action* (docs/VISION.md
§14, Phase 1.8) -- a different cut from `sitewide/aggregation.py`'s
template consistency, which asks "does this template's own event fire
consistently across its own pages." This asks: does "Add to Cart" fire the
same event shape everywhere it appears on the site, regardless of which
page template implements it -- product page, quick-view, search results,
a recommendation widget? Four different implementations of the same
business interaction is a real tagging-quality finding template-scoped
consistency checks structurally can't see, since each implementation may
live in a different template.

Grouped by `TrackingRecommendation.business_objective` (the same
deterministic taxonomy `recommend.heuristics` already assigns, e.g.
"Purchase Intent") rather than by the *observed* event name, since the
whole point is comparing what different pages call the same underlying
business action -- grouping by observed name would trivially never find
a naming inconsistency.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Tuple

from pytagmanager.correlation.journey import TrackingJourney
from pytagmanager.recommend.models import TrackingRecommendation

# A journey is only counted as "fired" for this business action if it
# reached the datalayer or gtm stage -- matching _infer_business_event's
# own definition of a real business_event, not its synthetic
# "click:selector" fallback name for an interaction that produced nothing.
_FIRED_STAGES = ("datalayer", "gtm")


@dataclass(frozen=True)
class BusinessActionImplementation:
    """One observed instance of a business action being tested somewhere
    on the site: which page/selector tested it, and what actually fired."""

    page_url: str
    selector: str
    observed_event_name: str  # "" if tested but nothing fired at the datalayer/gtm stage
    fired: bool


@dataclass(frozen=True)
class BusinessActionConsistencyReport:
    business_objective: str
    implementations: Tuple[BusinessActionImplementation, ...] = field(default_factory=tuple)

    @property
    def distinct_event_names(self) -> List[str]:
        names = {impl.observed_event_name for impl in self.implementations if impl.fired}
        return sorted(names)

    @property
    def fired_count(self) -> int:
        return sum(1 for impl in self.implementations if impl.fired)

    @property
    def untested_or_silent_count(self) -> int:
        return len(self.implementations) - self.fired_count

    @property
    def is_consistent(self) -> bool:
        """True unless at least two implementations of this business
        action fired *different* event names. Implementations that never
        fired at all are surfaced via `untested_or_silent_count`, not
        folded into this verdict -- that's already
        `diagnostics.rules.find_untested_recommendations`'s job; this
        report's unique contribution is naming/shape drift among the ones
        that did fire.
        """
        return len(self.distinct_event_names) <= 1


def analyze_business_action_consistency(
    recs_by_page: Dict[str, List[TrackingRecommendation]],
    journeys: List[TrackingJourney],
) -> List[BusinessActionConsistencyReport]:
    """`recs_by_page` is page_url -> the static `TrackingRecommendation`s
    detected for it (what `diagnose`'s crawl loop already builds per page);
    `journeys` is every `TrackingJourney` observed across the whole crawl.

    A journey is matched to the recommendation that produced it by
    (page_url, selector) -- the same join key
    `diagnostics.rules.find_untested_recommendations` already uses
    (`journey.anchor_selector` vs `rec.selector`), just applied across
    pages instead of within one.

    Only business actions tested via more than one recommendation/selector
    are returned -- one implementation has nothing to be inconsistent
    *with*.
    """
    journey_by_page_selector: Dict[Tuple[str, str], TrackingJourney] = {}
    for journey in journeys:
        if not journey.observations:
            continue
        page_url = journey.observations[0].page_url
        selector = journey.anchor_selector
        if selector:
            journey_by_page_selector[(page_url, selector)] = journey

    grouped: Dict[str, List[BusinessActionImplementation]] = {}
    for page_url, recs in recs_by_page.items():
        for rec in recs:
            journey = journey_by_page_selector.get((page_url, rec.selector))
            fired = bool(journey) and any(journey.stage_present(stage) for stage in _FIRED_STAGES)
            grouped.setdefault(rec.business_objective, []).append(
                BusinessActionImplementation(
                    page_url=page_url,
                    selector=rec.selector,
                    observed_event_name=journey.business_event if fired else "",
                    fired=fired,
                )
            )

    return [
        BusinessActionConsistencyReport(business_objective=objective, implementations=tuple(implementations))
        for objective, implementations in sorted(grouped.items())
        if len(implementations) > 1
    ]
