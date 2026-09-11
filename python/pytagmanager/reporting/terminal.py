"""Human-readable terminal report -- the primary output format (spec
section 13). Leads with a stage-by-stage checklist and one plain-language
root-cause line per non-healthy journey, not a raw event log.
"""

from __future__ import annotations

from typing import List, Optional

from pytagmanager.correlation.journey import STAGES, TrackingJourney
from pytagmanager.diagnostics.models import Diagnosis
from pytagmanager.diagnostics.rules import DiagnosticContext, diagnose_journey, primary_diagnosis
from pytagmanager.observability.state import StateDiff
from pytagmanager.recommend.models import TrackingRecommendation
from pytagmanager.reporting.summary import compute_health_summary

_STAGE_LABELS = {
    "interaction": "Browser interaction",
    "mutation": "DOM element",
    "application": "Application API call",
    "datalayer": "dataLayer event",
    "gtm": "GTM trigger/tag",
    "network": "GA4 request",
}


def diagnose_journeys(
    journeys: List[TrackingJourney],
    ctx: DiagnosticContext,
) -> List[TrackingJourney]:
    """Run the rule engine over every journey and return new journeys with
    `.status`/`.diagnosis` populated (TrackingJourney is frozen; this
    returns replacements rather than mutating in place)."""
    diagnosed = []
    for journey in journeys:
        diagnoses = diagnose_journey(journey, ctx)
        diagnosed.append(journey.with_diagnosis(primary_diagnosis(diagnoses)))
    return diagnosed


def render_terminal_report(
    journeys: List[TrackingJourney],
    untested: Optional[List[TrackingRecommendation]] = None,
    verbose: bool = False,
    extra_findings: Optional[List[Diagnosis]] = None,
    state_diffs: Optional[List[StateDiff]] = None,
) -> str:
    untested = untested or []
    summary = compute_health_summary(journeys, untested)
    critical = [j for j in journeys if j.status == "critical"]
    warnings = [j for j in journeys if j.status == "warning"]

    lines = ["PyTagManager Tracking Health", "=" * 29, ""]
    lines.append(f"Pages tested: {summary.pages_tested}")
    lines.append(f"Tracking journeys: {summary.journeys_total}")
    lines.append("")
    lines.append(f"\U0001F534 {summary.critical} Critical")
    lines.append(f"\U0001F7E0 {summary.warnings} Warnings")
    lines.append(f"\U0001F7E2 {summary.healthy} Healthy")
    lines.append("")

    if critical:
        lines.append("CRITICAL")
        lines.append("-" * 8)
        lines.append("")
        for index, journey in enumerate(critical, start=1):
            lines.extend(_render_journey(index, journey))

    if warnings:
        lines.append("WARNINGS")
        lines.append("-" * 8)
        lines.append("")
        for index, journey in enumerate(warnings, start=1):
            lines.extend(_render_journey(index, journey))

    if extra_findings:
        lines.append("ADDITIONAL FINDINGS")
        lines.append("-" * 19)
        for finding in extra_findings:
            lines.append(f"  - [{finding.confidence}] {finding.message}")
        lines.append("")

    non_empty_diffs = [d for d in (state_diffs or []) if not d.is_empty]
    if non_empty_diffs:
        lines.append("RUNTIME STATE CHANGES")
        lines.append("-" * 22)
        for diff in non_empty_diffs:
            lines.append(f"  {diff.before_label} -> {diff.after_label}")
            lines.extend(_render_state_diff_changes(diff))
        lines.append("")

    if verbose and untested:
        lines.append("UNTESTED (static candidates found, no runtime confirmation)")
        lines.append("-" * 59)
        for rec in untested:
            lines.append(f"  - {rec.event_name} via {rec.selector} ({rec.page_url})")
        lines.append("")

    lines.append(f"Event coverage: {summary.event_coverage:.0%}")
    lines.append(f"Duplicate rate: {summary.duplicate_rate:.1%}")
    lines.append(f"Missing-event rate: {summary.missing_event_rate:.1%}")

    return "\n".join(lines)


def _render_state_diff_changes(diff: StateDiff) -> List[str]:
    lines = []
    categories = [
        ("cookies", diff.cookies_added, diff.cookies_removed, diff.cookies_modified),
        ("localStorage", diff.local_storage_added, diff.local_storage_removed, diff.local_storage_modified),
        ("sessionStorage", diff.session_storage_added, diff.session_storage_removed, diff.session_storage_modified),
    ]
    for label, added, removed, modified in categories:
        for key in added:
            lines.append(f"    + {label}.{key}")
        for key in removed:
            lines.append(f"    - {label}.{key}")
        for key in modified:
            lines.append(f"    ~ {label}.{key}")
    for event_name in diff.new_data_layer_events:
        lines.append(f"    + dataLayer event: {event_name or '(unnamed)'}")
    return lines


def _render_journey(index: int, journey: TrackingJourney) -> List[str]:
    lines = [f"{index}. {journey.business_event}", ""]
    for stage in STAGES:
        mark = "✓" if journey.stage_present(stage) else "✗"
        lines.append(f"   {_STAGE_LABELS[stage]:<22} {mark}")
    lines.append("")
    if journey.diagnosis:
        lines.append(f"   Root cause ({journey.diagnosis.confidence}):")
        lines.append(f"   {journey.diagnosis.message}")
    lines.append("")
    return lines
