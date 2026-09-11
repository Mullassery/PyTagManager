"""Human-readable site-wide report (spec sections 17/19): site health
summary, per-template health, cross-page consistency findings, and a
tracking matrix. Columns are limited to what's actually measurable from
observed journeys -- no invented metrics.
"""

from __future__ import annotations

from typing import List, Optional

from pytagmanager.sitewide.aggregation import SiteHealthReport, TemplateConsistencyReport, TemplateHealth
from pytagmanager.sitewide.anomalies import Anomaly
from pytagmanager.sitewide.interaction_consistency import BusinessActionConsistencyReport


def _pct(value: Optional[float]) -> str:
    return f"{value:.1%}" if value is not None else "N/A"


def _status_icon(value: Optional[float], warn_below: float = 1.0, fail_below: float = 0.5) -> str:
    if value is None:
        return "—"  # em dash: no data
    if value >= warn_below:
        return "✅"  # check
    if value >= fail_below:
        return "⚠️"  # warning
    return "❌"  # cross


def render_site_health_report(
    site_health: SiteHealthReport,
    consistency_reports: List[TemplateConsistencyReport],
    anomalies: Optional[List[Anomaly]] = None,
    business_action_reports: Optional[List[BusinessActionConsistencyReport]] = None,
) -> str:
    anomalies = anomalies or []
    business_action_reports = business_action_reports or []
    lines = ["PyTagManager Site Health", "=" * 25, ""]
    lines.append(f"{site_health.pages_scanned} pages scanned")
    lines.append(f"Overall tracking health score: {site_health.overall_score}/100")
    lines.append("")
    lines.append(f"GTM coverage        {_pct(site_health.gtm_coverage)}")
    lines.append(f"GA4 coverage        {_pct(site_health.ga4_coverage)}")
    lines.append(f"DataLayer coverage  {_pct(site_health.datalayer_coverage)}")
    lines.append(f"Event coverage      {_pct(site_health.event_coverage)}")
    lines.append(f"Consent             {_pct(site_health.consent_ok_rate)}")
    lines.append("")
    lines.append(f"Potential duplicate events: {_pct(site_health.duplicate_rate)}")
    lines.append(f"Pages with JS tracking errors: {site_health.pages_with_js_errors}")
    lines.append("")

    lines.append("Template Health")
    lines.append("-" * 16)
    for template_health in sorted(site_health.template_healths, key=lambda t: t.score):
        lines.append(
            f"{template_health.template.label} Template: {template_health.score}/100 "
            f"({template_health.journeys_total} journeys tested)"
        )
    lines.append("")

    regressions = [finding for report in consistency_reports for finding in report.regressions]
    if regressions:
        lines.append("Cross-Page Consistency Findings")
        lines.append("-" * 32)
        for finding in regressions:
            lines.append(f"  - {finding}")
        lines.append("")

    if anomalies:
        lines.append("Anomalies")
        lines.append("-" * 9)
        for anomaly in anomalies:
            lines.append(f"  - {anomaly.message}")
        lines.append("")

    inconsistent = [r for r in business_action_reports if not r.is_consistent]
    if inconsistent:
        lines.append("Cross-Implementation Consistency (same business action, different pages)")
        lines.append("-" * 72)
        for report in inconsistent:
            names = ", ".join(report.distinct_event_names)
            lines.append(
                f"  - {report.business_objective}: {report.fired_count} implementation(s) fired, "
                f"{len(report.distinct_event_names)} different event name(s) observed ({names})"
            )
            for impl in report.implementations:
                status = impl.observed_event_name if impl.fired else "(no event fired)"
                lines.append(f"      {impl.page_url} [{impl.selector}] -> {status}")
        lines.append("")

    lines.append("Site-Wide Tracking Matrix")
    lines.append("-" * 25)
    lines.append(f"{'Template':<22}{'GTM':>8}{'GA4':>8}{'DataLayer':>12}{'Errors':>8}")
    for template_health in site_health.template_healths:
        lines.append(_matrix_row(template_health))

    return "\n".join(lines)


def _matrix_row(template_health: TemplateHealth) -> str:
    gtm = _status_icon(template_health.gtm_coverage)
    ga4 = _status_icon(template_health.ga4_coverage)
    datalayer = _status_icon(template_health.datalayer_coverage)
    errors = str(template_health.js_error_count) if template_health.js_error_count else "0"
    return f"{template_health.template.label:<22}{gtm:>8}{ga4:>8}{datalayer:>12}{errors:>8}"


def build_site_health_json(
    site_health: SiteHealthReport,
    consistency_reports: List[TemplateConsistencyReport],
    anomalies: Optional[List[Anomaly]] = None,
    business_action_reports: Optional[List[BusinessActionConsistencyReport]] = None,
) -> dict:
    anomalies = anomalies or []
    business_action_reports = business_action_reports or []
    return {
        "schema_version": 1,
        "pages_scanned": site_health.pages_scanned,
        "overall_score": site_health.overall_score,
        "coverage": {
            "gtm": site_health.gtm_coverage,
            "ga4": site_health.ga4_coverage,
            "datalayer": site_health.datalayer_coverage,
            "event": site_health.event_coverage,
            "consent": site_health.consent_ok_rate,
        },
        "duplicate_rate": site_health.duplicate_rate,
        "pages_with_js_errors": site_health.pages_with_js_errors,
        "templates": [
            {
                "label": th.template.label,
                "template_id": th.template.template_id,
                "score": th.score,
                "healthy": th.healthy,
                "warnings": th.warnings,
                "critical": th.critical,
                "journeys_total": th.journeys_total,
                "gtm_coverage": th.gtm_coverage,
                "ga4_coverage": th.ga4_coverage,
                "datalayer_coverage": th.datalayer_coverage,
                "js_error_count": th.js_error_count,
                "page_count": len(th.template.page_urls),
            }
            for th in site_health.template_healths
        ],
        "cross_page_consistency": [
            {
                "template": report.template.label,
                "event_stats": [
                    {
                        "event_name": stat.event_name,
                        "pass_count": stat.pass_count,
                        "fail_count": stat.fail_count,
                        "total": stat.total,
                        "pass_rate": round(stat.pass_rate, 4),
                    }
                    for stat in report.event_stats
                ],
                "regressions": report.regressions,
            }
            for report in consistency_reports
        ],
        "anomalies": [
            {
                "kind": anomaly.kind,
                "page_url": anomaly.page_url,
                "message": anomaly.message,
                "details": anomaly.details,
            }
            for anomaly in anomalies
        ],
        "business_action_consistency": [
            {
                "business_objective": report.business_objective,
                "is_consistent": report.is_consistent,
                "distinct_event_names": report.distinct_event_names,
                "fired_count": report.fired_count,
                "untested_or_silent_count": report.untested_or_silent_count,
                "implementations": [
                    {
                        "page_url": impl.page_url,
                        "selector": impl.selector,
                        "observed_event_name": impl.observed_event_name,
                        "fired": impl.fired,
                    }
                    for impl in report.implementations
                ],
            }
            for report in business_action_reports
        ],
    }
