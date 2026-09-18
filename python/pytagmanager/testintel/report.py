"""Human-readable and JSON rendering for `TestCandidate`s, mirroring
`tagexec/report.py`'s / `dictionary/report.py`'s terminal/JSON split.
"""

from __future__ import annotations

from typing import List, Sequence

from pytagmanager.testintel.candidates import TestCandidate
from pytagmanager.testintel.playwright_export import export_playwright_script

JSON_SCHEMA_VERSION = 1


def render_test_candidates(candidates: Sequence[TestCandidate]) -> List[str]:
    """Rendered as a list of lines (not a full report string), matching
    `tagexec.report`'s convention -- callers splice this into their own
    larger report alongside diagnostics/traces/tag-execution sections."""
    if not candidates:
        return []
    lines = ["TEST CANDIDATES (discovery, not verified -- review before formalizing)", "-" * 71]
    for candidate in candidates:
        lines.append(f"  [{candidate.category}/{candidate.severity}] {candidate.name}")
        lines.append(f"    Observed: {candidate.observed}")
        lines.append(f"    Problem:  {candidate.observed_problem}")
        lines.append(f"    Evidence: {candidate.evidence_count} page(s)")
        for step in candidate.suggested_verification:
            lines.append(f"      - {step}")
        lines.append("")
    return lines


def build_test_candidates_json(candidates: Sequence[TestCandidate], include_playwright_draft: bool = True) -> List[dict]:
    result = []
    for candidate in candidates:
        entry = {
            "name": candidate.name,
            "category": candidate.category,
            "severity": candidate.severity,
            "observed": candidate.observed,
            "observed_problem": candidate.observed_problem,
            "evidence_pages": list(candidate.evidence_pages),
            "evidence_count": candidate.evidence_count,
            "suggested_verification": list(candidate.suggested_verification),
            "source_root_causes": list(candidate.source_root_causes),
        }
        if include_playwright_draft:
            entry["playwright_draft"] = export_playwright_script(candidate)
        result.append(entry)
    return result
