from pytagmanager.sitewide.aggregation import (
    SiteHealthReport,
    TemplateConsistencyReport,
    TemplateEventStat,
    TemplateHealth,
    analyze_template_consistency,
    compute_site_health,
    compute_template_health,
)
from pytagmanager.sitewide.anomalies import (
    Anomaly,
    detect_site_anomalies,
    detect_template_anomalies,
)
from pytagmanager.sitewide.history import (
    HealthHistoryEntry,
    RegressionAlert,
    append_history_entry,
    detect_regression,
    load_history,
)
from pytagmanager.sitewide.notify import Notifier, WebhookNotifier
from pytagmanager.sitewide.page_type import (
    PAGE_TYPES,
    HeuristicPageTypeClassifier,
    OllamaPageTypeClassifier,
    PageSummary,
    PageTypeResult,
    assign_semantic_labels,
    summarize_page,
)
from pytagmanager.sitewide.report import (
    build_site_health_json,
    render_site_health_report,
)
from pytagmanager.sitewide.templates import PageTemplate, detect_templates, url_template

__all__ = [
    "PAGE_TYPES",
    "Anomaly",
    "HealthHistoryEntry",
    "HeuristicPageTypeClassifier",
    "Notifier",
    "OllamaPageTypeClassifier",
    "PageSummary",
    "PageTemplate",
    "PageTypeResult",
    "RegressionAlert",
    "SiteHealthReport",
    "TemplateConsistencyReport",
    "TemplateEventStat",
    "TemplateHealth",
    "WebhookNotifier",
    "analyze_template_consistency",
    "append_history_entry",
    "assign_semantic_labels",
    "build_site_health_json",
    "compute_site_health",
    "compute_template_health",
    "detect_regression",
    "detect_site_anomalies",
    "detect_template_anomalies",
    "detect_templates",
    "load_history",
    "render_site_health_report",
    "summarize_page",
    "url_template",
]
