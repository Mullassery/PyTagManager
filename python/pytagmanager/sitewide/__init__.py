from pytagmanager.sitewide.aggregation import (
    SiteHealthReport,
    TemplateConsistencyReport,
    TemplateEventStat,
    TemplateHealth,
    analyze_template_consistency,
    compute_site_health,
    compute_template_health,
)
from pytagmanager.sitewide.anomalies import Anomaly, detect_site_anomalies, detect_template_anomalies
from pytagmanager.sitewide.page_type import (
    PAGE_TYPES,
    HeuristicPageTypeClassifier,
    OllamaPageTypeClassifier,
    PageSummary,
    PageTypeResult,
    assign_semantic_labels,
    summarize_page,
)
from pytagmanager.sitewide.history import (
    HealthHistoryEntry,
    RegressionAlert,
    append_history_entry,
    detect_regression,
    load_history,
)
from pytagmanager.sitewide.notify import Notifier, WebhookNotifier
from pytagmanager.sitewide.report import build_site_health_json, render_site_health_report
from pytagmanager.sitewide.templates import PageTemplate, detect_templates, url_template

__all__ = [
    "PageTemplate",
    "detect_templates",
    "url_template",
    "TemplateEventStat",
    "TemplateConsistencyReport",
    "TemplateHealth",
    "SiteHealthReport",
    "analyze_template_consistency",
    "compute_template_health",
    "compute_site_health",
    "Anomaly",
    "detect_template_anomalies",
    "detect_site_anomalies",
    "render_site_health_report",
    "build_site_health_json",
    "PAGE_TYPES",
    "PageSummary",
    "PageTypeResult",
    "summarize_page",
    "HeuristicPageTypeClassifier",
    "OllamaPageTypeClassifier",
    "assign_semantic_labels",
    "HealthHistoryEntry",
    "RegressionAlert",
    "load_history",
    "append_history_entry",
    "detect_regression",
    "Notifier",
    "WebhookNotifier",
]
