"""Statistical anomaly detection across a site-wide crawl (spec section 16):
outliers *within* an otherwise-passing population, distinct from
`aggregation.analyze_template_consistency`'s pass/fail-rate regressions.

Two checks, both computed relative to a template's own observed norm (never
a hardcoded threshold, since "normal" varies per site):

1. **Unusual event repetition** -- a page firing the same business event far
   more often than its template's average (e.g. one page generating 4x the
   template's normal `page_view` count).
2. **Config drift** -- a page whose GTM container ID or GA4 measurement ID
   (parsed from the `gtm.js`/collect request URLs already observed) differs
   from what the rest of its template uses.

Both require at least two pages with a signal to compute a norm against;
a single data point can't be judged anomalous relative to itself.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional

from pytagmanager.correlation.journey import TrackingJourney
from pytagmanager.sitewide.templates import PageTemplate

_REPETITION_MULTIPLIER = 3.0  # a page must fire an event at least this many times the template average to flag


@dataclass(frozen=True)
class Anomaly:
    kind: str  # "unusual_event_repetition" | "config_drift"
    message: str
    page_url: str
    details: Dict[str, object] = field(default_factory=dict)


def _extract_gtm_container_id(journey: TrackingJourney) -> Optional[str]:
    for request in journey.events_of_type("network_request"):
        if "gtm.js" in request.payload.get("url", ""):
            container_id = request.payload.get("params", {}).get("id")
            if container_id:
                return container_id
    return None


def _extract_measurement_id(journey: TrackingJourney) -> Optional[str]:
    for request in journey.events_of_type("network_request"):
        measurement_id = request.payload.get("params", {}).get("tid")
        if measurement_id:
            return measurement_id
    return None


def _detect_event_repetition_anomalies(
    template: PageTemplate,
    journeys_by_page: Dict[str, List[TrackingJourney]],
) -> List[Anomaly]:
    counts_by_page: Dict[str, Dict[str, int]] = {}
    for url in template.page_urls:
        counts: Dict[str, int] = {}
        for journey in journeys_by_page.get(url, []):
            counts[journey.business_event] = counts.get(journey.business_event, 0) + 1
        counts_by_page[url] = counts

    event_names = {name for counts in counts_by_page.values() for name in counts}
    anomalies = []
    for event_name in sorted(event_names):
        per_page_counts = {url: counts.get(event_name, 0) for url, counts in counts_by_page.items()}
        nonzero = [count for count in per_page_counts.values() if count > 0]
        if len(nonzero) < 2:
            continue  # need at least 2 data points to have a norm to deviate from
        average = sum(nonzero) / len(nonzero)
        threshold = max(3, average * _REPETITION_MULTIPLIER)
        for url, count in per_page_counts.items():
            if count >= threshold:
                anomalies.append(
                    Anomaly(
                        kind="unusual_event_repetition",
                        message=(
                            f"'{event_name}' fired {count} times on this page, "
                            f"vs. a {template.label} template average of {average:.1f}."
                        ),
                        page_url=url,
                        details={"event_name": event_name, "count": count, "template_average": round(average, 2)},
                    )
                )
    return anomalies


def _detect_config_drift(
    template: PageTemplate,
    journeys_by_page: Dict[str, List[TrackingJourney]],
    extractor: Callable[[TrackingJourney], Optional[str]],
    label: str,
) -> List[Anomaly]:
    ids_by_page: Dict[str, set] = {
        url: {extractor(journey) for journey in journeys_by_page.get(url, []) if extractor(journey)}
        for url in template.page_urls
    }
    all_ids = [value for ids in ids_by_page.values() for value in ids]
    if len(set(all_ids)) < 2:
        return []  # everyone agrees (or nobody has data) -- nothing to flag

    majority_id, _ = Counter(all_ids).most_common(1)[0]
    return [
        Anomaly(
            kind="config_drift",
            message=(
                f"This page uses a different {label} ({', '.join(sorted(ids))}) "
                f"than the {template.label} template's typical '{majority_id}'."
            ),
            page_url=url,
            details={"label": label, "observed": sorted(ids), "expected": majority_id},
        )
        for url, ids in ids_by_page.items()
        if ids and majority_id not in ids
    ]


def detect_template_anomalies(
    template: PageTemplate,
    journeys_by_page: Dict[str, List[TrackingJourney]],
) -> List[Anomaly]:
    return [
        *_detect_event_repetition_anomalies(template, journeys_by_page),
        *_detect_config_drift(template, journeys_by_page, _extract_gtm_container_id, "GTM container"),
        *_detect_config_drift(template, journeys_by_page, _extract_measurement_id, "GA4 measurement ID"),
    ]


def detect_site_anomalies(
    templates: List[PageTemplate],
    journeys_by_page: Dict[str, List[TrackingJourney]],
) -> List[Anomaly]:
    return [anomaly for template in templates for anomaly in detect_template_anomalies(template, journeys_by_page)]
