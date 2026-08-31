"""Normalized shapes for GTM/GA4 live configuration, shared by
gtm_client.py, ga4_client.py, and diagnostics.rules -- the "what should
happen" side of a diagnosis, sourced from the real APIs rather than a
hand-authored expectation file.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass(frozen=True)
class GtmTrigger:
    trigger_id: str
    name: str
    type: str
    # The literal dataLayer event name this trigger matches (extracted from
    # a CUSTOM_EVENT trigger's customEventFilter), or None for trigger types
    # that don't gate on one (e.g. a plain CLICK trigger).
    event_name: Optional[str] = None


@dataclass(frozen=True)
class GtmTag:
    tag_id: str
    name: str
    type: str
    firing_trigger_ids: List[str] = field(default_factory=list)
    parameters: Dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class Ga4CustomDimension:
    parameter_name: str
    display_name: str
    scope: str  # "EVENT" | "USER"


@dataclass(frozen=True)
class Ga4EventDefinition:
    event_name: str
    custom: bool = True
