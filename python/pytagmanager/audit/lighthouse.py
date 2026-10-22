"""Optional Lighthouse audit ingestion and repeated-run CI assessment.

Lighthouse (Apache-2.0) measures performance/accessibility/best-practices and
returns a JSON report. This adapter runs the installed CLI and normalizes the
scores and Core Web Vitals so they can be joined with tag diagnostics.

The single-run ``LighthouseRunner.run()`` path is deliberately unchanged. The
``run_repeated()`` path exists because one Lighthouse run is an anecdote, not a
performance assessment: it executes several fresh runs, reports the median and
observed range, and refuses to invent a verdict when there are not enough
completed samples or when explicit budgets were not supplied.

It does not vendor Chromium or Lighthouse. A missing binary raises
``LighthouseUnavailable`` instead of returning fabricated scores.
"""

from __future__ import annotations

import datetime
import json
import math
import shutil
import statistics
import subprocess
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

LIGHTHOUSE_CI_SCHEMA_VERSION = 1

# Bounds keep an accidental `--runs 10000` from turning a debugging command
# into an hours-long browser benchmark. Raise this deliberately if a genuinely
# larger CI sample is ever justified.
MAX_CI_RUNS = 20
DEFAULT_CI_RUNS = 3
DEFAULT_MIN_CI_RUNS = 2

# These keys are the normalized metric names emitted by _METRIC_AUDITS below.
# They are also accepted by `--budget`.
LIGHTHOUSE_METRIC_KEYS = (
    "lcp_ms",
    "tbt_ms",
    "cls",
    "inp_ms",
    "fcp_ms",
    "speed_index_ms",
)
LIGHTHOUSE_CATEGORY_KEYS = (
    "performance",
    "accessibility",
    "best-practices",
    "seo",
)
_BUDGET_DIRECTION = {
    **{key: "lower_is_better" for key in LIGHTHOUSE_METRIC_KEYS},
    **{key: "higher_is_better" for key in LIGHTHOUSE_CATEGORY_KEYS},
}

_METRIC_UNITS = {
    "lcp_ms": "ms",
    "tbt_ms": "ms",
    "inp_ms": "ms",
    "fcp_ms": "ms",
    "speed_index_ms": "ms",
    "cls": "",
}
_SCORE_KEYS = frozenset(LIGHTHOUSE_CATEGORY_KEYS)

_METRIC_AUDITS = {
    "largest-contentful-paint": "lcp_ms",
    "total-blocking-time": "tbt_ms",
    "cumulative-layout-shift": "cls",
    "interaction-to-next-paint": "inp_ms",
    "first-contentful-paint": "fcp_ms",
    "speed-index": "speed_index_ms",
}


class LighthouseUnavailable(RuntimeError):
    """Raised when the Lighthouse CLI is not installed."""


@dataclass
class LighthouseReport:
    url: str
    categories: dict[str, float] = field(default_factory=dict)
    metrics: dict[str, float] = field(default_factory=dict)
    audits: list[dict[str, Any]] = field(default_factory=list)
    raw: dict[str, Any] = field(default_factory=dict)
    lighthouse_version: str = ""
    fetch_time: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "url": self.url,
            "categories": self.categories,
            "metrics": self.metrics,
            "audits": self.audits,
            "lighthouse_version": self.lighthouse_version,
            "fetch_time": self.fetch_time,
        }


def _report_from_json(url: str, payload: dict[str, Any]) -> LighthouseReport:
    categories: dict[str, float] = {}
    for name, data in (payload.get("categories") or {}).items():
        if not isinstance(data, dict):
            continue
        score = data.get("score")
        # A missing score is unknown, not zero. Treating it as zero would
        # manufacture a failure that Lighthouse did not report.
        if score is not None:
            categories[str(name)] = float(score)

    metrics: dict[str, float] = {}
    audits: list[dict[str, Any]] = []
    for audit_id, audit in (payload.get("audits") or {}).items():
        if not isinstance(audit, dict):
            continue
        if audit_id in _METRIC_AUDITS and audit.get("numericValue") is not None:
            metrics[_METRIC_AUDITS[audit_id]] = float(audit["numericValue"])
        score = audit.get("score")
        if score is not None and float(score) < 1.0:
            audits.append(
                {
                    "id": audit_id,
                    "title": audit.get("title"),
                    "score": float(score),
                    "displayValue": audit.get("displayValue"),
                    "description": audit.get("description"),
                }
            )
    audits.sort(key=lambda item: item["score"])
    return LighthouseReport(
        url=url,
        categories=categories,
        metrics=metrics,
        audits=audits,
        raw=payload,
        lighthouse_version=str(payload.get("lighthouseVersion") or ""),
        fetch_time=str(payload.get("fetchTime") or ""),
    )


