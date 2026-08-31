"""Event correlation engine: groups the flat TrackingEvent stream a session
produces into TrackingJourney records -- one logical business action
(interaction -> DOM mutation -> dataLayer -> GTM -> analytics network
request) per journey, per docs/ARCHITECTURE.md's Tracking Observability
capability.

Correlation is time-window-based, anchored on user-interaction events
(click/submit/change): each interaction starts a new journey, and events
between that interaction and either the next interaction or the
correlation window's end are attributed to it. This is deliberately not
"everything in the same N seconds is related" -- interaction anchors give
correlation a causal starting point, and the window bounds how long a
downstream effect can plausibly take.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field, replace
from typing import TYPE_CHECKING, List, Optional

from pytagmanager.observability.events import TrackingEvent

if TYPE_CHECKING:
    # Deferred to a type-checking-only import: pytagmanager.diagnostics
    # (via its __init__) imports pytagmanager.diagnostics.rules, which
    # imports this module -- a real runtime import here would be circular.
    from pytagmanager.diagnostics.models import Diagnosis

DEFAULT_CORRELATION_WINDOW_SECONDS = 5.0

STAGES = ("interaction", "mutation", "application", "datalayer", "gtm", "network")

_INTERACTION_TYPES = frozenset({"click", "submit", "change"})
_STAGE_BY_EVENT_TYPE = {
    "click": "interaction",
    "submit": "interaction",
    "change": "interaction",
    "dom_insert": "mutation",
    "dom_remove": "mutation",
    "api_call": "application",
    "datalayer_push": "datalayer",
    "gtm_event": "gtm",
    "network_request": "network",
}


@dataclass(frozen=True)
class TrackingJourney:
    journey_id: str
    business_event: str
    start_time: float
    end_time: float
    observations: List[TrackingEvent] = field(default_factory=list)
    status: str = "unknown"  # healthy | warning | failed | unknown
    diagnosis: Optional[Diagnosis] = None

    def stage_present(self, stage: str) -> bool:
        return any(_STAGE_BY_EVENT_TYPE.get(o.event_type) == stage for o in self.observations)

    @property
    def anchor_selector(self) -> Optional[str]:
        """The selector of the interaction that started this journey.
        Stable regardless of what happened downstream -- unlike
        `business_event` (inferred from the *observed* dataLayer/GTM event
        name), this is safe to use as a join key for "what should have
        happened" lookups even when the runtime event name mismatches what
        was expected.
        """
        return self.observations[0].selector if self.observations else None

    @property
    def stages(self) -> dict:
        return {stage: self.stage_present(stage) for stage in STAGES}

    def events_of_type(self, event_type: str) -> List[TrackingEvent]:
        return [o for o in self.observations if o.event_type == event_type]

    def with_diagnosis(self, diagnosis: Diagnosis) -> "TrackingJourney":
        return replace(self, status=diagnosis.severity, diagnosis=diagnosis)


def _infer_business_event(anchor: TrackingEvent, related: List[TrackingEvent]) -> str:
    for event in related:
        if event.event_type == "datalayer_push" and event.event_name:
            return event.event_name
    for event in related:
        if event.event_type == "gtm_event" and event.event_name and not event.event_name.startswith("gtm."):
            return event.event_name
    return f"{anchor.event_type}:{anchor.selector or anchor.event_name or 'unknown'}"


def correlate_events(
    events: List[TrackingEvent],
    window_seconds: float = DEFAULT_CORRELATION_WINDOW_SECONDS,
) -> List[TrackingJourney]:
    """Partition `events` (typically `ObservationSession.events`) into one
    TrackingJourney per user interaction, attributing every downstream
    event within `window_seconds` (and before the next interaction) to it.
    """
    ordered = sorted(events, key=lambda e: e.timestamp)
    anchors = [e for e in ordered if e.event_type in _INTERACTION_TYPES]
    journeys: List[TrackingJourney] = []

    for index, anchor in enumerate(anchors):
        window_end = anchor.timestamp + window_seconds
        next_anchor_time = anchors[index + 1].timestamp if index + 1 < len(anchors) else None
        boundary = window_end if next_anchor_time is None else min(window_end, next_anchor_time)

        related = [
            event
            for event in ordered
            if anchor.timestamp <= event.timestamp < boundary
            and (event is anchor or event.event_type not in _INTERACTION_TYPES)
        ]

        journeys.append(
            TrackingJourney(
                journey_id=str(uuid.uuid4()),
                business_event=_infer_business_event(anchor, related),
                start_time=anchor.timestamp,
                end_time=related[-1].timestamp if related else anchor.timestamp,
                observations=related,
            )
        )

    return journeys
