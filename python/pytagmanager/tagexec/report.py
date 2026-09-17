"""Human-readable and JSON rendering for a `StaticScanResult`, mirroring
`dictionary/report.py`'s terminal/JSON split.
"""

from __future__ import annotations

from typing import Optional, Tuple

from pytagmanager.tagexec.static_scan import StaticScanResult

JSON_SCHEMA_VERSION = 1


def render_static_scan_report(
    result: StaticScanResult, delayed_container_ids: Tuple[str, ...] = ()
) -> str:
    lines = [f"PyTagManager Tag Execution Static Scan: {result.page_url}", "=" * 40, ""]

    if result.gtm_containers:
        lines.append(f"GTM containers ({len(result.gtm_containers)}):")
        for container in result.gtm_containers:
            delayed_marker = " [delayed-load]" if container.container_id in delayed_container_ids else ""
            lines.append(f"  - {container.container_id} via {container.load_mechanism}{delayed_marker}")
        if result.has_multiple_gtm_containers:
            lines.append("  WARNING: multiple distinct GTM containers detected on this page.")
        lines.append("")
    else:
        lines.append("No GTM containers detected.")
        lines.append("")

    if result.vendors:
        lines.append(f"Vendor implementations ({len(result.vendors)}):")
        by_category: dict = {}
        for vendor in result.vendors:
            by_category.setdefault(vendor.category, []).append(vendor)
        for category in sorted(by_category):
            lines.append(f"  {category}:")
            for vendor in by_category[category]:
                lines.append(f"    - {vendor.vendor} ({vendor.evidence})")
        lines.append("")
    else:
        lines.append("No known vendor implementations detected.")
        lines.append("")

    return "\n".join(lines)


def build_static_scan_json(result: StaticScanResult, delayed_container_ids: Tuple[str, ...] = ()) -> dict:
    return {
        "schema_version": JSON_SCHEMA_VERSION,
        "page_url": result.page_url,
        "gtm_containers": [
            {
                "container_id": c.container_id,
                "load_mechanism": c.load_mechanism,
                "delayed_load": c.container_id in delayed_container_ids,
            }
            for c in result.gtm_containers
        ],
        "multiple_gtm_containers": result.has_multiple_gtm_containers,
        "vendors": [
            {"vendor": v.vendor, "category": v.category, "evidence": v.evidence} for v in result.vendors
        ],
    }