class LighthouseRunner:
    """Run Lighthouse and return normalized scores/metrics."""

    def __init__(
        self,
        lighthouse_path: str = "lighthouse",
        chrome_path: str | None = None,
        timeout: int = 120,
        extra_args: list[str] | None = None,
        max_output_bytes: int = 25_000_000,
    ):
        if max_output_bytes <= 0:
            raise ValueError("max_output_bytes must be positive")
        self.lighthouse_path = lighthouse_path
        self.chrome_path = chrome_path
        self.timeout = timeout
        self.extra_args = list(extra_args or [])
        self.max_output_bytes = max_output_bytes

    def is_available(self) -> bool:
        return shutil.which(self.lighthouse_path) is not None

    def _binary(self) -> str:
        resolved = shutil.which(self.lighthouse_path)
        if resolved is None:
            raise LighthouseUnavailable(
                "lighthouse was not found on PATH. Install the Apache-2.0 CLI "
                "with `npm install -g lighthouse` or pass lighthouse_path=..."
            )
        return resolved

    def run(
        self, url: str, *, only_categories: list[str] | None = None
    ) -> LighthouseReport:
        binary = self._binary()
        command = [
            binary,
            url,
            "--output",
            "json",
            "--output-path",
            "stdout",
            "--quiet",
            "--chrome-flags=--headless=new --no-sandbox",
        ]
        if only_categories:
            command.append("--only-categories=" + ",".join(only_categories))
        if self.chrome_path:
            command.append(f"--chrome-path={self.chrome_path}")
        command.extend(self.extra_args)

        try:
            completed = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=self.timeout,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError(f"lighthouse timed out after {self.timeout}s") from exc

        stdout = completed.stdout or ""
        if len(stdout.encode("utf-8", errors="ignore")) > self.max_output_bytes:
            raise RuntimeError(
                "lighthouse output exceeded the configured "
                f"{self.max_output_bytes}-byte limit; refusing to parse an "
                "unbounded report"
            )

        if completed.returncode != 0:
            detail = (completed.stderr or stdout or "").strip()
            raise RuntimeError(
                f"lighthouse failed ({completed.returncode}): {detail[:800]}"
            )
        try:
            payload = json.loads(stdout)
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"lighthouse emitted invalid JSON: {exc}") from exc
        if not isinstance(payload, dict):
            raise RuntimeError("lighthouse emitted a non-object JSON report")
        return _report_from_json(url, payload)

    def run_repeated(
        self,
        url: str,
        *,
        runs: int = DEFAULT_CI_RUNS,
        min_runs: int | None = None,
        budgets: Mapping[str, float] | None = None,
        only_categories: list[str] | None = None,
    ) -> "LighthouseCIReport":
        """Run Lighthouse several times and aggregate honestly.

        Each invocation is a separate Lighthouse process. Failed runs are
        retained as failures rather than silently dropped. The assessment is
        based only on completed runs and is explicitly insufficient when fewer
        than ``min_runs`` completed.
        """
        if runs < 1 or runs > MAX_CI_RUNS:
            raise ValueError(f"runs must be between 1 and {MAX_CI_RUNS}, got {runs}")
        if min_runs is None:
            min_runs = min(DEFAULT_MIN_CI_RUNS, runs)
        if min_runs < 1 or min_runs > runs:
            raise ValueError(f"min_runs must be between 1 and runs ({runs}), got {min_runs}")
        if budgets:
            _validate_budget_keys(budgets)

        # Fail fast on a missing binary instead of recording N identical
        # failures that obscure the actual setup error.
        self._binary()

        samples: List[LighthouseSample] = []
        for index in range(runs):
            started = datetime.datetime.now(datetime.timezone.utc)
            try:
                report = self.run(url, only_categories=only_categories)
                duration = (datetime.datetime.now(datetime.timezone.utc) - started).total_seconds()
                samples.append(LighthouseSample(index=index, report=report, duration_seconds=duration))
            except Exception as exc:  # noqa: BLE001 - retained as evidence, not swallowed
                duration = (datetime.datetime.now(datetime.timezone.utc) - started).total_seconds()
                samples.append(
                    LighthouseSample(
                        index=index,
                        error=f"{type(exc).__name__}: {exc}",
                        duration_seconds=duration,
                    )
                )

        return build_lighthouse_ci_report(
            url,
            samples=samples,
            requested_runs=runs,
            min_runs=min_runs,
            budgets=budgets,
        )


