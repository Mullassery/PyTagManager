"""Runtime validation of an SDR against observed tracking journeys."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlsplit, urlunsplit

from pytagmanager.correlation.journey import TrackingJourney

from .schema import SdrEvent, SdrParameter, SdrSchema

_CHECK_PASSED = "passed"
_CHECK_FAILED = "failed"


@dataclass(frozen=True)
class SdrCheck:
    kind: str
    status: str
    message: str
    parameter: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "status": self.status,
            "message": self.message,
            "parameter": self.parameter,
        }


@dataclass(frozen=True)
class SdrIssue:
    code: str
    severity: str
    event_name: str
    message: str
    recommendation: str
    parameter: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "severity": self.severity,
            "event_name": self.event_name,
            "parameter": self.parameter,
            "message": self.message,
            "recommendation": self.recommendation,
        }


@dataclass(frozen=True)
class SdrEventResult:
    event_name: str
    status: str
    occurrences: int
    pages: tuple[str, ...]
    selector: str
    network_observed: bool
    checks: tuple[SdrCheck, ...]
    issues: tuple[SdrIssue, ...]

    @property
    def checks_passed(self) -> int:
        return sum(check.status == _CHECK_PASSED for check in self.checks)

    @property
    def checks_failed(self) -> int:
        return sum(check.status == _CHECK_FAILED for check in self.checks)

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_name": self.event_name,
            "status": self.status,
            "occurrences": self.occurrences,
            "pages": list(self.pages),
            "selector": self.selector,
            "network_observed": self.network_observed,
            "checks": [check.to_dict() for check in self.checks],
            "issues": [issue.to_dict() for issue in self.issues],
        }


@dataclass(frozen=True)
class SdrValidation:
    schema_name: str
    events: tuple[SdrEventResult, ...]
    issues: tuple[SdrIssue, ...]
    limitations: tuple[str, ...] = ()

    @property
    def checks_passed(self) -> int:
        return sum(event.checks_passed for event in self.events)

    @property
    def checks_failed(self) -> int:
        return sum(event.checks_failed for event in self.events)

    @property
    def checks_total(self) -> int:
        return self.checks_passed + self.checks_failed

    @property
    def alignment_score(self) -> float:
        return self.checks_passed / self.checks_total if self.checks_total else 0.0

    @property
    def is_aligned(self) -> bool:
        return self.checks_total > 0 and self.checks_failed == 0

    @property
    def recommendations(self) -> tuple[str, ...]:
        return tuple(dict.fromkeys(issue.recommendation for issue in self.issues))

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": 1,
            "sdr_name": self.schema_name,
            "alignment_score": round(self.alignment_score, 4),
            "checks": {
                "total": self.checks_total,
                "passed": self.checks_passed,
                "failed": self.checks_failed,
            },
            "events": [event.to_dict() for event in self.events],
            "issues": [issue.to_dict() for issue in self.issues],
            "recommendations": list(self.recommendations),
            "limitations": list(self.limitations),
        }


def _safe_page(value: Any) -> str:
    if not isinstance(value, str) or not value:
        return ""
    try:
        parsed = urlsplit(value)
    except ValueError:
        return ""
    return urlunsplit((parsed.scheme, parsed.netloc, parsed.path, "", ""))


def _normalize_selector(value: str) -> str:
    return value.replace("'", '"')


def _lookup(payload: Mapping[str, Any], name: str) -> tuple[Any, bool]:
    if name in payload:
        return payload[name], True
    current: Any = payload
    for part in name.split("."):
        if not isinstance(current, Mapping) or part not in current:
            return None, False
        current = current[part]
    return current, True


def _observed_type(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int):
        return "integer"
    if isinstance(value, float):
        return "number"
    if isinstance(value, str):
        return "string"
    if isinstance(value, list):
        return "array"
    if isinstance(value, Mapping):
        return "object"
    return type(value).__name__


def _matches_type(value: Any, types: Iterable[str]) -> bool:
    for expected in types:
        if expected == "any":
            return True
        if expected == "string" and isinstance(value, str):
            return True
        if expected == "number" and isinstance(value, (int, float)) and not isinstance(value, bool):
            return True
        if expected == "integer" and isinstance(value, int) and not isinstance(value, bool):
            return True
        if expected == "boolean" and isinstance(value, bool):
            return True
        if expected == "array" and isinstance(value, list):
            return True
        if expected == "object" and isinstance(value, Mapping):
            return True
    return False


def _allowed_matches(value: Any, allowed: tuple[Any, ...]) -> bool:
    if not allowed:
        return True
    for candidate in allowed:
        if isinstance(value, bool) or isinstance(candidate, bool):
            if isinstance(value, bool) and isinstance(candidate, bool) and value == candidate:
                return True
            continue
        if isinstance(value, (int, float)):
            try:
                if float(value) == float(candidate):
                    return True
            except (TypeError, ValueError):
                pass
            continue
        if str(value) == str(candidate):
            return True
    return False


def _issue(
    code: str,
    severity: str,
    event_name: str,
    message: str,
    recommendation: str,
    parameter: str = "",
) -> SdrIssue:
    return SdrIssue(
        code=code,
        severity=severity,
        event_name=event_name,
        message=message,
        recommendation=recommendation,
        parameter=parameter,
    )


def _parameter_result(
    event_name: str,
    parameter: SdrParameter,
    payloads: list[Mapping[str, Any]],
) -> tuple[list[SdrCheck], list[SdrIssue]]:
    checks: list[SdrCheck] = []
    issues: list[SdrIssue] = []
    values = [_lookup(payload, parameter.name) for payload in payloads]
    present = [value for value, found in values if found]
    missing = len(values) - len(present)
    if missing:
        if parameter.required:
            checks.append(
                SdrCheck(
                    kind="parameter_present",
                    status=_CHECK_FAILED,
                    parameter=parameter.name,
                    message=(
                        f"Required parameter {parameter.name!r} was missing from "
                        f"{missing} of {len(values)} event occurrence(s)."
                    ),
                )
            )
            issues.append(
                _issue(
                    "missing_parameter",
                    "critical",
                    event_name,
                    f"Required parameter {parameter.name!r} is missing from at least one dataLayer occurrence.",
                    f"Add {parameter.name!r} to the {event_name!r} dataLayer push and map it in the tag.",
                    parameter.name,
                )
            )
        if not present:
            return checks, issues
    else:
        checks.append(
            SdrCheck(
                kind="parameter_present",
                status=_CHECK_PASSED,
                parameter=parameter.name,
                message=f"Parameter {parameter.name!r} is present in every occurrence.",
            )
        )

    wrong = [value for value in present if not _matches_type(value, parameter.types)]
    if wrong:
        expected = " or ".join(parameter.types)
        observed = ", ".join(sorted({_observed_type(value) for value in wrong}))
        checks.append(
            SdrCheck(
                kind="parameter_type",
                status=_CHECK_FAILED,
                parameter=parameter.name,
                message=f"Parameter {parameter.name!r} expected {expected}, observed {observed}.",
            )
        )
        issues.append(
            _issue(
                "wrong_type",
                "warning",
                event_name,
                f"Parameter {parameter.name!r} has type {observed}, expected {expected}.",
                f"Normalize {parameter.name!r} to {expected} before pushing the {event_name!r} event.",
                parameter.name,
            )
        )
    else:
        checks.append(
            SdrCheck(
                kind="parameter_type",
                status=_CHECK_PASSED,
                parameter=parameter.name,
                message=f"Parameter {parameter.name!r} matches {', '.join(parameter.types)}.",
            )
        )
    if parameter.allowed:
        invalid = [value for value in present if not _allowed_matches(value, parameter.allowed)]
        if invalid:
            checks.append(
                SdrCheck(
                    kind="parameter_allowed",
                    status=_CHECK_FAILED,
                    parameter=parameter.name,
                    message=f"Parameter {parameter.name!r} is outside the SDR allow-list.",
                )
            )
            issues.append(
                _issue(
                    "value_not_allowed",
                    "warning",
                    event_name,
                    f"Parameter {parameter.name!r} has a value outside the SDR allow-list.",
                    f"Restrict {parameter.name!r} to an allowed value or update the SDR.",
                    parameter.name,
                )
            )
        else:
            checks.append(
                SdrCheck(
                    kind="parameter_allowed",
                    status=_CHECK_PASSED,
                    parameter=parameter.name,
                    message=f"Parameter {parameter.name!r} is inside the SDR allow-list.",
                )
            )
    return checks, issues


def _event_result(
    spec: SdrEvent,
    journeys: list[TrackingJourney],
) -> SdrEventResult:
    matches: list[tuple[TrackingJourney, list[Any]]] = []
    for journey in journeys:
        pushes = [
            event
            for event in journey.observations
            if event.event_type == "datalayer_push" and event.event_name == spec.event_name
        ]
        if pushes:
            matches.append((journey, sorted(pushes, key=lambda event: event.timestamp)))

    checks: list[SdrCheck] = []
    issues: list[SdrIssue] = []
    if not matches:
        checks.append(
            SdrCheck(
                kind="event_present",
                status=_CHECK_FAILED,
                message=f"No dataLayer push named {spec.event_name!r} was observed.",
            )
        )
        issues.append(
            _issue(
                "missing_event",
                "critical",
                spec.event_name,
                f"No dataLayer event named {spec.event_name!r} was observed in the tested journeys.",
                f"Verify the interaction handler pushes {spec.event_name!r}; check for JS errors, a missing "
                "trigger, or a scenario that does not exercise the intended interaction.",
            )
        )
        return SdrEventResult(
            event_name=spec.event_name,
            status="missing",
            occurrences=0,
            pages=(),
            selector="",
            network_observed=False,
            checks=tuple(checks),
            issues=tuple(issues),
        )

    checks.append(
        SdrCheck(
            kind="event_present",
            status=_CHECK_PASSED,
            message=f"dataLayer event {spec.event_name!r} was observed.",
        )
    )
    occurrences = sum(len(pushes) for _, pushes in matches)
    pages = tuple(
        sorted(
            {
                _safe_page(event.page_url)
                for _, pushes in matches
                for event in pushes
                if _safe_page(event.page_url)
            }
        )
    )
    selectors = tuple(
        sorted({journey.anchor_selector for journey, _ in matches if journey.anchor_selector})
    )
    network_observed = any(
        event.event_type == "network_request"
        for journey, _ in matches
        for event in journey.observations
    )

    if spec.page_contains:
        matching_pages = [page for page in pages if spec.page_contains.lower() in page.lower()]
        if pages and len(matching_pages) == len(pages):
            checks.append(
                SdrCheck(
                    kind="page_condition",
                    status=_CHECK_PASSED,
                    message=f"Event fired on pages containing {spec.page_contains!r}.",
                )
            )
        else:
            checks.append(
                SdrCheck(
                    kind="page_condition",
                    status=_CHECK_FAILED,
                    message=f"Event fired outside the SDR page condition {spec.page_contains!r}.",
                )
            )
            issues.append(
                _issue(
                    "page_condition_mismatch",
                    "warning",
                    spec.event_name,
                    f"Event {spec.event_name!r} fired on a page outside the SDR condition.",
                    f"Update the GTM trigger/page condition so {spec.event_name!r} fires only on pages "
                    f"containing {spec.page_contains!r}.",
                )
            )

    if spec.selector:
        expected = _normalize_selector(spec.selector)
        observed = {_normalize_selector(selector) for selector in selectors}
        if observed and observed == {expected}:
            checks.append(
                SdrCheck(
                    kind="selector_condition",
                    status=_CHECK_PASSED,
                    message=f"Event was anchored to selector {spec.selector!r}.",
                )
            )
        else:
            checks.append(
                SdrCheck(
                    kind="selector_condition",
                    status=_CHECK_FAILED,
                    message=f"Event was not anchored exclusively to selector {spec.selector!r}.",
                )
            )
            issues.append(
                _issue(
                    "selector_condition_mismatch",
                    "warning",
                    spec.event_name,
                    f"Event {spec.event_name!r} was not anchored exclusively to the SDR selector.",
                    f"Update the trigger/event wiring so {spec.event_name!r} fires from {spec.selector!r}.",
                )
            )

    payloads = [push.payload for _, pushes in matches for push in pushes]
    for parameter in spec.parameters:
        parameter_checks, parameter_issues = _parameter_result(spec.event_name, parameter, payloads)
        checks.extend(parameter_checks)
        issues.extend(parameter_issues)

    if spec.require_network:
        if network_observed:
            checks.append(
                SdrCheck(
                    kind="network_observed",
                    status=_CHECK_PASSED,
                    message="An analytics network request was observed in the matching journey.",
                )
            )
        else:
            checks.append(
                SdrCheck(
                    kind="network_observed",
                    status=_CHECK_FAILED,
                    message="No analytics network request was observed after the dataLayer event.",
                )
            )
            issues.append(
                _issue(
                    "network_missing",
                    "warning",
                    spec.event_name,
                    f"dataLayer event {spec.event_name!r} fired but no analytics network request was observed.",
                    "Verify the GTM trigger/tag and that consent or client-side blocking is not suppressing "
                    "the request. Server-side delivery is not observable here.",
                )
            )

    duplicate_count = max((len(pushes) for _, pushes in matches), default=0)
    if duplicate_count > 1:
        checks.append(
            SdrCheck(
                kind="single_fire",
                status=_CHECK_FAILED,
                message=f"Event fired {duplicate_count} times in one interaction.",
            )
        )
        issues.append(
            _issue(
                "duplicate_event",
                "warning",
                spec.event_name,
                f"dataLayer event {spec.event_name!r} fired {duplicate_count} times in one interaction.",
                "Remove the duplicate push or narrow the trigger so the event fires once per interaction.",
            )
        )
    else:
        checks.append(
            SdrCheck(
                kind="single_fire",
                status=_CHECK_PASSED,
                message="Event fired at most once per matching interaction.",
            )
        )

    status = "aligned" if not any(check.status == _CHECK_FAILED for check in checks) else "partial"
    return SdrEventResult(
        event_name=spec.event_name,
        status=status,
        occurrences=occurrences,
        pages=pages,
        selector=selectors[0] if len(selectors) == 1 else "",
        network_observed=network_observed,
        checks=tuple(checks),
        issues=tuple(issues),
    )


def validate_sdr(schema: SdrSchema, journeys: Iterable[TrackingJourney]) -> SdrValidation:
    journey_list = list(journeys)
    results = tuple(_event_result(spec, journey_list) for spec in schema.events)
    issues = tuple(issue for result in results for issue in result.issues)
    limitations = [
        (
            "Validation covers observed dataLayer events and payload fields. It does not prove GA4/Adobe "
            "parameter equivalence or server-side delivery."
        ),
        (
            "Only interactions exercised by the current scenario/crawl are evaluated; untested interactions "
            "appear as missing events."
        ),
        "Parameter values are never serialized; reports contain presence, type and allow-list outcomes only.",
        "Network observation only proves that some network request occurred in the matching journey.",
        "SDR alignment is not a legal compliance verdict and does not validate consent enforcement.",
    ]
    if not journey_list:
        issues = issues + (
            _issue(
                "no_runtime_evidence",
                "critical",
                "",
                "No runtime journeys were observed, so the SDR could not be exercised.",
                "Run diagnose with a scenario or crawl that exercises the SDR events.",
            ),
        )
    return SdrValidation(
        schema_name=schema.name,
        events=results,
        issues=issues,
        limitations=tuple(limitations),
    )
