"""Adobe Tags (Adobe Experience Platform Tags, formerly "Launch") exporter.

Builds Adobe Launch Rule Components in Launch's real Reactor API rule shape
(https://developer.adobe.com/experience-platform-apis/references/experience-platform-tags/#tag/Rules) --
a rule is `events[]` (what triggers it) + `conditions[]` (gating logic) +
`actions[]` (what it does), where each entry references an extension
"module" by its real Adobe Launch Core Extension module path (the actual
paths Launch's own Core Extension ships:
`core/src/lib/events/click.js`, `core/src/lib/events/formSubmit.js`,
`core/src/lib/actions/customCode.js`) and a `settings` object matching
that module's real settings schema (Core Extension's Click Event settings
take `elementSelector` + `bubbleFireIfParent`, matching the DOM Ready /
Click event settings Launch's UI itself produces).

This is the exporter for Adobe's tag-rule authoring surface, not XDM
schema/event modeling (Adobe Experience Platform's separate, considerably
deeper standardized-schema system) -- XDM-native modeling is out of scope
for this pass; see docs/ARCHITECTURE.md.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import List

from pytagmanager.export._taxonomy import canonical_event
from pytagmanager.recommend.models import TrackingRecommendation

# Real Adobe Launch Core Extension event-module paths, keyed by our
# internal trigger_type ("click" / "submit").
_EVENT_MODULE_PATHS = {
    "click": "core/src/lib/events/click.js",
    "submit": "core/src/lib/events/formSubmit.js",
}
_DEFAULT_EVENT_MODULE_PATH = "core/src/lib/events/click.js"

_ACTION_MODULE_PATH = "core/src/lib/actions/customCode.js"


def _rule_name(rec: TrackingRecommendation) -> str:
    return f"{canonical_event(rec)} - {rec.trigger_type} - {rec.selector}"


def build_adobe_launch_rules(recommendations: List[TrackingRecommendation]) -> dict:
    """Build `{"rules": [<Launch rule component>, ...]}`. Each rule's
    `actions[0]` is a `customCode` action containing a
    `_satellite.track(...)` call stub naming the canonical event and
    carrying PyTagManager's recommendation metadata as a comment -- Launch
    has no native "send this named event with these params" action without
    an analytics extension configured (which varies per Adobe org), so
    `customCode` is the safe, always-valid placeholder a reviewer wires up
    to their actual Adobe Analytics/AEP Web SDK extension action.
    """
    rules = []
    for rec in recommendations:
        event_module = _EVENT_MODULE_PATHS.get(rec.trigger_type, _DEFAULT_EVENT_MODULE_PATH)
        canonical = canonical_event(rec)

        rules.append(
            {
                "name": _rule_name(rec),
                "events": [
                    {
                        "modulePath": event_module,
                        "settings": {
                            "elementSelector": rec.selector,
                            "bubbleFireIfParent": False,
                        },
                    }
                ],
                "conditions": [],
                "actions": [
                    {
                        "modulePath": _ACTION_MODULE_PATH,
                        "settings": {
                            "language": "javascript",
                            "source": (
                                f"// PyTagManager recommendation: {rec.business_objective} "
                                f"(confidence={rec.confidence})\n"
                                f"// {rec.rationale}\n"
                                f'_satellite.track("{canonical}", '
                                f'{{ selector: "{rec.selector}", pageUrl: "{rec.page_url}" }});'
                            ),
                        },
                    }
                ],
            }
        )

    return {"rules": rules}


def export_adobe_tags_json(recommendations: List[TrackingRecommendation], path: str) -> None:
    doc = build_adobe_launch_rules(recommendations)
    Path(path).write_text(json.dumps(doc, indent=2))