@dataclass(frozen=True)
class LighthouseSample:
    index: int
    report: Optional[LighthouseReport] = None
    error: str = ""
    duration_seconds: float = 0.0

    @property
    def ok(self) -> bool:
        return self.report is not None

    def to_dict(self) -> dict[str, Any]:
        if self.report is not None:
            return {
                "index": self.index,
                "status": "completed",
                "duration_seconds": round(self.duration_seconds, 3),
                "lighthouse_version": self.report.lighthouse_version,
                "categories": self.report.categories,
                "metrics": self.report.metrics,
            }
        return {
            "index": self.index,
            "status": "failed",
            "duration_seconds": round(self.duration_seconds, 3),
            "error": self.error,
        }


@dataclass(frozen=True)
class LighthouseDistribution:
    key: str
    values: Tuple[float, ...]
    median: float
    minimum: float
    maximum: float
    mean: float
    stdev: float
    spread_ratio: float
    unit: str = ""

    @classmethod
    def from_values(cls, key: str, values: Sequence[float]) -> "LighthouseDistribution":
        if not values:
            raise ValueError("a distribution requires at least one value")
        ordered = tuple(float(value) for value in values)
        median = statistics.median(ordered)
        spread_ratio = (max(ordered) - min(ordered)) / abs(median) if median else 0.0
        return cls(
            key=key,
            values=ordered,
            median=median,
            minimum=min(ordered),
            maximum=max(ordered),
            mean=statistics.fmean(ordered),
            stdev=statistics.pstdev(ordered) if len(ordered) > 1 else 0.0,
            spread_ratio=spread_ratio,
            unit=_METRIC_UNITS.get(key, ""),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "sample_count": len(self.values),
            "median": self.median,
            "minimum": self.minimum,
            "maximum": self.maximum,
            "mean": self.mean,
            "stdev": self.stdev,
            "spread_ratio": round(self.spread_ratio, 4),
            "unit": self.unit,
        }


@dataclass(frozen=True)
class LighthouseBudgetResult:
    key: str
    limit: float
    observed: Optional[float]
    direction: str
    passed: bool
    reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "limit": self.limit,
            "observed_median": self.observed,
            "direction": self.direction,
            "passed": self.passed,
            "reason": self.reason,
        }


@dataclass(frozen=True)
class LighthouseCIReport:
    url: str
    requested_runs: int
    min_runs: int
    completed_runs: int
    failed_runs: int
    samples: Tuple[LighthouseSample, ...]
    metrics: Mapping[str, LighthouseDistribution]
    categories: Mapping[str, LighthouseDistribution]
    budget_results: Tuple[LighthouseBudgetResult, ...]
    status: str
    confidence: str
    assessment: str
    limitations: Tuple[str, ...]
    generated_at: str
    schema_version: int = LIGHTHOUSE_CI_SCHEMA_VERSION

    @property
    def budget_failed(self) -> bool:
        return any(not result.passed for result in self.budget_results)

    @property
    def insufficient_data(self) -> bool:
        return self.status == "insufficient_data"

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "generated_at": self.generated_at,
            "url": self.url,
            "requested_runs": self.requested_runs,
            "min_runs": self.min_runs,
            "completed_runs": self.completed_runs,
            "failed_runs": self.failed_runs,
            "status": self.status,
            "confidence": self.confidence,
            "assessment": self.assessment,
            "limitations": list(self.limitations),
            "samples": [sample.to_dict() for sample in self.samples],
            "metrics": {key: value.to_dict() for key, value in self.metrics.items()},
            "categories": {key: value.to_dict() for key, value in self.categories.items()},
            "budget_results": [result.to_dict() for result in self.budget_results],
        }


