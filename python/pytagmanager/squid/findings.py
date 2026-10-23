"""Versioned PyTagManager findings contract for Squid-CRM custom objects.

This module defines the PyTagManager side of the Squid custom-object contract.
It does not perform network writes and does not assume a live Squid workspace.
A write plan is emitted for a Squid adapter to execute after metadata creation,
API-key authorization and a live contract test.
"""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any, Mapping
from urllib.parse import urlsplit, urlunsplit

CONTRACT_VERSION = 1
CONTRACT_ID = "pytagmanager.squid.tag-finding.v1"
OBJECT_NAME_SINGULAR = "tagManagerFinding"
OBJECT_NAME_PLURAL = "tagManagerFindings"
LABEL_SINGULAR = "Tag Manager Finding"
LABEL_PLURAL = "Tag Manager Findings"
OBJECT_ICON = "IconAlertTriangle"

SEVERITIES = frozenset({"critical", "warning", "unknown"})
CONFIDENCES = frozenset({"Confirmed", "Highly likely", "Possible", "Needs investigation"})

FIELD_DEFINITIONS = (
    {
        "name": "findingId",
        "label": "Finding ID",
        "type": "TEXT",
        "isNullable": False,
        "isUnique": True,
        "isSearchable": True,
        "description": "Stable PyTagManager finding identity.",
    },
    {
        "name": "ruleId",
        "label": "Rule ID",
        "type": "TEXT",
        "isNullable": False,
        "isSearchable": True,
        "description": "Machine-readable diagnostic rule or root-cause identifier.",
    },
    {
        "name": "rootCause",
        "label": "Root Cause",
        "type": "TEXT",
        "isNullable": False,
        "isSearchable": True,
        "description": "Root-cause slug emitted by PyTagManager.",
    },
    {
        "name": "severity",
        "label": "Severity",
        "type": "TEXT",
        "isNullable": False,
        "description": "PyTagManager severity: critical, warning, or unknown.",
    },
    {
        "name": "confidence",
        "label": "Confidence",
        "type": "TEXT",
        "isNullable": False,
        "description": "Evidence confidence from the diagnostic engine.",
    },
    {
        "name": "message",
        "label": "Message",
        "type": "TEXT",
        "isNullable": False,
        "description": "Plain-language finding summary.",
    },
    {
        "name": "recommendation",
        "label": "Recommendation",
        "type": "TEXT",
        "isNullable": False,
        "description": "Actionable remediation guidance.",
    },
    {
        "name": "pageUrl",
        "label": "Page URL",
        "type": "TEXT",
        "isNullable": True,
        "description": "Page URL without query string or fragment.",
    },
    {
        "name": "selector",
        "label": "Selector",
        "type": "TEXT",
        "isNullable": True,
        "description": "Interaction selector associated with the finding.",
    },
    {
        "name": "tagId",
        "label": "Tag ID",
        "type": "TEXT",
        "isNullable": True,
        "description": "GTM tag identifier when the finding names one.",
    },
    {
        "name": "containerId",
        "label": "Container ID",
        "type": "TEXT",
        "isNullable": True,
        "description": "GTM container identifier when available.",
    },
    {
        "name": "sourceEvent",
        "label": "Source Event",
        "type": "TEXT",
        "isNullable": True,
        "description": "Business event or dataLayer event associated with the finding.",
    },
    {
        "name": "source",
        "label": "Source",
        "type": "TEXT",
        "isNullable": False,
        "description": "PyTagManager report source, e.g. diagnose.",
    },
    {
        "name": "schemaVersion",
        "label": "Schema Version",
        "type": "TEXT",
        "isNullable": False,
        "description": "PyTagManager Squid finding record schema version.",
    },
)

