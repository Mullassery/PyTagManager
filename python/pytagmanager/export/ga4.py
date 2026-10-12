"""GA4 (Google Analytics 4) exporter.

Builds a config in the shape of a GA4 Measurement Protocol event batch
(https://developers.google.com/analytics/devguides/collection/protocol/ga4/reference/events),
using GA4's own documented "recommended events" names and parameters
(https://developers.google.com/analytics/devguides/collection/ga4/reference/events)
wherever our internal recommendation taxonomy has a real GA4 equivalent,
falling back to a custom event (GA4 supports arbitrary custom event names
outside the recommended list) otherwise.

This is a config/import artifact, not a live API call -- no measurement ID
or API secret is required to generate it, matching every other exporter in
this package.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import List

from pytagmanager.export._taxonomy import canonical_event
from pytagmanager.recommend.models import TrackingRecommendation

# canonical event key -> (GA4 event name, param builder).
# Event names and their parameter sets are GA4's documented recommended
# events; https://developers.google.com/analytics/devguides/collection/ga4/reference/events
_GA4_EVENT_SPECS = {
    "add_to_cart": ("add_to_cart", {"currency": "USD", "value": 0.0, "items": []}),
    "start_trial": ("sign_up", {"method": "trial"}),
    "subscribe": ("sign_up", {"method": "subscription"}),
    "generate_lead": ("generate_lead", {"currency": "USD", "value": 0.0}),
    "login": ("login", {"method": "site"}),
    "content_engagement": ("select_content", {"content_type": "", "item_id": ""}),
    "search": ("search", {"search_term": ""}),
    # Phase 1.8 taxonomy (docs/VISION.md §14): the newer interactive-element
    # objectives. GA4 has a documented recommended event for cart/wishlist/
    # video; the content-discovery/pagination/navigation/modal objectives
    # have no GA4 recommended event of their own so they reuse GA4's
    # `select_content` (its generic recommended "user selected content"
    # event) with a content_type that distinguishes them.
    "remove_from_cart": ("remove_from_cart", {"currency": "USD", "value": 0.0, "items": []}),
    "add_to_wishlist": ("add_to_wishlist", {"currency": "USD", "value": 0.0, "items": []}),
    "content_discovery": ("select_content", {"content_type": "results", "item_id": ""}),
    "pagination": ("select_content", {"content_type": "pagination", "item_id": ""}),
    "video_engagement": ("video_start", {"video_title": "", "video_current_time": 0.0}),
    "navigation": ("select_content", {"content_type": "navigation", "item_id": ""}),
    "modal_interaction": ("select_content", {"content_type": "modal", "item_id": ""}),
}
_DEFAULT_GA4_EVENT_NAME = "select_content"


def build_ga4_config(recommendations: List[TrackingRecommendation]) -> dict:
    """Build a GA4 event-configuration export: one entry per recommendation,
    each shaped like a GA4 Measurement Protocol event (`name` + `params`),
    using GA4's recommended-event names/params where our taxonomy maps to
    one, plus PyTagManager-specific metadata (selector, confidence,
    rationale) needed to review/wire the event client-side via gtag.js or
    a dataLayer push -- GA4 itself has no concept of a DOM selector, so
    that lives under `_pytagmanager`, mirroring how gtm.py keeps
    non-native fields under `metadata`.
    """
    events = []
    for rec in recommendations:
        canonical = canonical_event(rec)
        ga4_name, base_params = _GA4_EVENT_SPECS.get(canonical, (_DEFAULT_GA4_EVENT_NAME, {}))
        params = dict(base_params)
        params["event_category"] = rec.event_category

        events.append(
            {
                "name": ga4_name,
                "params": params,
                "_pytagmanager": {
                    "triggerType": rec.trigger_type,
                    "selector": rec.selector,
                    "selectorFallbacks": rec.selector_fallbacks,
                    "businessObjective": rec.business_objective,
                    "confidence": rec.confidence,
                    "rationale": rec.rationale,
                    "pageUrl": rec.page_url,
                },
            }
        )

    return {
        "measurementProtocolVersion": "2",
        "events": events,
    }


def export_ga4_json(recommendations: List[TrackingRecommendation], path: str) -> None:
    config = build_ga4_config(recommendations)
    Path(path).write_text(json.dumps(config, indent=2))
