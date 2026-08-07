from __future__ import annotations

from typing import List, Protocol

from pytagmanager.recommend.models import TrackingRecommendation


class Exporter(Protocol):
    """Interface every tracking-config exporter implements. v1 ships one
    implementation (`pytagmanager.export.gtm`); GA4, Segment, Snowplow,
    Adobe Tags, Tealium, etc. are future work plugging into this same seam.
    """

    def export(self, recommendations: List[TrackingRecommendation]) -> dict: ...
