"""Rule-based diagnostic engine (spec section 9). Deterministic by design --
no LLM dependency -- so `pytagmanager diagnose` works with zero external
credentials beyond what's needed to observe the browser. Every rule is a
small `(TrackingJourney, DiagnosticContext) -> Optional[Diagnosis]`
callable registered in `REGISTRY`, mirroring `export/base.py`'s
`EXPORTERS` registry pattern.

`diagnose_journey` runs every rule and returns every match (a journey can
have more than one simultaneous issue, e.g. a PII leak *and* an event-name
mismatch); `primary_diagnosis` picks the most severe one for the journey's
single-line headline in reporting.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional

from pytagmanager.analytics_api.models import GtmTag, GtmTrigger
from pytagmanager.correlation.journey import TrackingJourney
from pytagmanager.diagnostics.models import Diagnosis
from pytagmanager.observability.scenario import Expectation
from pytagmanager.recommend.models import TrackingRecommendation

_SEVERITY_RANK = {"critical": 3, "warning": 2, "unknown": 1, "healthy": 0}

# Content-pattern PII detection (distinct from events.py's key-name-based
# redact_payload): catches PII leaking through innocuously-named fields,
# e.g. an email address passed as a "search_term" parameter.
_PII_PATTERNS = {
    "email": re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}"),
    "credit_card": re.compile(r"\b(?:\d[ -]?){13,16}\b"),
    "ssn": re.compile(r"\b\d{3}-\d{2}-\d{4}\b"),
    "phone": re.compile(r"\b\d{3}[-.]?\d{3}[-.]?\d{4}\b"),
}


def _normalize_selector(selector: str) -> str:
    return selector.replace("'", '"')


@dataclass
class DiagnosticContext:
    """Bundles the "what should happen" side of a diagnosis: hand-authored
    scenario expectations, and/or live GTM/GA4 config. All fields are
    optional -- rules that need a piece of context they weren't given
    simply don't fire rather than guessing.
    """

    # Keyed by the *selector* of the interaction that starts a scenario
    # (`journey.anchor_selector`), not by business_event -- business_event
    # is inferred from the observed runtime event, so it's exactly the
    # wrong key when what we're checking is whether that name is correct.
    expectations_by_selector: Dict[str, List[Expectation]] = field(default_factory=dict)
    gtm_triggers: Optional[List[GtmTrigger]] = None
    gtm_tags: Optional[List[GtmTag]] = None
    ga4_ingestion: Dict[str, Optional[bool]] = field(default_factory=dict)  # event_name -> was_ingested

    def __post_init__(self) -> None:
        # CSS attribute selectors are quote-style-agnostic
        # ([data-testid='x'] == [data-testid="x"]), but agent.js's
        # describeSelector() always emits double quotes while a
        # hand-authored scenario YAML might use either -- normalize both
        # sides of the lookup so they always compare equal.
        self.expectations_by_selector = {
            _normalize_selector(k): v for k, v in self.expectations_by_selector.items()
        }

    def expected_datalayer_event(self, selector: Optional[str]) -> Optional[str]:
        """The exact event name a hand-authored scenario asserts, or None.
        Deliberately does NOT include `any_datalayer_event` expectations --
        those are auto-derived best guesses, not real predictions of the
        literal name, so they must never drive an exact-match comparison
        (see `expects_any_datalayer_event` for the weaker "some event
        fired" check auto-discovery actually wants).
        """
        if not selector:
            return None
        for expectation in self.expectations_by_selector.get(_normalize_selector(selector), []):
            if expectation.kind == "datalayer_event":
                return expectation.value
        return None

    def expects_any_datalayer_event(self, selector: Optional[str]) -> bool:
        if not selector:
            return False
        return any(
            expectation.kind in ("datalayer_event", "any_datalayer_event")
            for expectation in self.expectations_by_selector.get(_normalize_selector(selector), [])
        )

    def ga4_ingested(self, event_name: str) -> Optional[bool]:
        return self.ga4_ingestion.get(event_name)


def _first_event_name(journey: TrackingJourney, event_type: str) -> Optional[str]:
    events = journey.events_of_type(event_type)
    return events[0].event_name or None if events else None


def _normalize(name: str) -> str:
    return re.sub(r"[_\-\s]", "", name.lower())


def _find_trigger_by_event(name: str, triggers: List[GtmTrigger]) -> Optional[GtmTrigger]:
    return next((t for t in triggers if t.event_name == name), None)


def _find_closest_trigger(name: str, triggers: List[GtmTrigger]) -> Optional[GtmTrigger]:
    normalized = _normalize(name)
    return next(
        (t for t in triggers if t.event_name and _normalize(t.event_name) == normalized and t.event_name != name),
        None,
    )


def rule_spa_navigation_missing_pageview(journey: TrackingJourney, ctx: DiagnosticContext) -> Optional[Diagnosis]:
    route_changes = journey.events_of_type("route_change")
    if not route_changes:
        return None
    pageviews = [e for e in journey.events_of_type("datalayer_push") if "page_view" in (e.event_name or "").lower()]
    if pageviews:
        return None
    return Diagnosis(
        severity="critical",
        root_cause="spa_navigation_missing_pageview",
        message="SPA navigation occurred without the expected page-view tracking event.",
        rule_name="spa_navigation_missing_pageview",
        details={"route": route_changes[0].payload.get("url", "")},
        confidence="Highly likely",
    )


def rule_missing_datalayer_event(journey: TrackingJourney, ctx: DiagnosticContext) -> Optional[Diagnosis]:
    if not ctx.expects_any_datalayer_event(journey.anchor_selector):
        return None
    if journey.stage_present("datalayer"):
        return None
    expected = ctx.expected_datalayer_event(journey.anchor_selector)
    return Diagnosis(
        severity="critical",
        root_cause="missing_datalayer_event",
        message="User interaction occurred but the application did not generate the expected dataLayer event.",
        rule_name="missing_datalayer_event",
        details={"expected_event": expected} if expected else {},
        confidence="Confirmed",
    )


def rule_event_name_mismatch(journey: TrackingJourney, ctx: DiagnosticContext) -> Optional[Diagnosis]:
    observed = _first_event_name(journey, "datalayer_push")
    if not observed:
        return None

    expected = ctx.expected_datalayer_event(journey.anchor_selector)
    if expected and observed != expected:
        return Diagnosis(
            severity="critical",
            root_cause="event_name_mismatch",
            message=f"Runtime dataLayer event '{observed}' does not match the expected event name '{expected}'.",
            rule_name="event_name_mismatch",
            details={"runtime_event": observed, "expected_event": expected},
            confidence="Confirmed",
        )

    if ctx.gtm_triggers is not None and _find_trigger_by_event(observed, ctx.gtm_triggers) is None:
        closest = _find_closest_trigger(observed, ctx.gtm_triggers)
        if closest is not None:
            return Diagnosis(
                severity="critical",
                root_cause="gtm_trigger_mismatch",
                message=(
                    f"GTM trigger event name does not match the runtime dataLayer event. "
                    f"Runtime: '{observed}'. GTM trigger '{closest.name}' expects: '{closest.event_name}'."
                ),
                rule_name="event_name_mismatch",
                details={"runtime_event": observed, "configured_event": closest.event_name, "affected_trigger": closest.name},
                confidence="Highly likely",
            )
    return None


def rule_api_call_without_tracking_event(journey: TrackingJourney, ctx: DiagnosticContext) -> Optional[Diagnosis]:
    """Site-Wide QA spec section 4: '/cart API succeeds -> cart UI changes
    -> add_to_cart event absent' should be flagged as a potential tracking
    gap. Deliberately narrow: only fires when this interaction's selector
    has an explicit expectation (scenario-authored or auto-derived from a
    static recommendation) -- an app makes many API calls that were never
    meant to be tracked, and flagging all of them would be pure noise
    (the spec explicitly warns against assuming every API call implies a
    tracking event).
    """
    api_calls = journey.events_of_type("api_call")
    if not api_calls or journey.stage_present("datalayer") or journey.stage_present("gtm"):
        return None
    if not ctx.expects_any_datalayer_event(journey.anchor_selector):
        return None
    expected = ctx.expected_datalayer_event(journey.anchor_selector)
    details = {"url": api_calls[0].payload.get("url", "")}
    if expected:
        details["expected_event"] = expected
    return Diagnosis(
        severity="warning",
        root_cause="api_call_without_tracking_event",
        message="An application API call completed but no corresponding dataLayer event was generated.",
        rule_name="api_call_without_tracking_event",
        details=details,
        confidence="Possible",
    )


def rule_gtm_tag_not_executed(journey: TrackingJourney, ctx: DiagnosticContext) -> Optional[Diagnosis]:
    observed = _first_event_name(journey, "datalayer_push")
    if not observed or ctx.gtm_triggers is None or ctx.gtm_tags is None:
        return None
    trigger = _find_trigger_by_event(observed, ctx.gtm_triggers)
    if trigger is None:
        return None
    matching_tags = [t for t in ctx.gtm_tags if trigger.trigger_id in t.firing_trigger_ids]
    if not matching_tags or journey.stage_present("network") or journey.stage_present("gtm"):
        return None
    return Diagnosis(
        severity="critical",
        root_cause="gtm_tag_not_executed",
        message="dataLayer event was generated but the expected GTM tag did not execute.",
        rule_name="gtm_tag_not_executed",
        details={"event": observed, "affected_tags": [t.name for t in matching_tags]},
        confidence="Highly likely",
    )


def _consent_denied(journey: TrackingJourney) -> bool:
    return any(
        "denied" in str(value).lower()
        for event in journey.events_of_type("consent_change")
        for value in event.payload.values()
    )


def rule_missing_analytics_request(journey: TrackingJourney, ctx: DiagnosticContext) -> Optional[Diagnosis]:
    if not (journey.stage_present("datalayer") or journey.stage_present("gtm")):
        return None
    observed = _first_event_name(journey, "datalayer_push") or journey.business_event
    if not journey.stage_present("network"):
        if _consent_denied(journey):
            # rule_consent_blocking already explains this more specifically;
            # reporting both would be a redundant pair of warnings for the
            # same underlying symptom.
            return None
        return Diagnosis(
            severity="warning",
            root_cause="missing_ga4_request",
            message="GTM tag executed but no corresponding GA4 network request was observed.",
            rule_name="missing_analytics_request",
            details={"event": observed},
            confidence="Confirmed",
        )
    ingested = ctx.ga4_ingested(observed)
    if ingested is False:
        return Diagnosis(
            severity="warning",
            root_cause="ga4_ingestion_not_confirmed",
            message="A GA4 request was sent, but GA4's realtime report does not show it was received.",
            rule_name="missing_analytics_request",
            details={"event": observed},
            confidence="Highly likely",
        )
    return None


def rule_duplicate_analytics_request(journey: TrackingJourney, ctx: DiagnosticContext) -> Optional[Diagnosis]:
    requests = journey.events_of_type("network_request")
    if len(requests) <= 1:
        return None
    return Diagnosis(
        severity="warning",
        root_cause="duplicate_analytics_request",
        message="Possible duplicate analytics implementation: multiple analytics requests observed for one business action.",
        rule_name="duplicate_analytics_request",
        details={"request_count": len(requests)},
        confidence="Confirmed",
    )


def rule_duplicate_datalayer_event(journey: TrackingJourney, ctx: DiagnosticContext) -> Optional[Diagnosis]:
    pushes = [e for e in journey.events_of_type("datalayer_push") if e.event_name == journey.business_event]
    if len(pushes) <= 1:
        return None
    return Diagnosis(
        severity="warning",
        root_cause="duplicate_datalayer_event",
        message="Possible duplicate application event: the same dataLayer event fired more than once for one action.",
        rule_name="duplicate_datalayer_event",
        details={"push_count": len(pushes)},
        confidence="Confirmed",
    )


def rule_consent_blocking(journey: TrackingJourney, ctx: DiagnosticContext) -> Optional[Diagnosis]:
    if journey.stage_present("network") or not journey.stage_present("datalayer"):
        return None
    if not _consent_denied(journey):
        return None
    return Diagnosis(
        severity="warning",
        root_cause="consent_blocked",
        message="Tag execution may have been prevented by consent configuration.",
        rule_name="consent_blocking",
        details={},
        confidence="Possible",
    )


def rule_js_error_blocking(journey: TrackingJourney, ctx: DiagnosticContext) -> Optional[Diagnosis]:
    if not ctx.expects_any_datalayer_event(journey.anchor_selector) or journey.stage_present("datalayer"):
        return None
    errors = journey.events_of_type("js_error")
    if not errors:
        return None
    return Diagnosis(
        severity="critical",
        root_cause="js_error_blocking",
        message="Tracking event may have been prevented by a JavaScript error.",
        rule_name="js_error_blocking",
        details={"errors": [e.payload.get("message", "") for e in errors]},
        confidence="Possible",
    )


def rule_parameter_loss(journey: TrackingJourney, ctx: DiagnosticContext) -> Optional[Diagnosis]:
    pushes = journey.events_of_type("datalayer_push")
    requests = journey.events_of_type("network_request")
    if not pushes or not requests:
        return None
    # "items" is a structured ecommerce array, not a scalar that flows
    # through GA4 hit query params the same way -- it's validated
    # separately by rule_ecommerce_missing_parameters, not here.
    upstream_params = {k for k, v in pushes[0].payload.items() if k not in ("event", "items") and v not in (None, "")}
    downstream_params = set()
    for request in requests:
        params = request.payload.get("params", {})
        for key in params:
            downstream_params.add(key[3:] if key.startswith("ep.") else key)
    missing = upstream_params - downstream_params
    if not missing:
        return None
    return Diagnosis(
        severity="warning",
        root_cause="parameter_loss",
        message="A tracking parameter was present upstream (dataLayer) but missing from the analytics request.",
        rule_name="parameter_loss",
        details={"missing_parameters": sorted(missing)},
        confidence="Possible",
    )


# Required GA4 ecommerce parameters per event (spec section 9's Ecommerce
# Audit) -- deliberately only the fields whose *absence* is unambiguous
# evidence of a broken implementation regardless of the site's specific
# catalog/checkout shape; item-level fields (item_id/item_name/quantity/
# price) live inside `items[]` and aren't separately validated here since
# their shape varies too much to check generically without false positives.
_ECOMMERCE_REQUIRED_PARAMS = {
    "view_item": {"items", "currency", "value"},
    "view_item_list": {"items"},
    "add_to_cart": {"items", "currency", "value"},
    "remove_from_cart": {"items", "currency", "value"},
    "begin_checkout": {"items", "currency", "value"},
    "add_shipping_info": {"items", "currency", "value"},
    "add_payment_info": {"items", "currency", "value"},
    "purchase": {"transaction_id", "items", "currency", "value"},
}


def rule_ecommerce_missing_parameters(journey: TrackingJourney, ctx: DiagnosticContext) -> Optional[Diagnosis]:
    pushes = journey.events_of_type("datalayer_push")
    if not pushes:
        return None
    push = pushes[0]
    required = _ECOMMERCE_REQUIRED_PARAMS.get(push.event_name)
    if not required:
        return None
    present = {key for key, value in push.payload.items() if value not in (None, "", [])}
    missing = required - present
    if not missing:
        return None
    return Diagnosis(
        severity="warning",
        root_cause="ecommerce_missing_parameters",
        message=f"'{push.event_name}' is missing required ecommerce parameter(s): {', '.join(sorted(missing))}.",
        rule_name="ecommerce_missing_parameters",
        details={"event": push.event_name, "missing_parameters": sorted(missing)},
        confidence="Confirmed",
    )


def rule_pii_leak(journey: TrackingJourney, ctx: DiagnosticContext) -> Optional[Diagnosis]:
    """Content-pattern PII scan over dataLayer/network payload *values*
    (not just key names -- see events.redact_payload for the key-based
    denylist this complements). Inspired by ObservePoint's PII Detection
    feature: catches PII leaking through innocuously-named fields.
    """
    findings = []
    for event in journey.observations:
        if event.event_type not in ("datalayer_push", "network_request"):
            continue
        for value in _flatten_values(event.payload):
            for pii_type, pattern in _PII_PATTERNS.items():
                if pattern.search(str(value)):
                    findings.append(pii_type)
    if not findings:
        return None
    return Diagnosis(
        severity="warning",
        root_cause="pii_leak_detected",
        message="Tracking payload appears to contain personally identifiable information.",
        rule_name="pii_leak",
        details={"pii_types": sorted(set(findings))},
        confidence="Possible",
    )


def _flatten_values(payload) -> List[str]:
    values: List[str] = []
    if isinstance(payload, dict):
        for v in payload.values():
            values.extend(_flatten_values(v))
    elif isinstance(payload, (list, tuple)):
        for v in payload:
            values.extend(_flatten_values(v))
    elif payload is not None:
        values.append(payload)
    return values


REGISTRY: List[Callable[[TrackingJourney, DiagnosticContext], Optional[Diagnosis]]] = [
    rule_spa_navigation_missing_pageview,
    rule_missing_datalayer_event,
    rule_api_call_without_tracking_event,
    rule_event_name_mismatch,
    rule_gtm_tag_not_executed,
    rule_missing_analytics_request,
    rule_duplicate_analytics_request,
    rule_duplicate_datalayer_event,
    rule_consent_blocking,
    rule_js_error_blocking,
    rule_parameter_loss,
    rule_ecommerce_missing_parameters,
    rule_pii_leak,
]


def diagnose_journey(journey: TrackingJourney, ctx: DiagnosticContext) -> List[Diagnosis]:
    return [d for rule in REGISTRY if (d := rule(journey, ctx)) is not None]


def primary_diagnosis(diagnoses: List[Diagnosis]) -> Diagnosis:
    if not diagnoses:
        return Diagnosis.healthy()
    return max(diagnoses, key=lambda d: _SEVERITY_RANK.get(d.severity, 0))


def find_untested_recommendations(
    recommendations: List[TrackingRecommendation],
    journeys: List[TrackingJourney],
) -> List[TrackingRecommendation]:
    """Static candidates (`recommend.recommend_for_graph()` output) with no
    corresponding runtime journey -- i.e. the element was never exercised
    during observation. Distinct severity from the rules above: this means
    "untested," not "confirmed broken" (the element might be unreachable in
    this session, e.g. behind a modal or a later page in a flow).
    """
    tested_selectors = {
        obs.selector
        for journey in journeys
        for obs in journey.observations
        if obs.event_type in ("click", "submit", "change") and obs.selector
    }
    return [r for r in recommendations if r.selector not in tested_selectors]


def find_duplicate_purchases(journeys: List[TrackingJourney]) -> List[Diagnosis]:
    """Cross-journey ecommerce check: the same `transaction_id` appearing in
    more than one 'purchase' dataLayer push anywhere in the session is a
    strong signal of a double-fired purchase event (e.g. a confirmation
    page re-tracked on reload). Unlike every other rule, this can't be
    detected from a single journey in isolation, so it isn't in `REGISTRY`
    -- callers run it once over the full journey list, not per journey.
    """
    counts_by_transaction: Dict[str, int] = {}
    for journey in journeys:
        for push in journey.events_of_type("datalayer_push"):
            if push.event_name != "purchase":
                continue
            transaction_id = push.payload.get("transaction_id")
            if transaction_id:
                counts_by_transaction[transaction_id] = counts_by_transaction.get(transaction_id, 0) + 1

    return [
        Diagnosis(
            severity="critical",
            root_cause="duplicate_purchase",
            message=f"Purchase event fired {count} times for the same transaction_id.",
            rule_name="duplicate_purchase",
            details={"transaction_id": transaction_id, "count": count},
            confidence="Confirmed",
        )
        for transaction_id, count in counts_by_transaction.items()
        if count > 1
    ]
