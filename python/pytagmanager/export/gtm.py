from __future__ import annotations

import json
from pathlib import Path
from typing import List

from pytagmanager.recommend.models import TrackingRecommendation

_GTM_TRIGGER_TYPE_MAP = {
    "click": "CLICK",
    "submit": "FORM_SUBMISSION",
}


def build_gtm_container(recommendations: List[TrackingRecommendation]) -> dict:
    """Build a minimal, valid-shape GTM container export (tags + triggers +
    variables) from tracking recommendations. This covers the fields needed
    to review and hand-import a v1 recommendation set -- it is not a full
    replica of GTM's export schema; broader field coverage is future work.
    """
    tags = []
    triggers = []

    for i, rec in enumerate(recommendations, start=1):
        trigger_id = f"trigger_{i}"
        tag_id = f"tag_{i}"

        triggers.append(
            {
                "triggerId": trigger_id,
                "name": f"{rec.event_name} - {rec.trigger_type}",
                "type": _GTM_TRIGGER_TYPE_MAP.get(rec.trigger_type, rec.trigger_type.upper()),
                "filter": {
                    "selector": rec.selector,
                    "selectorFallbacks": rec.selector_fallbacks,
                },
            }
        )

        tags.append(
            {
                "tagId": tag_id,
                "name": rec.event_name,
                "type": "gaawe",
                "firingTriggerId": [trigger_id],
                "parameter": {
                    "eventName": rec.event_name,
                    "eventCategory": rec.event_category,
                },
                "metadata": {
                    "businessObjective": rec.business_objective,
                    "confidence": rec.confidence,
                    "rationale": rec.rationale,
                    "pageUrl": rec.page_url,
                },
            }
        )

    return {
        "exportFormatVersion": 2,
        "containerVersion": {
            "tag": tags,
            "trigger": triggers,
            "variable": [],
        },
    }


def export_gtm_json(recommendations: List[TrackingRecommendation], path: str) -> None:
    container = build_gtm_container(recommendations)
    Path(path).write_text(json.dumps(container, indent=2))