def _validate_budget_keys(budgets: Mapping[str, float]) -> None:
    unknown = sorted(set(budgets) - set(_BUDGET_DIRECTION))
    if unknown:
        allowed = ", ".join(sorted(_BUDGET_DIRECTION))
        raise ValueError(f"unknown budget key(s): {', '.join(unknown)}; allowed: {allowed}")
    for key, value in budgets.items():
        if not math.isfinite(value) or value < 0:
            raise ValueError(f"budget {key!r} must be a finite non-negative number, got {value!r}")


def parse_budgets(specs: Iterable[str]) -> Dict[str, float]:
    """Parse repeatable ``key=value`` budget CLI options."""
    budgets: Dict[str, float] = {}
    for spec in specs:
        key, separator, raw_value = spec.partition("=")
        key = key.strip()
        if not separator or not key:
            raise ValueError(f"budget must be METRIC=VALUE, got {spec!r}")
        try:
            value = float(raw_value.strip())
        except ValueError as exc:
            raise ValueError(f"budget value for {key!r} is not a number: {raw_value!r}") from exc
        if key in budgets:
            raise ValueError(f"budget {key!r} was supplied more than once")
        budgets[key] = value
    _validate_budget_keys(budgets)
    return budgets


def _collect_distributions(
    reports: Sequence[LighthouseReport],
    attribute: str,
    keys: Sequence[str],
) -> Dict[str, LighthouseDistribution]:
    distributions: Dict[str, LighthouseDistribution] = {}
    for key in keys:
        values = []
        for report in reports:
            source = getattr(report, attribute)
            if key in source and source[key] is not None:
                values.append(float(source[key]))
        if values:
            distributions[key] = LighthouseDistribution.from_values(key, values)
    return distributions


def _budget_results(
    budgets: Mapping[str, float],
    metrics: Mapping[str, LighthouseDistribution],
    categories: Mapping[str, LighthouseDistribution],
) -> Tuple[LighthouseBudgetResult, ...]:
    results: List[LighthouseBudgetResult] = []
    for key, limit in budgets.items():
        direction = _BUDGET_DIRECTION[key]
        distribution = metrics.get(key) or categories.get(key)
        if distribution is None:
            results.append(
                LighthouseBudgetResult(
                    key=key,
                    limit=limit,
                    observed=None,
                    direction=direction,
                    passed=False,
                    reason="metric was not present in any completed run; this is not a pass",
                )
            )
            continue
        observed = distribution.median
        passed = observed <= limit if direction == "lower_is_better" else observed >= limit
        results.append(
            LighthouseBudgetResult(
                key=key,
                limit=limit,
                observed=observed,
                direction=direction,
                passed=passed,
                reason="",
            )
        )
    return tuple(results)


def _confidence(
    completed_runs: int,
    min_runs: int,
    metrics: Mapping[str, LighthouseDistribution],
) -> str:
    if completed_runs < min_runs or completed_runs < 2:
        return "insufficient"
    spreads = [
        distribution.spread_ratio
        for key, distribution in metrics.items()
        if key in {"lcp_ms", "tbt_ms", "inp_ms", "cls"} and distribution.median > 0
    ]
    worst_spread = max(spreads, default=0.0)
    if completed_runs >= 5 and worst_spread <= 0.10:
        return "high"
    if completed_runs >= 3 and worst_spread <= 0.25:
        return "medium"
    return "low"


def _format_value(key: str, value: float) -> str:
    if key in _SCORE_KEYS:
        return f"{value:.3f}"
    if key == "cls":
        return f"{value:.3f}"
    return f"{value:,.1f} ms"


