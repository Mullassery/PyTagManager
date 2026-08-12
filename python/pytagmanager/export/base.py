from __future__ import annotations

from typing import Callable, Dict, List, NamedTuple, Protocol

from pytagmanager.export.adobe_tags import build_adobe_launch_rules
from pytagmanager.export.ga4 import build_ga4_config
from pytagmanager.export.gtm import build_gtm_container
from pytagmanager.export.rudderstack import build_rudderstack_tracking_plan
from pytagmanager.export.segment import build_segment_tracking_plan
from pytagmanager.export.snowplow import build_snowplow_schemas
from pytagmanager.export.tealium import build_tealium_profile
from pytagmanager.recommend.models import TrackingRecommendation


class Exporter(Protocol):
    """Interface every tracking-config exporter implements. Every builder
    function in this package (`build_gtm_container`, `build_ga4_config`,
    `build_segment_tracking_plan`, `build_snowplow_schemas`,
    `build_tealium_profile`, `build_rudderstack_tracking_plan`,
    `build_adobe_launch_rules`) satisfies this same
    `List[TrackingRecommendation] -> dict` shape, and is registered in
    `EXPORTERS` below so the CLI (and any other caller) can dispatch on a
    format name without importing every module directly.
    """

    def export(self, recommendations: List[TrackingRecommendation]) -> dict: ...


class ExporterSpec(NamedTuple):
    build: Callable[[List[TrackingRecommendation]], dict]
    label: str


# CLI `--export <name>` -> (builder function, human-readable label used in
# CLI output). Adding a new exporter means adding one module + one entry
# here; the CLI's Click `Choice` and dispatch logic read this dict, not a
# hardcoded list.
EXPORTERS: Dict[str, ExporterSpec] = {
    "gtm": ExporterSpec(build_gtm_container, "GTM container"),
    "ga4": ExporterSpec(build_ga4_config, "GA4 event config"),
    "segment": ExporterSpec(build_segment_tracking_plan, "Segment tracking plan"),
    "snowplow": ExporterSpec(build_snowplow_schemas, "Snowplow schemas"),
    "tealium": ExporterSpec(build_tealium_profile, "Tealium iQ profile"),
    "rudderstack": ExporterSpec(build_rudderstack_tracking_plan, "RudderStack tracking plan"),
    "adobe_tags": ExporterSpec(build_adobe_launch_rules, "Adobe Tags (Launch) rules"),
}
