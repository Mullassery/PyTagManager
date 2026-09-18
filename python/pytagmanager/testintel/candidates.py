"""Test Candidates (docs/VISION.md §15, Phase 1.9): turn Phase 1.5/1.8's
findings into structured, evidence-backed hypotheses an engineer reviews
before formalizing as a real Playwright test -- never an assertion this
product makes on its own authority.

**The severity scale is deliberately capped below "Confirmed defect".**
`SEVERITY_LEVELS` is VISION's own refinement of `Diagnosis.confidence`'s
existing scale (Observed → Potential issue → Suspected defect → Requires
verification → Confirmed defect), but this module's generators never
produce "Confirmed defect" -- "the product never self-certifies a finding
as a confirmed defect" (§15). The strongest a generated candidate ever
gets is "Requires verification": a human or a real Playwright run is what
actually confirms a defect, not this module.

**Categories** mirror §15's list exactly. Two of the nine
(`data_type`, `storage_behavior`) have no generator in this pass -- no
existing rule in `diagnostics/rules.py` currently detects a data-type
mismatch or a missing storage-side-effect, so nothing is fabricated for
them. `event_payload`/`event_existence`/`network_transmission`/
`consent_behavior`/`timing` are generated from `Diagnosis` root causes
(`generate_diagnosis_candidates`), `consistency` from cross-page business-
action naming drift (`generate_consistency_candidates`), and `regression`
from Website Data Dictionary schema drift (`testintel.regression`, item 3).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Sequence, Tuple

from pytagmanager.correlation.journey import TrackingJourney
from pytagmanager.diagnostics.models import CONFIDENCE_LEVELS
from pytagmanager.sitewide.interaction_consistency import BusinessActionConsistencyReport

CATEGORY_EVENT_EXISTENCE = "event_existence"
CATEGORY_EVENT_PAYLOAD = "event_payload"
CATEGORY_DATA_TYPE = "data_type"
CATEGORY_TIMING = "timing"
CATEGORY_CONSISTENCY = "consistency"
CATEGORY_NETWORK_TRANSMISSION = "network_transmission"
CATEGORY_STORAGE_BEHAVIOR = "storage_behavior"
CATEGORY_CONSENT_BEHAVIOR = "consent_behavior"
CATEGORY_REGRESSION = "regression"

CATEGORIES = (
    CATEGORY_EVENT_EXISTENCE,
    CATEGORY_EVENT_PAYLOAD,
    CATEGORY_DATA_TYPE,
    CATEGORY_TIMING,
    CATEGORY_CONSISTENCY,
    CATEGORY_NETWORK_TRANSMISSION,
    CATEGORY_STORAGE_BEHAVIOR,
    CATEGORY_CONSENT_BEHAVIOR,
    CATEGORY_REGRESSION,
)

# VISION.md §15's refined scale. Index order is worst-to-best in the sense
# that later stages are closer to a verified conclusion -- "Confirmed
# defect" is last and, by design, never assigned by this module.
SEVERITY_OBSERVED = "Observed"
SEVERITY_POTENTIAL_ISSUE = "Potential issue"
SEVERITY_SUSPECTED_DEFECT = "Suspected defect"
SEVERITY_REQUIRES_VERIFICATION = "Requires verification"
SEVERITY_CONFIRMED_DEFECT = "Confirmed defect"  # never assigned by this module -- see module docstring

SEVERITY_LEVELS = (
    SEVERITY_OBSERVED,
    SEVERITY_POTENTIAL_ISSUE,
    SEVERITY_SUSPECTED_DEFECT,
    SEVERITY_REQUIRES_VERIFICATION,
    SEVERITY_CONFIRMED_DEFECT,
)

# Diagnosis.confidence -> TestCandidate.severity. Deliberately never maps
# to SEVERITY_CONFIRMED_DEFECT, even for Diagnosis.confidence == "Confirmed"
# -- that confidence level means the *observation* is confirmed (e.g. "no
# event fired, confirmed"), not that the underlying defect classification
# (intentional vs. bug) has been confirmed, which only a human/Playwright
# run can do.
_SEVERITY_BY_CONFIDENCE: Dict[str, str] = {
    "Confirmed": SEVERITY_REQUIRES_VERIFICATION,
    "Highly likely": SEVERITY_SUSPECTED_DEFECT,
    "Possible": SEVERITY_POTENTIAL_ISSUE,
    "Needs investigation": SEVERITY_OBSERVED,
}
assert set(_SEVERITY_BY_CONFIDENCE) == set(CONFIDENCE_LEVELS)  # stay in sync with diagnostics.models

# root_cause -> category, for every root_cause diagnostics/rules.py's
# REGISTRY (+ find_duplicate_purchases) actually emits. See module
# docstring for the two categories with no source here.
_CATEGORY_BY_ROOT_CAUSE: Dict[str, str] = {
    "spa_navigation_missing_pageview": CATEGORY_EVENT_EXISTENCE,
    "missing_datalayer_event": CATEGORY_EVENT_EXISTENCE,
    "api_call_without_tracking_event": CATEGORY_EVENT_EXISTENCE,
    "js_error_blocking": CATEGORY_EVENT_EXISTENCE,
    "event_name_mismatch": CATEGORY_EVENT_PAYLOAD,
    "gtm_trigger_mismatch": CATEGORY_EVENT_PAYLOAD,
    "parameter_loss": CATEGORY_EVENT_PAYLOAD,
    "ecommerce_missing_parameters": CATEGORY_EVENT_PAYLOAD,
    "pii_leak_detected": CATEGORY_EVENT_PAYLOAD,
    "duplicate_datalayer_event": CATEGORY_EVENT_PAYLOAD,
    "duplicate_purchase": CATEGORY_EVENT_PAYLOAD,
    "gtm_tag_not_executed": CATEGORY_NETWORK_TRANSMISSION,
    "missing_ga4_request": CATEGORY_NETWORK_TRANSMISSION,
    "ga4_ingestion_not_confirmed": CATEGORY_NETWORK_TRANSMISSION,
    "duplicate_analytics_request": CATEGORY_NETWORK_TRANSMISSION,
    "consent_blocked": CATEGORY_CONSENT_BEHAVIOR,
    "timing_delay": CATEGORY_TIMING,
}

_VERIFICATION_STEPS_BY_CATEGORY: Dict[str, Tuple[str, ...]] = {
    CATEGORY_EVENT_EXISTENCE: (
        "Open the page and trigger the interaction ({selector})",
        "Capture window.dataLayer before and after the interaction",
        "Assert a new dataLayer event was pushed for '{business_event}'",
    ),
    CATEGORY_EVENT_PAYLOAD: (
        "Trigger the interaction ({selector}) and capture the resulting dataLayer event",
        "Locate the '{business_event}' event",
        "Assert the event's payload matches what's expected (see Observed problem)",
    ),
    CATEGORY_NETWORK_TRANSMISSION: (
        "Trigger the interaction ({selector})",
        "Capture outgoing network requests after the dataLayer/GTM stage fires",
        "Assert an analytics request corresponding to '{business_event}' was sent, and only once",
    ),
    CATEGORY_CONSENT_BEHAVIOR: (
        "Set consent state to denied before loading the page",
        "Trigger the interaction ({selector})",
        "Assert no tracking network request fires while consent is denied",
    ),
    CATEGORY_TIMING: (
        "Trigger the interaction ({selector})",
        "Record the timestamp the '{business_event}' dataLayer event fires",
        "Record the timestamp any state it depends on (cookie/storage/dataLayer field) becomes available",
        "Assert the dependency was available at or before the trigger's timestamp",
    ),
    CATEGORY_CONSISTENCY: (
        "Trigger '{business_event}' from each UI surface it appears on (see Evidence)",
        "Capture the resulting dataLayer event name/shape from each surface",
        "Assert every surface produces the same event name and shape",
    ),
    CATEGORY_REGRESSION: (
        "Trigger the interaction that produces '{business_event}' (previously confirmed to include '{field}')",
        "Capture the resulting dataLayer event payload",
        "Assert the field '{field}' is present in the payload",
    ),
}

_ROOT_CAUSE_LABELS: Dict[str, str] = {
    "spa_navigation_missing_pageview": "should fire a page_view event on SPA navigation",
    "missing_datalayer_event": "should fire a dataLayer event",
    "api_call_without_tracking_event": "should fire a dataLayer event when its API call succeeds",
    "js_error_blocking": "should fire even when a JS error occurs nearby",
    "event_name_mismatch": "should fire under the expected event name",
    "gtm_trigger_mismatch": "should match its configured GTM trigger's event name",
    "parameter_loss": "should not lose parameters between dataLayer and the analytics request",
    "ecommerce_missing_parameters": "should include all required ecommerce parameters",
    "pii_leak_detected": "should not leak PII in its payload",
    "duplicate_datalayer_event": "should not push its dataLayer event more than once",
    "duplicate_purchase": "should not fire more than once for the same transaction",
    "gtm_tag_not_executed": "should have its GTM tag actually execute",
    "missing_ga4_request": "should produce a corresponding GA4 network request",
    "ga4_ingestion_not_confirmed": "should be confirmed ingested by GA4",
    "duplicate_analytics_request": "should not send more than one analytics request",
    "consent_blocked": "should respect consent state before firing",
    "timing_delay": "should have its dependent state available before it fires",
}


@dataclass(frozen=True)
class TestCandidate:
    # VISION.md §15's own term -- named accurately rather than avoiding
    # "Test" for pytest's sake. __test__ = False tells pytest's collector
    # this dataclass isn't a test class, silencing the otherwise-harmless
    # "cannot collect ... __init__ constructor" warning.
    __test__ = False

    name: str
    category: str  # one of CATEGORIES
    severity: str  # one of SEVERITY_LEVELS, never SEVERITY_CONFIRMED_DEFECT at generation time
    observed: str
    observed_problem: str
    evidence_pages: Tuple[str, ...] = field(default_factory=tuple)  # deduped, sorted
    suggested_verification: Tuple[str, ...] = field(default_factory=tuple)
    source_root_causes: Tuple[str, ...] = field(default_factory=tuple)

    @property
    def evidence_count(self) -> int:
        return len(self.evidence_pages)


def format_verification_steps(category: str, business_event: str, selector: "str | None", **extra: str) -> Tuple[str, ...]:
    templates = _VERIFICATION_STEPS_BY_CATEGORY.get(category, ())
    return tuple(
        step.format(business_event=business_event, selector=selector or "the relevant element", **extra)
        for step in templates
    )


def generate_diagnosis_candidates(journeys: Sequence[TrackingJourney]) -> List[TestCandidate]:
    """Groups journeys by (root_cause, business_event) -- the same
    underlying problem observed across however many pages/interactions it
    showed up on becomes ONE candidate with an evidence list, not one
    candidate per occurrence (VISION.md §15's own example: "Evidence: 23
    product pages", not 23 separate candidates)."""
    groups: Dict[Tuple[str, str], List[TrackingJourney]] = {}
    for journey in journeys:
        diagnosis = journey.diagnosis
        if diagnosis is None or diagnosis.root_cause == "none":
            continue
        category = _CATEGORY_BY_ROOT_CAUSE.get(diagnosis.root_cause)
        if category is None:
            continue  # a root_cause with no category mapping is skipped, not guessed at
        groups.setdefault((diagnosis.root_cause, journey.business_event), []).append(journey)

    candidates = []
    for (root_cause, business_event), group in sorted(groups.items()):
        category = _CATEGORY_BY_ROOT_CAUSE[root_cause]
        diagnosis = group[0].diagnosis
        pages = tuple(sorted({j.observations[0].page_url for j in group if j.observations}))
        selector = group[0].anchor_selector
        label = _ROOT_CAUSE_LABELS.get(root_cause, root_cause.replace("_", " "))
        candidates.append(
            TestCandidate(
                name=f"'{business_event}' {label}",
                category=category,
                severity=_SEVERITY_BY_CONFIDENCE.get(diagnosis.confidence, SEVERITY_OBSERVED),
                observed=f"'{business_event}' event observed",
                observed_problem=diagnosis.message,
                evidence_pages=pages,
                suggested_verification=format_verification_steps(category, business_event, selector),
                source_root_causes=(root_cause,),
            )
        )
    return candidates


def generate_consistency_candidates(reports: Sequence[BusinessActionConsistencyReport]) -> List[TestCandidate]:
    """One candidate per business action whose fired implementations
    disagree on event naming/shape across UI surfaces -- reuses Phase 1.8's
    `analyze_business_action_consistency()` output rather than a new
    cross-page comparison engine (VISION.md §15's "cross-implementation
    comparison stays central")."""
    candidates = []
    for report in reports:
        if report.is_consistent:
            continue
        pages = tuple(sorted({impl.page_url for impl in report.implementations if impl.fired}))
        names = ", ".join(report.distinct_event_names)
        candidates.append(
            TestCandidate(
                name=f"'{report.business_objective}' should fire the same event everywhere it appears",
                category=CATEGORY_CONSISTENCY,
                severity=SEVERITY_SUSPECTED_DEFECT,
                observed=f"{report.fired_count} implementation(s) of '{report.business_objective}' fired",
                observed_problem=(
                    f"{len(report.distinct_event_names)} different event name(s) observed across "
                    f"implementations that fired: {names}"
                ),
                evidence_pages=pages,
                suggested_verification=format_verification_steps(
                    CATEGORY_CONSISTENCY, report.business_objective, None
                ),
                source_root_causes=("business_action_naming_drift",),
            )
        )
    return candidates
