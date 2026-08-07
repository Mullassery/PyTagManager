from __future__ import annotations

from dataclasses import dataclass
from typing import List


@dataclass
class TrackingRecommendation:
    event_name: str
    trigger_type: str
    selector: str
    selector_fallbacks: List[str]
    event_category: str
    business_objective: str
    confidence: float
    rationale: str
    page_url: str = ""