def _assessment_text(
    completed_runs: int,
    min_runs: int,
    metrics: Mapping[str, LighthouseDistribution],
    categories: Mapping[str, LighthouseDistribution],
    failed_runs: int,
    budget_results: Sequence[LighthouseBudgetResult],
    confidence: str,
) -> str:
    if completed_runs < min_runs:
        return (
            f"Only {completed_runs} of {min_runs} required Lighthouse run(s) completed; "
            "no performance assessment is made. This is an execution failure, not a clean result."
        )

    parts: List[str] = []
    if "lcp_ms" in metrics:
        lcp = metrics["lcp_ms"]
        parts.append(
            f"median LCP {_format_value('lcp_ms', lcp.median)} "
            f"(observed range {lcp.minimum:,.1f}-{lcp.maximum:,.1f} ms)"
        )
    if "tbt_ms" in metrics:
        tbt = metrics["tbt_ms"]
        parts.append(
            f"median TBT {_format_value('tbt_ms', tbt.median)} "
            f"(range {tbt.minimum:,.1f}-{tbt.maximum:,.1f} ms)"
        )
    if "cls" in metrics:
        cls = metrics["cls"]
        parts.append(f"median CLS {cls.median:.3f} (range {cls.minimum:.3f}-{cls.maximum:.3f})")
    if "performance" in categories:
        score = categories["performance"]
        parts.append(
            f"median performance score {score.median:.3f} "
            f"(range {score.minimum:.3f}-{score.maximum:.3f})"
        )

    summary = ", ".join(parts) if parts else "Lighthouse returned no comparable metrics"
    text = (
        f"Observed {summary} across {completed_runs} successful Lighthouse run(s). "
        "This is a repeated lab measurement, not field data (CrUX/RUM) and not a guarantee."
    )
    if failed_runs:
        text += f" {failed_runs} run(s) failed; the assessment excludes them and may be biased."
    if budget_results:
        text += " Budgets are evaluated against the median, not the best run."
    if confidence == "low":
        text += " Run-to-run spread is high or the sample is small; treat these medians as provisional."
    return text


def _limitations(
    completed_runs: int,
    failed_runs: int,
    confidence: str,
    has_budgets: bool,
) -> Tuple[str, ...]:
    limitations = [
        "Lighthouse is a lab measurement; it does not prove field (CrUX/RUM) speed or business impact.",
        "Medians from a small number of runs are a technical heuristic, not a statistical guarantee.",
        "Results are comparable only when Lighthouse version, device emulation, network conditions and URL are aligned.",
        "Missing metrics are omitted, not treated as zero or as a passing result.",
        "This report does not prove downstream tag delivery, attribution, or legal compliance.",
    ]
    if completed_runs < DEFAULT_MIN_CI_RUNS:
        limitations.append(
            "Fewer than two successful runs were completed; no central tendency can be established."
        )
    if failed_runs:
        limitations.append(
            "Failed runs are retained as failures and excluded from the median; a clean pass cannot be claimed."
        )
    if confidence == "low":
        limitations.append(
            "Observed run-to-run variability is material; increase --runs and stabilize the test environment before acting."
        )
    if not has_budgets:
        limitations.append(
            "No budgets were supplied, so this report makes no pass/fail performance verdict."
        )
    return tuple(limitations)


def build_lighthouse_ci_report(
    url: str,
    *,
    samples: Sequence[LighthouseSample],
    requested_runs: int,
    min_runs: int,
    budgets: Mapping[str, float] | None = None,
) -> LighthouseCIReport:
    """Aggregate completed/failed samples into a deterministic CI report."""
    if requested_runs < 1:
        raise ValueError("requested_runs must be positive")
    if min_runs < 1 or min_runs > requested_runs:
        raise ValueError("min_runs must be between 1 and requested_runs")
    if len(samples) > requested_runs:
        raise ValueError("samples cannot exceed requested_runs")
    budgets = dict(budgets or {})
    _validate_budget_keys(budgets)

    reports = [sample.report for sample in samples if sample.report is not None]
    completed_runs = len(reports)
    failed_runs = len(samples) - completed_runs

    metrics = _collect_distributions(reports, "metrics", LIGHTHOUSE_METRIC_KEYS)
    categories = _collect_distributions(reports, "categories", LIGHTHOUSE_CATEGORY_KEYS)
    budget_results = _budget_results(budgets, metrics, categories)
    confidence = _confidence(completed_runs, min_runs, metrics)

    if completed_runs < min_runs:
        status = "insufficient_data"
    elif any(not result.passed for result in budget_results):
        status = "budget_failed"
    elif failed_runs:
        status = "partial"
    elif budget_results:
        status = "budget_passed"
    else:
        status = "observed"

    assessment = _assessment_text(
        completed_runs,
        min_runs,
        metrics,
        categories,
        failed_runs,
        budget_results,
        confidence,
    )
    limitations = _limitations(completed_runs, failed_runs, confidence, bool(budget_results))

    return LighthouseCIReport(
        url=url,
        requested_runs=requested_runs,
        min_runs=min_runs,
        completed_runs=completed_runs,
        failed_runs=failed_runs,
        samples=tuple(samples),
        metrics=metrics,
        categories=categories,
        budget_results=budget_results,
        status=status,
        confidence=confidence,
        assessment=assessment,
        limitations=limitations,
        generated_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
    )


