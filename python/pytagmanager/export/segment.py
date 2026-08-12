"""Segment exporter: builds a Segment Protocols "Tracking Plan" JSON
document, in the shape Segment's Tracking Plan API/import accepts
(https://segment.com/docs/protocols/tracking-plan/), using Segment's
documented Ecommerce Spec v2 event names
(https://segment.com/docs/connections/spec/ecommerce/v2/) where our
taxonomy maps onto one, and Segment's Title-Case object-action naming
convention otherwise.

Each event's `rules` block is a JSON Schema fragment (Segment tracking
plans validate `properties` against JSON Schema) describing the event's
expected properties -- this mirrors the real shape Segment stores/validates
against, not just a flat property list.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import List

from pytagmanager.export._taxonomy import canonical_event
from pytagmanager.recommend.models import TrackingRecommendation

# canonical event key -> (Segment event name, JSON-Schema `properties` dict, required list).
# "Product Added" is Segment's own Ecommerce v2 spec name; the others follow
# Segment's documented Title-Case verb-object naming convention since
# Segment has no single official spec covering lead-gen/auth/content events.
_SEGMENT_EVENT_SPECS = {
    "add_to_cart": (
        "Product Added",
        {"product_id": {"type": "string"}, "cart_id": {"type": "string"}},
        ["product_id"],
    ),
    "start_trial": ("Trial Started", {"plan": {"type": "string"}}, []),
    "subscribe": ("Subscription Started", {"plan": {"type": "string"}}, []),
    "generate_lead": ("Lead Generated", {"lead_source": {"type": "string"}}, []),
    "login": ("Signed In", {"method": {"type": "string"}}, []),
    "content_engagement": ("Content Viewed", {"content_type": {"type": "string"}}, []),
    "search": ("Products Searched", {"query": {"type": "string"}}, []),
}
_DEFAULT_SEGMENT_EVENT = ("Custom Event Triggered", {}, [])


def build_segment_tracking_plan(recommendations: List[TrackingRecommendation]) -> dict:
    """Build a Segment Tracking Plan document: `display_name` + `rules.events[]`,
    each event carrying a JSON-Schema `rules.properties.properties` block
    (Segment's real tracking-plan validation shape) plus a `labels` map used
    here to carry PyTagManager-specific provenance (selector, confidence,
    rationale) that Segment's schema has no native field for.
    """
    events = []
    for rec in recommendations:
        canonical = canonical_event(rec)
        name, props, required = _SEGMENT_EVENT_SPECS.get(canonical, _DEFAULT_SEGMENT_EVENT)

        events.append(
            {
                "name": name,
                "description": rec.rationale,
                "rules": {
                    "properties": {
                        "properties": {
                            "type": "object",
                            "properties": props,
                            "required": required,
                        },
                        "context": {},
                        "traits": {},
                    },
                    "labels": {
                        "pytagmanager_trigger_type": rec.trigger_type,
                        "pytagmanager_selector": rec.selector,
                        "pytagmanager_business_objective": rec.business_objective,
                        "pytagmanager_confidence": str(rec.confidence),
                        "pytagmanager_page_url": rec.page_url,
                    },
                },
                "version": 1,
            }
        )

    return {
        "display_name": "PyTagManager Tracking Plan",
        "rules": {
            "events": events,
            "global": {"properties": {"context": {}, "traits": {}}},
        },
    }


def export_segment_json(recommendations: List[TrackingRecommendation], path: str) -> None:
    plan = build_segment_tracking_plan(recommendations)
    Path(path).write_text(json.dumps(plan, indent=2))
