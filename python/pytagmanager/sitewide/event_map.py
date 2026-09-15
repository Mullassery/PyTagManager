"""Runtime Event Map (docs/VISION.md §14, Phase 1.8 item 5): one matrix,
interaction x {JS, dataLayer, Network, GTM}, site-wide -- alongside, not
replacing, `sitewide/aggregation.py`'s existing per-template health
matrix. That matrix answers "is this template healthy"; this one answers
"for this specific interaction, wherever it happens on the site, which
stages of the tracking chain actually fired."

Mostly a presentation layer over what `TrackingJourney` already carries
(`STAGES`/`stage_present()`), not new capture logic -- grouped by
`business_event` (the journey's own inferred event name) rather than by
page/template, since the point of this matrix is a site-wide view per
interaction, not per page.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List

from pytagmanager.correlation.journey import TrackingJourney

# The four VISION.md §14 columns, mapped onto TrackingJourney.STAGES:
# "JS" -> DOM mutation observed (the JS runtime actually did something
# visible), "Network" -> the analytics request stage. "interaction" and
# "application" stages aren't part of this matrix -- they describe the
# trigger itself and app-internal API calls, not the tracking chain.
_COLUMNS = (("js", "mutation"), ("datalayer", "datalayer"), ("network", "network"), ("gtm", "gtm"))


@dataclass(frozen=True)
class RuntimeEventMapRow:
    business_event: str
    journeys_total: int
    js_coverage: float
    datalayer_coverage: float
    network_coverage: float
    gtm_coverage: float

    @property
    def stage_coverage(self) -> Dict[str, float]:
        return {
            "js": self.js_coverage,
            "datalayer": self.datalayer_coverage,
            "network": self.network_coverage,
            "gtm": self.gtm_coverage,
        }


def build_runtime_event_map(journeys: List[TrackingJourney]) -> List[RuntimeEventMapRow]:
    grouped: Dict[str, List[TrackingJourney]] = {}
    for journey in journeys:
        grouped.setdefault(journey.business_event, []).append(journey)

    rows = []
    for business_event, group in sorted(grouped.items()):
        total = len(group)
        coverage = {
            column: sum(1 for j in group if j.stage_present(stage)) / total for column, stage in _COLUMNS
        }
        rows.append(
            RuntimeEventMapRow(
                business_event=business_event,
                journeys_total=total,
                js_coverage=coverage["js"],
                datalayer_coverage=coverage["datalayer"],
                network_coverage=coverage["network"],
                gtm_coverage=coverage["gtm"],
            )
        )
    return rows