def render_lighthouse_ci_report(report: LighthouseCIReport) -> str:
    lines = [f"Lighthouse CI: {report.url}", "=" * (15 + len(report.url)), ""]
    lines.append(
        f"Runs: {report.requested_runs} requested, {report.completed_runs} completed, "
        f"{report.failed_runs} failed (minimum required: {report.min_runs})"
    )
    versions = sorted({sample.report.lighthouse_version for sample in report.samples if sample.report and sample.report.lighthouse_version})
    if versions:
        lines.append(f"Lighthouse version(s): {', '.join(versions)}")
    lines.append(f"Status: {report.status.upper().replace('_', ' ')}")
    lines.append(f"Confidence: {report.confidence.upper()}")
    lines.append("")

    if report.metrics or report.categories:
        lines.append("Observed distributions (median, range):")
        for key, distribution in report.metrics.items():
            lines.append(
                f"  {key}: {_format_value(key, distribution.median)} "
                f"(range {distribution.minimum:,.1f}-{distribution.maximum:,.1f}, n={len(distribution.values)})"
            )
        for key, distribution in report.categories.items():
            lines.append(
                f"  {key}: {distribution.median:.3f} "
                f"(range {distribution.minimum:.3f}-{distribution.maximum:.3f}, n={len(distribution.values)})"
            )
        lines.append("")

    if report.budget_results:
        lines.append("Budgets (evaluated against the median):")
        for result in report.budget_results:
            comparator = "<=" if result.direction == "lower_is_better" else ">="
            if result.observed is None:
                state = "UNAVAILABLE"
                detail = result.reason
            else:
                state = "PASS" if result.passed else "FAIL"
                detail = f"median {_format_value(result.key, result.observed)}"
            lines.append(f"  {state} {result.key} {comparator} {result.limit:g} ({detail})")
        lines.append("")

    lines.append("Assessment:")
    lines.append(f"  {report.assessment}")
    lines.append("")
    lines.append("Limitations:")
    for limitation in report.limitations:
        lines.append(f"  - {limitation}")
    return "\n".join(lines)


def run_lighthouse(url: str, **kwargs: Any) -> LighthouseReport:
    return LighthouseRunner(**kwargs).run(url)


def run_lighthouse_ci(
    url: str,
    *,
    runs: int = DEFAULT_CI_RUNS,
    min_runs: int | None = None,
    budgets: Mapping[str, float] | None = None,
    **runner_kwargs: Any,
) -> LighthouseCIReport:
    return LighthouseRunner(**runner_kwargs).run_repeated(
        url, runs=runs, min_runs=min_runs, budgets=budgets
    )


__all__ = [
    "DEFAULT_CI_RUNS",
    "DEFAULT_MIN_CI_RUNS",
    "LIGHTHOUSE_CATEGORY_KEYS",
    "LIGHTHOUSE_CI_SCHEMA_VERSION",
    "LIGHTHOUSE_METRIC_KEYS",
    "LighthouseBudgetResult",
    "LighthouseCIReport",
    "LighthouseDistribution",
    "LighthouseReport",
    "LighthouseRunner",
    "LighthouseSample",
    "LighthouseUnavailable",
    "MAX_CI_RUNS",
    "build_lighthouse_ci_report",
    "parse_budgets",
    "render_lighthouse_ci_report",
    "run_lighthouse",
    "run_lighthouse_ci",
]
