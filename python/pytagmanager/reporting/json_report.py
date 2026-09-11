"""Versioned machine-readable JSON report (spec section 14). Secondary to
the terminal report, not the default -- `schema_version` lets this evolve
without silently breaking consumers pinned to an earlier shape.
"""

from __future__ import annotations

from typing import List, Optional

from pytagmanager.correlation.journey import TrackingJourney
from pytagmanager.diagnostics.models import Diagnosis
from pytagmanager.observability.state import StateDiff
from pytagmanager.recommend.models import TrackingRecommendation
from pytagmanager.reporting.summary import compute_health_summary

JSON_SCHEMA_VERSION = 1


def build_json_report(
    journeys: List[TrackingJourney],
    untested: Optional[List[TrackingRecommendation]] = None,
    extra_findings: Optional[List[Diagnosis]] = None,
    state_diffs: Optional[List[StateDiff]] = None,
) -> dict:
    untested = untested or []
    extra_findings = extra_findings or []
    state_diffs = state_diffs or []
    summary = compute_health_summary(journeys, untested)
    return {
        "schema_version": JSON_SCHEMA_VERSION,
        "summary": {
            "pages_tested": summary.pages_tested,
            "journeys_total": summary.journeys_total,
            "healthy": summary.healthy,
            "warnings": summary.warnings,
            "failed": summary.critical,
            "event_coverage": round(summary.event_coverage, 4),
            "duplicate_rate": round(summary.duplicate_rate, 4),
            "missing_event_rate": round(summary.missing_event_rate, 4),
        },
        "diagnostics": [
            {
                "journey_id": journey.journey_id,
                "event": journey.business_event,
                "severity": journey.status,
                "status": "healthy" if journey.status == "healthy" else "failed",
                "root_cause": journey.diagnosis.root_cause if journey.diagnosis else "none",
                "message": journey.diagnosis.message if journey.diagnosis else "",
                "confidence": journey.diagnosis.confidence if journey.diagnosis else "Confirmed",
                "stages": journey.stages,
                "details": journey.diagnosis.details if journey.diagnosis else {},
            }
            for journey in journeys
        ],
        "untested_candidates": [
            {"event_name": rec.event_name, "selector": rec.selector, "page_url": rec.page_url} for rec in untested
        ],
        "additional_findings": [
            {
                "root_cause": finding.root_cause,
                "severity": finding.severity,
                "confidence": finding.confidence,
                "message": finding.message,
                "details": finding.details,
            }
            for finding in extra_findings
        ],
        "runtime_state_diffs": [
            {
                "before": diff.before_label,
                "after": diff.after_label,
                "cookies_added": diff.cookies_added,
                "cookies_removed": diff.cookies_removed,
                "cookies_modified": diff.cookies_modified,
                "local_storage_added": diff.local_storage_added,
                "local_storage_removed": diff.local_storage_removed,
                "local_storage_modified": diff.local_storage_modified,
                "session_storage_added": diff.session_storage_added,
                "session_storage_removed": diff.session_storage_removed,
                "session_storage_modified": diff.session_storage_modified,
                "new_data_layer_events": diff.new_data_layer_events,
            }
            for diff in state_diffs
            if not diff.is_empty
        ],
    }
