"""Tealium exporter: builds a Tealium iQ Tag Management "profile" export
using Tealium's own documented concepts -- the Universal Data Object (UDO,
the `utag_data` object Tealium's tracker reads on every event,
https://docs.tealium.com/platforms/javascript/data-layer/) and Load Rules
(the condition sets that gate whether a tag fires,
https://docs.tealium.com/platforms/tags-load-rules/load-rules/), rather than
GTM's tag/trigger vocabulary, since Tealium iQ is structured differently:
every event is a `utag.link()`/`utag.view()` call carrying a UDO payload,
and Load Rules decide which tags respond to it.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import List

from pytagmanager.export._taxonomy import canonical_event
from pytagmanager.recommend.models import TrackingRecommendation


def build_tealium_profile(recommendations: List[TrackingRecommendation]) -> dict:
    """Build `{"udo_events": [...], "load_rules": [...]}`.

    Each `udo_events` entry is a `utag.link()` call payload: `tealium_event`
    (Tealium's own name for the event-name field) plus business-context UDO
    variables. Each `load_rules` entry is a Tealium Load Rule keyed off
    `tealium_event equals <name>`, the standard Tealium pattern for gating a
    tag to one specific event.
    """
    udo_events = []
    load_rules = []

    for i, rec in enumerate(recommendations, start=1):
        event_name = canonical_event(rec)

        udo_events.append(
            {
                "call_type": "link",
                "tealium_event": event_name,
                "udo": {
                    "event_category": rec.event_category,
                    "business_objective": rec.business_objective,
                    "confidence": rec.confidence,
                    "page_url": rec.page_url,
                    "dom_selector": rec.selector,
                    "dom_selector_fallbacks": rec.selector_fallbacks,
                },
            }
        )

        load_rules.append(
            {
                "id": f"lr_{i}",
                "name": f"{event_name} - {rec.trigger_type}",
                "conditions": [
                    {"variable": "tealium_event", "operator": "equals", "value": event_name},
                ],
            }
        )

    return {"udo_events": udo_events, "load_rules": load_rules}


def export_tealium_json(recommendations: List[TrackingRecommendation], path: str) -> None:
    profile = build_tealium_profile(recommendations)
    Path(path).write_text(json.dumps(profile, indent=2))
