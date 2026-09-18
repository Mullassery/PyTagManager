from pytagmanager.perf.measure import (
    PerformanceBaseline,
    PerformanceSnapshot,
    TestEnvironmentConfig,
    capture_performance_snapshot,
    measure_page_performance,
)
from pytagmanager.perf.dependency_graph import DependencyEdge, ScriptDependencyGraph, build_dependency_graph
from pytagmanager.perf.experiments import (
    GROUP_TAG_MANAGEMENT,
    IsolationExperimentResult,
    available_groups,
    isolate_all_non_essential,
    isolate_group,
    isolate_script,
)
from pytagmanager.perf.history import (
    PerformanceHistoryEntry,
    PerformanceRegressionAlert,
    append_performance_history_entry,
    detect_performance_regression,
    load_performance_history,
)
from pytagmanager.perf.report import (
    TemplatePerformanceSummary,
    build_performance_report_json,
    rank_scripts_by_cost,
    render_performance_report,
    summarize_template_performance,
)
from pytagmanager.perf.scripts import ScriptEntry, ScriptInventory, build_script_inventory
from pytagmanager.perf.tagging_join import TaggingPerformanceTradeoff, build_tagging_performance_tradeoffs
from pytagmanager.perf.test_candidates import (
    generate_performance_budget_candidates,
    generate_performance_regression_candidates,
)

__all__ = [
    "PerformanceSnapshot",
    "PerformanceBaseline",
    "TestEnvironmentConfig",
    "capture_performance_snapshot",
    "measure_page_performance",
    "ScriptEntry",
    "ScriptInventory",
    "build_script_inventory",
    "DependencyEdge",
    "ScriptDependencyGraph",
    "build_dependency_graph",
    "IsolationExperimentResult",
    "GROUP_TAG_MANAGEMENT",
    "available_groups",
    "isolate_script",
    "isolate_group",
    "isolate_all_non_essential",
    "TaggingPerformanceTradeoff",
    "build_tagging_performance_tradeoffs",
    "TemplatePerformanceSummary",
    "rank_scripts_by_cost",
    "summarize_template_performance",
    "render_performance_report",
    "build_performance_report_json",
    "PerformanceHistoryEntry",
    "PerformanceRegressionAlert",
    "load_performance_history",
    "append_performance_history_entry",
    "detect_performance_regression",
    "generate_performance_budget_candidates",
    "generate_performance_regression_candidates",
]
