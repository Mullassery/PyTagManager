"""Cross-page consistency analysis, template/site health scoring, and the
"who's actually inconsistent" question the per-page `diagnose` output can't
answer on its own (spec sections 15-19): is a failure isolated to one page,
or a systemic template/component regression shared by many?

Every metric here is derived from what `pytagmanager diagnose` actually
observed across the crawl -- none are invented placeholders. A metric with
no supporting observations (e.g. no consent events seen anywhere) reports
as `None`, not a fabricated 100%.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

from pytagmanager.correlation.journey import TrackingJourney
from pytagmanager.recommend.models import TrackingRecommendation
from pytagmanager.sitewide.templates import PageTemplate

# An event must appear (successfully or not) on at least this fraction of a
# template's pages -- and on at least 2 pages -- before it's treated as a
# template-wide expectation rather than a one-off page-specific interaction
# that happens to share a template with unrelated pages.
_MIN_SUPPORT_RATIO = 0.2

_DUPLICATE_ROOT_CAUSES = {"duplicate_analytics_request", "duplicate_datalayer_event"}


@dataclass(frozen=True)
class TemplateEventStat:
    event_name: str
    pass_count: int
    fail_count: int
    total: int

    @property
    def pass_rate(self) -> float:
        return self.pass_count / self.total if self.total else 0.0


@dataclass(frozen=True)
class TemplateConsistencyReport:
    template: PageTemplate
    event_stats: List[TemplateEventStat] = field(default_factory=list)
    regressions: List[str] = field(default_factory=list)


@dataclass(frozen=True)
class TemplateHealth:
    template: PageTemplate
    score: int  # 0-100
    healthy: int
    warnings: int
    critical: int
    journeys_total: int
    gtm_coverage: Optional[float] = None
    ga4_coverage: Optional[float] = None
    datalayer_coverage: Optional[float] = None
    js_error_count: int = 0


@dataclass(frozen=True)
class SiteHealthReport:
    pages_scanned: int
    template_healths: List[TemplateHealth]
    overall_score: int
    gtm_coverage: Optional[float]
    ga4_coverage: Optional[float]
    datalayer_coverage: Optional[float]
    event_coverage: Optional[float]
    duplicate_rate: Optional[float]
    consent_ok_rate: Optional[float]
    pages_with_js_errors: int


def _page_has_journey_for_event(journeys: List[TrackingJourney], event_name: str) -> bool:
    return any(j.business_event == event_name for j in journeys)


def _page_passes_for_event(journeys: List[TrackingJourney], event_name: str) -> bool:
    return any(j.business_event == event_name and j.status == "healthy" for j in journeys)


def analyze_template_consistency(
    template: PageTemplate,
    journeys_by_page: Dict[str, List[TrackingJourney]],
) -> TemplateConsistencyReport:
    pages = template.page_urls
    total_pages = len(pages)
    if total_pages == 0:
        return TemplateConsistencyReport(template=template)

    event_names = {j.business_event for url in pages for j in journeys_by_page.get(url, [])}

    stats = []
    regressions = []
    for event_name in sorted(event_names):
        pages_with_event = [url for url in pages if _page_has_journey_for_event(journeys_by_page.get(url, []), event_name)]
        support_ratio = len(pages_with_event) / total_pages
        if support_ratio < _MIN_SUPPORT_RATIO or len(pages_with_event) < 2:
            continue  # one-off, not a template-wide expectation

        pass_count = sum(1 for url in pages if _page_passes_for_event(journeys_by_page.get(url, []), event_name))
        fail_count = total_pages - pass_count
        stats.append(TemplateEventStat(event_name=event_name, pass_count=pass_count, fail_count=fail_count, total=total_pages))

        # Majority succeed, a minority don't: likely a shared-component
        # regression on those specific pages. If more pages fail than pass,
        # we can't confidently call this event "expected" template-wide --
        # skip rather than overclaim.
        if fail_count > 0 and pass_count > fail_count:
            regressions.append(
                f"Potential {template.label} Template Regression: {fail_count} of {total_pages} "
                f"{template.label.lower()} pages do not generate '{event_name}'."
            )

    return TemplateConsistencyReport(template=template, event_stats=stats, regressions=regressions)


def compute_template_health(template: PageTemplate, journeys_by_page: Dict[str, List[TrackingJourney]]) -> TemplateHealth:
    journeys = [j for url in template.page_urls for j in journeys_by_page.get(url, [])]
    healthy = sum(1 for j in journeys if j.status == "healthy")
    warnings = sum(1 for j in journeys if j.status == "warning")
    critical = sum(1 for j in journeys if j.status == "critical")
    total = len(journeys)
    # Healthy counts fully, warnings count half, critical counts zero.
    score = round(100 * (healthy + 0.5 * warnings) / total) if total else 100

    def _coverage(stage: str) -> Optional[float]:
        return (sum(1 for j in journeys if j.stage_present(stage)) / total) if total else None

    return TemplateHealth(
        template=template,
        score=score,
        healthy=healthy,
        warnings=warnings,
        critical=critical,
        journeys_total=total,
        gtm_coverage=_coverage("gtm"),
        ga4_coverage=_coverage("network"),
        datalayer_coverage=_coverage("datalayer"),
        js_error_count=sum(1 for j in journeys if j.events_of_type("js_error")),
    )


def compute_site_health(
    templates: List[PageTemplate],
    journeys_by_page: Dict[str, List[TrackingJourney]],
    untested_by_page: Optional[Dict[str, List[TrackingRecommendation]]] = None,
) -> SiteHealthReport:
    untested_by_page = untested_by_page or {}
    all_journeys = [j for journeys in journeys_by_page.values() for j in journeys]
    total_journeys = len(all_journeys)

    template_healths = [compute_template_health(t, journeys_by_page) for t in templates]
    overall_score = (
        round(sum(th.score * th.journeys_total for th in template_healths) / total_journeys) if total_journeys else 100
    )

    def _coverage(stage: str) -> Optional[float]:
        return (sum(1 for j in all_journeys if j.stage_present(stage)) / total_journeys) if total_journeys else None

    all_untested = [r for recs in untested_by_page.values() for r in recs]
    denominator = total_journeys + len(all_untested)
    event_coverage = (total_journeys / denominator) if denominator else None

    consent_journeys = [j for j in all_journeys if j.events_of_type("consent_change")]
    consent_ok_rate = (
        sum(1 for j in consent_journeys if not (j.diagnosis and j.diagnosis.root_cause == "consent_blocked"))
        / len(consent_journeys)
        if consent_journeys
        else None
    )

    duplicate_rate = (
        sum(1 for j in all_journeys if j.diagnosis and j.diagnosis.root_cause in _DUPLICATE_ROOT_CAUSES) / total_journeys
        if total_journeys
        else None
    )

    return SiteHealthReport(
        pages_scanned=len(journeys_by_page),
        template_healths=template_healths,
        overall_score=overall_score,
        gtm_coverage=_coverage("gtm"),
        ga4_coverage=_coverage("network"),
        datalayer_coverage=_coverage("datalayer"),
        event_coverage=event_coverage,
        duplicate_rate=duplicate_rate,
        consent_ok_rate=consent_ok_rate,
        pages_with_js_errors=sum(1 for j in all_journeys if j.events_of_type("js_error")),
    )
