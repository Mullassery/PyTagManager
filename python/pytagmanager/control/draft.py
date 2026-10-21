"""Explicit discovery-recommendation to draft-config conversion."""

from __future__ import annotations

import copy
from dataclasses import dataclass
from typing import Any, Iterable, Mapping

from pytagmanager.control.config import ConfigPayload, Tag, Trigger
from pytagmanager.control.errors import ValidationError

_TRIGGER_TYPE_MAP = {
    "click": "click",
    "submit": "form_submit",
    "form_submit": "form_submit",
    "page_view": "page_view",
    "route_change": "route_change",
}


@dataclass(frozen=True)
class DraftConversion:
    tag: Tag
    trigger: Trigger
    warnings: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "tag": self.tag.to_dict(),
            "trigger": self.trigger.to_dict(),
            "warnings": list(self.warnings),
        }


@dataclass(frozen=True)
class DraftPayload:
    payload: ConfigPayload
    warnings: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "payload": self.payload.to_dict(),
            "warnings": list(self.warnings),
        }


def _as_mapping(recommendation: Any) -> dict[str, Any]:
    if isinstance(recommendation, Mapping):
        data = copy.deepcopy(dict(recommendation))
    else:
        data = {
            "event_name": getattr(recommendation, "event_name", None),
            "trigger_type": getattr(recommendation, "trigger_type", None),
            "selector": getattr(recommendation, "selector", None),
            "selector_fallbacks": list(getattr(recommendation, "selector_fallbacks", ()) or ()),
            "event_category": getattr(recommendation, "event_category", ""),
            "business_objective": getattr(recommendation, "business_objective", ""),
            "confidence": getattr(recommendation, "confidence", 0.0),
            "rationale": getattr(recommendation, "rationale", ""),
            "page_url": getattr(recommendation, "page_url", ""),
        }
    event_name = data.get("event_name")
    selector = data.get("selector")
    if not isinstance(event_name, str) or not event_name:
        raise ValidationError("recommendation.event_name must be a non-empty string")
    if not isinstance(selector, str) or not selector:
        raise ValidationError("recommendation.selector must be a non-empty string")
    data.setdefault("trigger_type", "custom_event")
    data.setdefault("selector_fallbacks", [])
    data.setdefault("event_category", "")
    data.setdefault("business_objective", "")
    data.setdefault("confidence", 0.0)
    data.setdefault("rationale", "")
    data.setdefault("page_url", "")
    return data


def _warnings_for(data: Mapping[str, Any], destination_ids, consent_purpose) -> list[str]:
    warnings = []
    if not destination_ids:
        warnings.append("No destination selected; the draft has no destination_ids.")
    if consent_purpose is None:
        warnings.append("No consent purpose declared; the draft is not consent-gated.")
    confidence = data.get("confidence")
    if isinstance(confidence, (int, float)) and confidence < 0.7:
        warnings.append("Low discovery confidence; review before approval.")
    selector = data.get("selector", "")
    if isinstance(selector, str) and (">" in selector or ":nth-child" in selector):
        warnings.append("Selector is positional and may be brittle across page changes.")
    if not data.get("page_url"):
        warnings.append("Recommendation has no source page URL.")
    return warnings


def draft_from_recommendation(
    recommendation: Any,
    *,
    adapter_key: str = "ga4_event",
    destination_ids: Iterable[str] = (),
    consent_purpose: str | None = None,
) -> DraftConversion:
    data = _as_mapping(recommendation)
    destination_ids = tuple(destination_ids)
    event_name = data["event_name"]
    trigger_type = _TRIGGER_TYPE_MAP.get(str(data["trigger_type"]), "custom_event")
    trigger = Trigger.create(
        name=f"{event_name} - {trigger_type}",
        type=trigger_type,
        conditions={
            "op": "equals",
            "path": "event.name",
            "value": event_name,
        },
    )
    warnings = _warnings_for(data, destination_ids, consent_purpose)
    evidence = {
        "recommendation": copy.deepcopy(data),
        "warnings": warnings,
    }
    tag = Tag.create(
        name=event_name,
        type=adapter_key,
        description=str(data.get("rationale", "")),
        parameters={
            "event_name": event_name,
            "event_category": data.get("event_category", ""),
            "business_objective": data.get("business_objective", ""),
        },
        trigger_ids=(trigger.trigger_id,),
        consent_purpose=consent_purpose,
        destination_ids=destination_ids,
        source_evidence=evidence,
    )
    return DraftConversion(tag=tag, trigger=trigger, warnings=tuple(warnings))


def draft_payload_from_recommendations(
    recommendations: Iterable[Any],
    *,
    adapter_key: str = "ga4_event",
    destination_ids: Iterable[str] = (),
    consent_purpose: str | None = None,
) -> DraftPayload:
    destination_ids = tuple(destination_ids)
    tags = []
    triggers = []
    warnings = []
    seen = set()
    for recommendation in recommendations:
        data = _as_mapping(recommendation)
        identity = (data["event_name"], data["selector"])
        if identity in seen:
            warnings.append(
                f"Duplicate recommendation {data['event_name']}@{data['selector']} was skipped."
            )
            continue
        seen.add(identity)
        conversion = draft_from_recommendation(
            data,
            adapter_key=adapter_key,
            destination_ids=destination_ids,
            consent_purpose=consent_purpose,
        )
        tags.append(conversion.tag)
        triggers.append(conversion.trigger)
        warnings.extend(conversion.warnings)
    if not tags:
        raise ValidationError("no recommendations were provided for draft conversion")
    return DraftPayload(
        payload=ConfigPayload(tags=tuple(tags), triggers=tuple(triggers)),
        warnings=tuple(dict.fromkeys(warnings)),
    )
