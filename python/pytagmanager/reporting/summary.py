"""Shared health-summary computation used by both the terminal and JSON
reporters (spec section 10) so the two output formats never disagree about
counts. Every metric here is derived from what was actually observed --
none are invented placeholders.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

from pytagmanager.correlation.journey import TrackingJourney
from pytagmanager.recommend.models import TrackingRecommendation

_DUPLICATE_ROOT_CAUSES = {"duplicate_analytics_request", "duplicate_datalayer_event"}


@dataclass(frozen=True)
class HealthSummary:
    pages_tested: int
    journeys_total: int
    healthy: int
    warnings: int
    critical: int
    event_coverage: float  # tested candidates / (tested + untested)
    duplicate_rate: float  # journeys with a duplicate-* root cause / total journeys
    missing_event_rate: float  # journeys with missing_datalayer_event root cause / total journeys


def compute_health_summary(
    journeys: List[TrackingJourney],
    untested: Optional[List[TrackingRecommendation]] = None,
) -> HealthSummary:
    untested = untested or []
    pages_tested = len({obs.page_url for journey in journeys for obs in journey.observations if obs.page_url})
    healthy = sum(1 for j in journeys if j.status == "healthy")
    warnings = sum(1 for j in journeys if j.status == "warning")
    critical = sum(1 for j in journeys if j.status == "critical")
    total = len(journeys)

    duplicates = sum(1 for j in journeys if j.diagnosis and j.diagnosis.root_cause in _DUPLICATE_ROOT_CAUSES)
    missing = sum(1 for j in journeys if j.diagnosis and j.diagnosis.root_cause == "missing_datalayer_event")

    tested_count = total
    coverage_denominator = tested_count + len(untested)
    event_coverage = (tested_count / coverage_denominator) if coverage_denominator else 0.0

    return HealthSummary(
        pages_tested=pages_tested,
        journeys_total=total,
        healthy=healthy,
        warnings=warnings,
        critical=critical,
        event_coverage=event_coverage,
        duplicate_rate=(duplicates / total) if total else 0.0,
        missing_event_rate=(missing / total) if total else 0.0,
    )
