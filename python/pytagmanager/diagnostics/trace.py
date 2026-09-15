"""Formalized Interaction Trace (docs/VISION.md §14, Phase 1.8 item 6):
Finding -> Interaction -> Element -> Timestamp -> JS event -> dataLayer
event -> storage change -> network request, as an explicit, serializable,
drillable object.

Mostly a presentation layer over what `TrackingJourney` (+ its optional
`Diagnosis`) and Phase 1.6's `StateDiff` already carry, not new capture
logic -- this module orders a journey's existing observations into steps
and, when a correlated `StateDiff` is supplied (see
`diagnostics.rules.DiagnosticContext.state_diff_for_journey`, the same
join key Phase 1.8 item 4's timing-delay rule uses), adds the storage
change VISION.md's chain calls for.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from pytagmanager.correlation.journey import TrackingJourney, stage_for_event_type
from pytagmanager.observability.state import StateDiff


@dataclass(frozen=True)
class InteractionTraceStep:
    stage: str
    event_type: str
    event_name: str
    timestamp: float
    source: str
    selector: Optional[str]
    payload: Dict[str, Any]


@dataclass(frozen=True)
class StorageChange:
    category: str  # "cookie" | "local_storage" | "session_storage"
    key: str
    change: str  # "added" | "removed" | "modified"


@dataclass(frozen=True)
class InteractionTrace:
    journey_id: str
    business_event: str
    page_url: str
    element_selector: Optional[str]
    start_time: float
    end_time: float
    status: str
    finding: Optional[str] = None
    confidence: Optional[str] = None
    steps: Tuple[InteractionTraceStep, ...] = field(default_factory=tuple)
    storage_changes: Tuple[StorageChange, ...] = field(default_factory=tuple)
    new_data_layer_events: Tuple[str, ...] = field(default_factory=tuple)


_STORAGE_FIELDS = (
    ("cookie", "cookies_added", "added"),
    ("cookie", "cookies_removed", "removed"),
    ("cookie", "cookies_modified", "modified"),
    ("local_storage", "local_storage_added", "added"),
    ("local_storage", "local_storage_removed", "removed"),
    ("local_storage", "local_storage_modified", "modified"),
    ("session_storage", "session_storage_added", "added"),
    ("session_storage", "session_storage_removed", "removed"),
    ("session_storage", "session_storage_modified", "modified"),
)


def _storage_changes(state_diff: Optional[StateDiff]) -> Tuple[StorageChange, ...]:
    if state_diff is None:
        return ()
    changes = []
    for category, attr, change in _STORAGE_FIELDS:
        for key in getattr(state_diff, attr):
            changes.append(StorageChange(category=category, key=key, change=change))
    return tuple(changes)


def build_interaction_trace(journey: TrackingJourney, state_diff: Optional[StateDiff] = None) -> InteractionTrace:
    steps = tuple(
        InteractionTraceStep(
            stage=stage_for_event_type(obs.event_type),
            event_type=obs.event_type,
            event_name=obs.event_name,
            timestamp=obs.timestamp,
            source=obs.source,
            selector=obs.selector,
            payload=obs.payload,
        )
        for obs in sorted(journey.observations, key=lambda o: o.timestamp)
    )
    diagnosis = journey.diagnosis
    return InteractionTrace(
        journey_id=journey.journey_id,
        business_event=journey.business_event,
        page_url=journey.observations[0].page_url if journey.observations else "",
        element_selector=journey.anchor_selector,
        start_time=journey.start_time,
        end_time=journey.end_time,
        status=journey.status,
        finding=diagnosis.message if diagnosis else None,
        confidence=diagnosis.confidence if diagnosis else None,
        steps=steps,
        storage_changes=_storage_changes(state_diff),
        new_data_layer_events=tuple(state_diff.new_data_layer_events) if state_diff else (),
    )


def render_interaction_trace(trace: InteractionTrace) -> str:
    lines = [f"Interaction Trace: {trace.business_event} [{trace.status}]"]
    lines.append(f"  Page: {trace.page_url}")
    lines.append(f"  Element: {trace.element_selector or '(unknown)'}")
    if trace.finding:
        lines.append(f"  Finding ({trace.confidence}): {trace.finding}")
    lines.append("  Timeline:")
    for step in trace.steps:
        name = f" '{step.event_name}'" if step.event_name else ""
        lines.append(f"    [{step.timestamp:.3f}] {step.stage}: {step.event_type}{name} (selector={step.selector})")
    if trace.storage_changes:
        lines.append("  Storage changes:")
        for change in trace.storage_changes:
            lines.append(f"    {change.change} {change.category}.{change.key}")
    if trace.new_data_layer_events:
        lines.append("  New dataLayer events observed in the correlated state diff:")
        for name in trace.new_data_layer_events:
            lines.append(f"    {name or '(unnamed)'}")
    return "\n".join(lines)


def build_interaction_trace_json(trace: InteractionTrace) -> dict:
    return {
        "journey_id": trace.journey_id,
        "business_event": trace.business_event,
        "page_url": trace.page_url,
        "element_selector": trace.element_selector,
        "start_time": trace.start_time,
        "end_time": trace.end_time,
        "status": trace.status,
        "finding": trace.finding,
        "confidence": trace.confidence,
        "steps": [
            {
                "stage": step.stage,
                "event_type": step.event_type,
                "event_name": step.event_name,
                "timestamp": step.timestamp,
                "source": step.source,
                "selector": step.selector,
                "payload": step.payload,
            }
            for step in trace.steps
        ],
        "storage_changes": [
            {"category": c.category, "key": c.key, "change": c.change} for c in trace.storage_changes
        ],
        "new_data_layer_events": list(trace.new_data_layer_events),
    }


def build_interaction_traces(
    journeys: List[TrackingJourney], state_diffs_by_journey_id: Optional[Dict[str, StateDiff]] = None
) -> List[InteractionTrace]:
    state_diffs_by_journey_id = state_diffs_by_journey_id or {}
    return [
        build_interaction_trace(journey, state_diffs_by_journey_id.get(journey.journey_id))
        for journey in journeys
    ]
