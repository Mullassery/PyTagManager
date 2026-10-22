"""Consent-management-platform auditing: detection, consent evidence, and
deterministic findings. This module never asserts legal compliance.
"""

from pytagmanager.cmp.adapters import ADAPTERS, detect_adapters, extract_signals
from pytagmanager.cmp.collector import (
    CmpAuditAuthorizationError,
    CmpAuditOptions,
    CmpAuditRunner,
)
from pytagmanager.cmp.models import (
    CATEGORIES,
    CmpAuditReport,
    CmpDetection,
    CmpEvidence,
    CmpFinding,
    ConsentState,
    CookieMetadata,
    RequestObservation,
)
from pytagmanager.cmp.report import render_cmp_audit_report
from pytagmanager.cmp.rules import analyze_cmp

__all__ = [
    "ADAPTERS",
    "CATEGORIES",
    "CmpAuditAuthorizationError",
    "CmpAuditOptions",
    "CmpAuditReport",
    "CmpAuditRunner",
    "CmpDetection",
    "CmpEvidence",
    "CmpFinding",
    "ConsentState",
    "CookieMetadata",
    "RequestObservation",
    "analyze_cmp",
    "detect_adapters",
    "extract_signals",
    "render_cmp_audit_report",
]
