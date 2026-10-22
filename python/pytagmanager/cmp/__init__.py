"""Consent-management-platform auditing: detection, consent evidence, and
deterministic findings. This module never asserts legal compliance.
"""

from pytagmanager.cmp.adapters import (
    ADAPTERS,
    detect_adapters,
    extract_signals,
    read_gpp_consent,
    read_tcf_consent,
    tcf_categories_from_purposes,
)
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
from pytagmanager.cmp.plugins import (
    AdapterFileError,
    load_adapter_file,
    load_adapter_files,
)
from pytagmanager.cmp.report import render_cmp_audit_report
from pytagmanager.cmp.rules import analyze_cmp

__all__ = [
    "ADAPTERS",
    "AdapterFileError",
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
    "load_adapter_file",
    "load_adapter_files",
    "read_gpp_consent",
    "read_tcf_consent",
    "render_cmp_audit_report",
    "tcf_categories_from_purposes",
]
