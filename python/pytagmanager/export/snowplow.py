"""Snowplow exporter: builds real Iglu self-describing JSON Schemas
(https://docs.snowplow.io/docs/pipeline-components-and-applications/iglu/common-architecture/self-describing-json-schemas/)
for each recommended event -- Snowplow's actual event-definition unit -- plus
one example self-describing event instance per recommendation, in the shape
a Snowplow tracker would emit
(https://docs.snowplow.io/docs/collecting-data/collecting-from-own-applications/snowplow-tracker-protocol/).

Snowplow has no "GTM-style container" concept: custom events are always
modeled as versioned JSON Schemas registered in an Iglu schema registry, so
that's the artifact this exporter produces (grouped by canonical event so
two recommendations for the same kind of event share one schema, matching
how Snowplow schemas are meant to be reused, not one-per-DOM-element).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import List

from pytagmanager.export._taxonomy import canonical_event
from pytagmanager.recommend.models import TrackingRecommendation

_IGLU_VENDOR = "com.pytagmanager"
_SCHEMA_VERSION = "1-0-0"


def _self_describing_schema(event_key: str) -> dict:
    """A real Iglu self-describing JSON Schema document (draft-04 based,
    per Snowplow's `self-desc` meta-schema)."""
    return {
        "$schema": "http://iglucentral.com/schemas/com.snowplowanalytics.self-desc/schema/jsonschema/1-0-0#",
        "description": f"PyTagManager-recommended '{event_key}' event.",
        "self": {
            "vendor": _IGLU_VENDOR,
            "name": event_key,
            "format": "jsonschema",
            "version": _SCHEMA_VERSION,
        },
        "type": "object",
        "properties": {
            "selector": {"type": "string"},
            "trigger_type": {"type": "string"},
            "business_objective": {"type": "string"},
            "confidence": {"type": "number", "minimum": 0, "maximum": 1},
            "page_url": {"type": "string"},
        },
        "required": ["selector", "trigger_type", "business_objective"],
        "additionalProperties": False,
    }


def _schema_uri(event_key: str) -> str:
    return f"iglu:{_IGLU_VENDOR}/{event_key}/jsonschema/{_SCHEMA_VERSION}"


def build_snowplow_schemas(recommendations: List[TrackingRecommendation]) -> dict:
    """Build `{"schemas": {event_key: <self-describing schema>}, "events": [<tracker payload>]}`.

    `schemas` is de-duplicated per canonical event key (Snowplow schemas are
    registered once and reused); `events` has one self-describing event
    instance per recommendation, in the real `unstruct_event` envelope shape
    a Snowplow tracker's `trackSelfDescribingEvent` call produces.
    """
    schemas: dict = {}
    events = []

    for rec in recommendations:
        event_key = canonical_event(rec)
        if event_key not in schemas:
            schemas[event_key] = _self_describing_schema(event_key)

        events.append(
            {
                "schema": "iglu:com.snowplowanalytics.snowplow/unstruct_event/jsonschema/1-0-0",
                "data": {
                    "schema": _schema_uri(event_key),
                    "data": {
                        "selector": rec.selector,
                        "trigger_type": rec.trigger_type,
                        "business_objective": rec.business_objective,
                        "confidence": rec.confidence,
                        "page_url": rec.page_url,
                    },
                },
            }
        )

    return {"schemas": schemas, "events": events}


def export_snowplow_json(recommendations: List[TrackingRecommendation], path: str) -> None:
    doc = build_snowplow_schemas(recommendations)
    Path(path).write_text(json.dumps(doc, indent=2))
