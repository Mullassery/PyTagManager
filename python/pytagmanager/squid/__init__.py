"""Squid-CRM custom-object contracts owned by PyTagManager."""

from .findings import (
    CONTRACT_ID,
    CONTRACT_VERSION,
    OBJECT_NAME_PLURAL,
    OBJECT_NAME_SINGULAR,
    SquidContractError,
    build_finding_manifest,
    build_findings_plan,
    diagnosis_to_finding_record,
    recommendation_for_root_cause,
    validate_finding_record,
)

__all__ = [
    "CONTRACT_ID",
    "CONTRACT_VERSION",
    "OBJECT_NAME_PLURAL",
    "OBJECT_NAME_SINGULAR",
    "SquidContractError",
    "build_finding_manifest",
    "build_findings_plan",
    "diagnosis_to_finding_record",
    "recommendation_for_root_cause",
    "validate_finding_record",
]
