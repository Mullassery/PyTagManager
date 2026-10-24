"""Performance Test Candidate integration (docs/VISION.md §16, Phase 1.95
item 9): reuses Phase 1.9's `TestCandidate` model rather than a parallel
one, for two of the performance-specific candidate shapes VISION.md §16
names by example -- "verify performance stays within threshold" and a
newly-introduced script correlated with a regression.

**Scope, disclosed honestly**: VISION's other named example, "verify
script does not load before consent," needs consent-state-aware
script-load-timing correlation this pass doesn't build -- no existing
`perf/` module cross-references consent events with script timing, so
nothing is fabricated for that case here.
"""

from __future__ import annotations

from collections.abc import Sequence

from pytagmanager.perf.experiments import IsolationExperimentResult
from pytagmanager.perf.history import PerformanceRegressionAlert
from pytagmanager.testintel.candidates import (
    CATEGORY_REGRESSION,
    CATEGORY_TIMING,
    SEVERITY_POTENTIAL_ISSUE,
    SEVERITY_REQUIRES_VERIFICATION,
    TestCandidate,
)

DEFAULT_TBT_BUDGET_MS = 200.0


def generate_performance_budget_candidates(
    results: Sequence[IsolationExperimentResult],
    tbt_budget_ms: float = DEFAULT_TBT_BUDGET_MS,
) -> list[TestCandidate]:
    """One candidate per isolation result whose measured TBT contribution
    meets or exceeds `tbt_budget_ms` -- "Potential issue", not stronger:
    a single controlled run exceeding a budget is worth a human look, not
    a confirmed regression on its own."""
    candidates = []
    for result in results:
        if (
            result.tbt_delta_ms is None
            or result.tbt_delta_ms < tbt_budget_ms
            or result.baseline is None
        ):
            continue
        candidates.append(
            TestCandidate(
                name=f"Verify {result.target_description} stays within a {tbt_budget_ms:.0f}ms TBT budget",
                category=CATEGORY_TIMING,
                severity=SEVERITY_POTENTIAL_ISSUE,
                observed=f"Blocking {result.target_description} improved TBT by {result.tbt_delta_ms:.1f}ms in a controlled run.",
                observed_problem=(
                    f"{result.target_description} costs at least {result.tbt_delta_ms:.1f}ms of main-thread "
                    f"blocking time, exceeding the {tbt_budget_ms:.0f}ms budget."
                ),
                evidence_pages=(result.baseline.url,),
                suggested_verification=(
                    "Load the page under the same controlled conditions (viewport, CPU throttling) as this run",
                    f"Measure TBT with {result.target_description} present",
                    f"Assert TBT contribution stays below {tbt_budget_ms:.0f}ms",
                ),
                source_root_causes=("performance_budget_exceeded",),
            )
        )
    return candidates


def generate_performance_regression_candidates(
    alerts: Sequence[PerformanceRegressionAlert],
) -> list[TestCandidate]:
    candidates = []
    for alert in alerts:
        candidates.append(
            TestCandidate(
                name=f"'{alert.metric}' should not regress between crawls",
                category=CATEGORY_REGRESSION,
                severity=SEVERITY_REQUIRES_VERIFICATION,
                observed=f"{alert.metric} was {alert.previous_value:.1f} in the previous recorded run.",
                observed_problem=alert.message,
                evidence_pages=(),
                suggested_verification=(
                    "Re-run the performance measurement under the same controlled conditions",
                    f"Compare {alert.metric} against the previous recorded baseline",
                    "If newly-introduced scripts are listed, isolate each one to confirm which (if any) is responsible",
                ),
                source_root_causes=("performance_regression",),
            )
        )
    return candidates