_RECOMMENDATIONS = {
    "missing_datalayer_event": (
        "Verify the interaction handler pushes the expected dataLayer event; check for JS errors "
        "or a missing GTM trigger before re-running diagnose."
    ),
    "event_name_mismatch": (
        "Align the dataLayer event name with the trigger/SDR or update the trigger to the observed "
        "event name."
    ),
    "gtm_tag_not_executed": (
        "Check the GTM trigger conditions and tag firing options for the named tag, then verify the "
        "request in a fresh diagnose run."
    ),
    "missing_ga4_request": (
        "Verify the analytics tag fires and that consent, trigger conditions, or client-side blocking "
        "is not suppressing the network request."
    ),
    "duplicate_datalayer_event": (
        "Remove the duplicate dataLayer push and ensure the interaction handler or GTM tag fires once."
    ),
    "duplicate_analytics_request": (
        "Find the duplicate tag/trigger path and ensure only one analytics request is sent per action."
    ),
    "consent_blocked": (
        "Inspect the CMP state and consent gating; confirm the tag fires only after the required purpose "
        "is granted."
    ),
    "pii_leak_detected": (
        "Remove PII from dataLayer and network payloads; pass only approved identifiers and rerun the "
        "checks."
    ),
    "spa_navigation_missing_pageview": (
        "Push a virtual page_view on SPA route changes and update the GTM history-change trigger."
    ),
    "ecommerce_missing_parameters": (
        "Add the missing ecommerce fields to the dataLayer push before the analytics tag fires."
    ),
    "parameter_loss": (
        "Trace the missing parameter from the dataLayer push through the GTM variable and tag mapping "
        "into the network request."
    ),
    "duplicate_purchase": (
        "Deduplicate purchase events by transaction ID and verify the purchase trigger fires once."
    ),
}


class SquidContractError(ValueError):
    """Raised when a diagnose report or finding record cannot satisfy the contract."""


def recommendation_for_root_cause(root_cause: str) -> str:
    return _RECOMMENDATIONS.get(
        root_cause,
        "Review the finding evidence, fix the named tracking layer, and rerun diagnose to verify.",
    )


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _safe_text(value: Any, limit: int = 500) -> str:
    if value is None:
        return ""
    return str(value).strip()[:limit]


def _safe_url(value: Any) -> str:
    if not isinstance(value, str) or not value:
        return ""
    try:
        parsed = urlsplit(value)
    except ValueError:
        return ""
    return urlunsplit((parsed.scheme, parsed.netloc, parsed.path, "", ""))


