"""Text rendering for SDR alignment reports."""

from __future__ import annotations

from .validate import SdrValidation


def render_sdr_report(validation: SdrValidation) -> str:
    lines = [
        "SDR Alignment",
        "=" * 13,
        "",
        f"SDR: {validation.schema_name}",
        f"Alignment score: {validation.alignment_score:.1%} "
        f"({validation.checks_passed}/{validation.checks_total} checks passed)",
        "",
    ]
    for event in validation.events:
        label = event.status.upper()
        lines.append(f"{event.event_name} [{label}]")
        lines.append(
            f"  occurrences: {event.occurrences}  pages: {', '.join(event.pages) or 'none observed'}"
        )
        for check in event.checks:
            marker = "PASS" if check.status == "passed" else "FAIL"
            lines.append(f"  {marker} {check.message}")
        if event.issues:
            lines.append("  Recommendations:")
            for issue in event.issues:
                lines.append(f"    - {issue.recommendation}")
        lines.append("")
    if validation.recommendations:
        lines.append("Prioritized recommendations")
        lines.append("-" * 27)
        for recommendation in validation.recommendations:
            lines.append(f"  - {recommendation}")
        lines.append("")
    if validation.limitations:
        lines.append("Limitations")
        lines.append("-" * 11)
        for limitation in validation.limitations:
            lines.append(f"  - {limitation}")
    return "\n".join(lines).rstrip()
