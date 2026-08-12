"""Shared mapping from PyTagManager's internal recommendation taxonomy
(`TrackingRecommendation.business_objective`, set by
`pytagmanager.recommend.heuristics`) to a platform-neutral canonical event
key. Each platform-specific exporter (ga4.py, segment.py, snowplow.py,
tealium.py, rudderstack.py, adobe_tags.py) then maps this canonical key to
that platform's own real, documented event-naming convention -- this file
just avoids duplicating the business_objective -> canonical-event lookup
across six exporters.
"""

from __future__ import annotations

from pytagmanager.recommend.models import TrackingRecommendation

# business_objective (see recommend/heuristics.py's _CTA_KEYWORDS and the
# dedicated "form_submission" case) -> canonical, platform-neutral event key.
CANONICAL_EVENT_MAP = {
    "Purchase Intent": "add_to_cart",
    "Trial Signup": "start_trial",
    "Subscription": "subscribe",
    "Lead Generation": "generate_lead",
    "Authentication": "login",
    "Content Engagement": "content_engagement",
    "Search": "search",
}

DEFAULT_CANONICAL_EVENT = "custom_event"


def canonical_event(rec: TrackingRecommendation) -> str:
    """The canonical, platform-neutral event key for a recommendation.
    Falls back to `DEFAULT_CANONICAL_EVENT` for any business_objective not
    in the map (defensive -- keeps exporters from KeyError'ing if the
    heuristics engine's taxonomy grows without every exporter being
    updated in lockstep)."""
    return CANONICAL_EVENT_MAP.get(rec.business_objective, DEFAULT_CANONICAL_EVENT)