def _details(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _finding_id(finding: Mapping[str, Any], source: str) -> str:
    details = _details(finding.get("details"))
    identity = {
        "source": source,
        "event": _safe_text(finding.get("event") or finding.get("event_name"), 200),
        "root_cause": _safe_text(finding.get("root_cause"), 200),
        "message": _safe_text(finding.get("message"), 500),
        "page_url": _safe_url(finding.get("page_url") or details.get("page_url") or details.get("url")),
        "selector": _safe_text(details.get("selector"), 300),
        "tag_id": _safe_text(details.get("tag_id") or details.get("tagId"), 200),
        "container_id": _safe_text(details.get("container_id") or details.get("containerId"), 200),
        "expected_event": _safe_text(details.get("expected_event"), 200),
        "runtime_event": _safe_text(details.get("runtime_event"), 200),
    }
    digest = hashlib.sha256(_canonical(identity).encode("utf-8")).hexdigest()
    return f"ptm_{digest[:24]}"


def diagnosis_to_finding_record(
    finding: Mapping[str, Any],
    *,
    source: str = "diagnose",
) -> dict[str, Any]:
    """Map one diagnose diagnostic/additional finding to a Squid record.

    Raw diagnostic details are used only for identity and selected safe fields;
    they are not copied into the emitted record.
    """
    if not isinstance(finding, Mapping):
        raise SquidContractError("finding must be an object")
    root_cause = _safe_text(finding.get("root_cause"), 200)
    if not root_cause or root_cause == "none":
        raise SquidContractError("finding has no root_cause")
    severity = _safe_text(finding.get("severity"), 50)
    if severity not in SEVERITIES:
        raise SquidContractError(f"unsupported severity: {severity!r}")
    confidence = _safe_text(finding.get("confidence"), 50) or "Needs investigation"
    if confidence not in CONFIDENCES:
        raise SquidContractError(f"unsupported confidence: {confidence!r}")
    details = _details(finding.get("details"))
    event = _safe_text(finding.get("event") or finding.get("event_name"), 200)
    message = _safe_text(finding.get("message"), 500)
    page_url = _safe_url(finding.get("page_url") or details.get("page_url") or details.get("url"))
    selector = _safe_text(details.get("selector"), 300)
    tag_id = _safe_text(details.get("tag_id") or details.get("tagId"), 200)
    container_id = _safe_text(details.get("container_id") or details.get("containerId"), 200)
    record = {
        "name": _safe_text(f"{event + ': ' if event else ''}{message or root_cause}", 200),
        "findingId": _finding_id(finding, source),
        "ruleId": _safe_text(finding.get("rule_id") or root_cause, 200),
        "rootCause": root_cause,
        "severity": severity,
        "confidence": confidence,
        "message": message,
        "recommendation": _safe_text(
            finding.get("recommendation") or recommendation_for_root_cause(root_cause), 1000
        ),
        "sourceEvent": event,
        "source": source,
        "schemaVersion": str(CONTRACT_VERSION),
    }
    optional = {
        "pageUrl": page_url,
        "selector": selector,
        "tagId": tag_id,
        "containerId": container_id,
    }
    record.update({key: value for key, value in optional.items() if value})
    return record


def validate_finding_record(record: Mapping[str, Any]) -> None:
    if not isinstance(record, Mapping):
        raise SquidContractError("record must be an object")
    required = (
        "name",
        "findingId",
        "ruleId",
        "rootCause",
        "severity",
        "confidence",
        "message",
        "recommendation",
        "source",
        "schemaVersion",
    )
    missing = [key for key in required if not _safe_text(record.get(key))]
    if missing:
        raise SquidContractError(f"record is missing required field(s): {', '.join(missing)}")
    if re.fullmatch(r"ptm_[a-f0-9]{24}", str(record["findingId"])) is None:
        raise SquidContractError("findingId must match ptm_<24 lowercase hex characters>")
    if record["severity"] not in SEVERITIES:
        raise SquidContractError(f"unsupported severity: {record['severity']!r}")
    if record["confidence"] not in CONFIDENCES:
        raise SquidContractError(f"unsupported confidence: {record['confidence']!r}")
    if "pageUrl" in record and record["pageUrl"] != _safe_url(record["pageUrl"]):
        raise SquidContractError("pageUrl must not contain a query string or fragment")


def build_finding_manifest() -> dict[str, Any]:
    object_metadata = {
        "nameSingular": OBJECT_NAME_SINGULAR,
        "namePlural": OBJECT_NAME_PLURAL,
        "labelSingular": LABEL_SINGULAR,
        "labelPlural": LABEL_PLURAL,
        "description": (
            "PyTagManager tracking findings. Created from versioned diagnostic evidence; "
            "not a consent or compliance verdict."
        ),
        "icon": OBJECT_ICON,
    }
    return {
        "schema_version": CONTRACT_VERSION,
        "contract": CONTRACT_ID,
        "status": "proposed",
        "owner": "PyTagManager",
        "object": object_metadata,
        "auto_fields": ["name"],
        "fields": [dict(field) for field in FIELD_DEFINITIONS],
        "metadata_operations": {
            "create_object": {"object": object_metadata},
            "create_fields": [
                {
                    "field": {
                        **{key: value for key, value in field.items() if key != "description"},
                        "objectMetadataId": "<created-object-id>",
                    }
                }
                for field in FIELD_DEFINITIONS
            ],
        },
        "record_schema": "schemas/squid/v1/tag-finding.schema.json",
        "upsert": {
            "method": "POST",
            "path": f"/rest/{OBJECT_NAME_PLURAL}/upsert",
            "body_shape": {"records": [{"findingId": "<ptm_...>", "...": "field values"}]},
            "match_field": "findingId",
            "lookup": {
                "method": "GET",
                "path": f"/rest/{OBJECT_NAME_PLURAL}",
                "query": "filter=findingId[eq]:<findingId>&limit=1",
                "selection": "exact findingId match only",
            },
            "idempotency": {
                "header": "Idempotency-Key",
                "scope": "Squid workspace",
                "value": "sha256 of the canonical batch body, prefixed pytagmanager-findings-v1:",
            },
        },
        "required_squid_acceptance": [
            "Create the tagManagerFinding object and all declared fields from metadata_operations.",
            "Enforce findingId uniqueness within a workspace.",
            "Confirm the REST lookup query and /upsert behavior against a live/test workspace.",
            "Grant the adapter an API key with Update capability; do not expose it to browsers.",
        ],
        "limitations": [
            "This is a proposed contract, not a live Squid integration.",
            "PyTagManager does not perform Squid writes or hold Squid credentials.",
            "Segments are owned by ClusterAudienceKit; this contract covers findings only.",
            "No generated GraphQL type is assumed; REST is the interim path.",
            "No consent decision or compliance verdict is encoded in a finding record.",
        ],
    }


def build_findings_plan(
    report: Mapping[str, Any],
    *,
    workspace_id: str | None = None,
) -> dict[str, Any]:
    if not isinstance(report, Mapping):
        raise SquidContractError("diagnose report must be an object")
    records: dict[str, dict[str, Any]] = {}
    diagnostics = report.get("diagnostics")
    if diagnostics is not None and not isinstance(diagnostics, list):
        raise SquidContractError("diagnose report diagnostics must be an array")
    for finding in diagnostics or []:
        if not isinstance(finding, Mapping):
            raise SquidContractError("each diagnostic must be an object")
        if finding.get("root_cause") in (None, "", "none"):
            continue
        if finding.get("severity") in (None, "", "healthy"):
            continue
        record = diagnosis_to_finding_record(finding)
        validate_finding_record(record)
        records[record["findingId"]] = record
    additional = report.get("additional_findings")
    if additional is not None and not isinstance(additional, list):
        raise SquidContractError("diagnose report additional_findings must be an array")
    for finding in additional or []:
        if not isinstance(finding, Mapping):
            raise SquidContractError("each additional finding must be an object")
        if finding.get("root_cause") in (None, "", "none"):
            continue
        record = diagnosis_to_finding_record(finding)
        validate_finding_record(record)
        records[record["findingId"]] = record

    ordered = [records[key] for key in sorted(records)]
    body = {"records": ordered}
    body_hash = hashlib.sha256(_canonical(body).encode("utf-8")).hexdigest()
    plan_id = f"ptm-{body_hash[:24]}"
    manifest = build_finding_manifest()
    request = None
    if ordered:
        request = {
            "method": "POST",
            "path": f"/rest/{OBJECT_NAME_PLURAL}/upsert",
            "headers": {
                "Content-Type": "application/json",
                "Idempotency-Key": f"pytagmanager-findings-v1:{body_hash}",
                "X-Correlation-Id": plan_id,
            },
            "body": body,
        }
    return {
        "schema_version": CONTRACT_VERSION,
        "contract": CONTRACT_ID,
        "status": "proposed",
        "workspace_id": workspace_id,
        "plan_id": plan_id,
        "manifest": manifest,
        "records": ordered,
        "request": request,
        "write_strategy": {
            "match_field": "findingId",
            "steps": [
                "Resolve each findingId with the documented REST lookup.",
                "Add the existing Squid record id to records that already exist.",
                "POST the batch to /rest/tagManagerFindings/upsert.",
                "Retry the identical request with the same Idempotency-Key on transient failure.",
            ],
            "requires": [
                "tagManagerFinding metadata created from the manifest",
                "unique findingId enforced per workspace",
                "Squid API key with Update capability",
            ],
        },
        "limitations": manifest["limitations"],
    }
