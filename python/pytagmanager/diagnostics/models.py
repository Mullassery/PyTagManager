"""Diagnosis output model for the rule-based diagnostic engine
(pytagmanager.diagnostics.rules). Kept dependency-free of
pytagmanager.correlation so pytagmanager.correlation.journey can embed a
Diagnosis on a TrackingJourney without a circular import.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict

# Ordered worst-to-best only in the sense that reporting sorts critical
# journeys first; "healthy" is not a failure severity at all.
SEVERITIES = frozenset({"critical", "warning", "healthy", "unknown"})

# How sure the rule engine is that the named root cause actually explains
# the symptom, as opposed to merely correlating with it (spec section 18:
# "do not claim causation when the evidence only establishes correlation").
# Severity says how bad it is; confidence says how sure we are why.
CONFIDENCE_LEVELS = frozenset({"Confirmed", "Highly likely", "Possible", "Needs investigation"})


@dataclass(frozen=True)
class Diagnosis:
    severity: str  # one of SEVERITIES
    root_cause: str  # short machine-readable slug, e.g. "gtm_trigger_mismatch"
    message: str  # one plain-language sentence explaining the failure
    rule_name: str
    details: Dict[str, Any] = field(default_factory=dict)
    confidence: str = "Needs investigation"  # one of CONFIDENCE_LEVELS

    @classmethod
    def healthy(cls) -> "Diagnosis":
        return cls(
            severity="healthy",
            root_cause="none",
            message="Tracking behaved as expected end to end.",
            rule_name="none",
            confidence="Confirmed",
        )
