"""Deterministic tests for repeated-run Lighthouse CI assessment.

No browser or real Lighthouse binary is launched: a fake executable emits
controlled JSON on each invocation, which is exactly what these tests need to
verify aggregation, failed-run retention and budget semantics.
"""

from __future__ import annotations

import json
import stat
from pathlib import Path
from typing import Iterable

import pytest
from click.testing import CliRunner

from pytagmanager.audit.lighthouse import (
    LighthouseRunner,
    LighthouseUnavailable,
    _report_from_json,
    parse_budgets,
    render_lighthouse_ci_report,
)
from pytagmanager.cli import main


def _payload(
    *,
    lcp: float = 1000.0,
    tbt: float = 100.0,
    cls: float = 0.05,
    performance: float | None = 0.82,
) -> dict:
    categories = {}
    if performance is not None:
        categories["performance"] = {"score": performance}
    return {
        "lighthouseVersion": "12.0.0",
        "fetchTime": "2026-10-22T00:00:00.000Z",
        "categories": categories,
        "audits": {
            "largest-contentful-paint": {"numericValue": lcp, "score": 0.8},
            "total-blocking-time": {"numericValue": tbt, "score": 0.6},
            "cumulative-layout-shift": {"numericValue": cls, "score": 1.0},
            "unused-javascript": {
                "title": "Reduce unused JavaScript",
                "score": 0.2,
                "displayValue": "Potential savings of 120 KB",
            },
        },
    }


def _fake_lighthouse(
    tmp_path: Path,
    payloads: Iterable[dict],
    *,
    failing_indices: Iterable[int] = (),
) -> Path:
    counter = tmp_path / "counter"
    script = tmp_path / "lighthouse"
    script.write_text(
        "#!/usr/bin/env python3\n"
        "import json, pathlib, sys\n"
        f"counter = pathlib.Path({str(counter)!r})\n"
        "index = int(counter.read_text()) if counter.exists() else 0\n"
        "counter.write_text(str(index + 1))\n"
        f"payloads = {list(payloads)!r}\n"
        f"failing = set({tuple(failing_indices)!r})\n"
        "if index in failing:\n"
        "    sys.stderr.write('fake lighthouse failure\\n')\n"
        "    sys.exit(1)\n"
        "sys.stdout.write(json.dumps(payloads[index % len(payloads)]))\n"
    )
    script.chmod(script.stat().st_mode | stat.S_IEXEC)
    return script


def test_run_repeated_reports_medians_ranges_and_confidence(tmp_path):
    binary = _fake_lighthouse(
        tmp_path,
        [
            _payload(lcp=1000.0, tbt=50.0, performance=0.80),
            _payload(lcp=1200.0, tbt=100.0, performance=0.82),
            _payload(lcp=1100.0, tbt=75.0, performance=0.84),
        ],
    )

    report = LighthouseRunner(lighthouse_path=str(binary)).run_repeated(
        "https://example.test", runs=3, min_runs=2
    )

    assert report.status == "observed"
    assert report.confidence in {"medium", "low"}
    assert report.completed_runs == 3
    assert report.failed_runs == 0
    assert report.metrics["lcp_ms"].median == 1100.0
    assert report.metrics["lcp_ms"].minimum == 1000.0
    assert report.metrics["lcp_ms"].maximum == 1200.0
    assert report.categories["performance"].median == 0.82
    assert "lab measurement" in report.assessment
    assert "median LCP" in report.assessment
    assert report.samples[0].report is not None


def test_budget_failure_is_visible_and_not_hidden_by_a_good_run(tmp_path):
    binary = _fake_lighthouse(
        tmp_path,
        [
            _payload(lcp=1000.0, performance=0.80),
            _payload(lcp=1200.0, performance=0.82),
            _payload(lcp=1100.0, performance=0.84),
        ],
    )

    report = LighthouseRunner(lighthouse_path=str(binary)).run_repeated(
        "https://example.test",
        runs=3,
        min_runs=2,
        budgets={"lcp_ms": 1150.0, "performance": 0.90},
    )

    assert report.status == "budget_failed"
    assert report.budget_failed is True
    by_key = {result.key: result for result in report.budget_results}
    assert by_key["lcp_ms"].passed is True
    assert by_key["performance"].passed is False
    assert by_key["performance"].observed == 0.82
    rendered = render_lighthouse_ci_report(report)
    assert "FAIL performance >= 0.9" in rendered


def test_missing_metric_is_unavailable_not_a_silent_pass(tmp_path):
    binary = _fake_lighthouse(tmp_path, [_payload(performance=None), _payload(performance=None)])

    report = LighthouseRunner(lighthouse_path=str(binary)).run_repeated(
        "https://example.test", runs=2, min_runs=1, budgets={"performance": 0.9}
    )

    result = report.budget_results[0]
    assert result.passed is False
    assert result.observed is None
    assert "not a pass" in result.reason
    assert report.status == "budget_failed"


def test_failed_runs_are_retained_and_insufficient_data_is_not_clean(tmp_path):
    binary = _fake_lighthouse(
        tmp_path,
        [_payload(lcp=1000.0)],
        failing_indices={1, 2},
    )

    report = LighthouseRunner(lighthouse_path=str(binary)).run_repeated(
        "https://example.test", runs=3, min_runs=2
    )

    assert report.completed_runs == 1
    assert report.failed_runs == 2
    assert report.status == "insufficient_data"
    assert report.confidence == "insufficient"
    assert "no performance assessment is made" in report.assessment
    assert all(sample.error for sample in report.samples[1:])
    assert "FAILED" not in render_lighthouse_ci_report(report)  # report has no fictional pass


def test_partial_runs_are_reported_as_partial_when_minimum_is_met(tmp_path):
    binary = _fake_lighthouse(
        tmp_path,
        [_payload(lcp=1000.0), _payload(lcp=1100.0), _payload(lcp=1200.0)],
        failing_indices={1},
    )

    report = LighthouseRunner(lighthouse_path=str(binary)).run_repeated(
        "https://example.test", runs=3, min_runs=2
    )

    assert report.completed_runs == 2
    assert report.failed_runs == 1
    assert report.status == "partial"
    assert "1 run(s) failed" in report.assessment


def test_parse_budgets_rejects_unknown_duplicate_and_non_numeric_values():
    with pytest.raises(ValueError, match="unknown budget"):
        parse_budgets(["not_a_metric=1"])
    with pytest.raises(ValueError, match="more than once"):
        parse_budgets(["lcp_ms=1", "lcp_ms=2"])
    with pytest.raises(ValueError, match="not a number"):
        parse_budgets(["lcp_ms=fast"])
    with pytest.raises(ValueError, match="non-negative"):
        parse_budgets(["lcp_ms=-1"])


def test_missing_binary_fails_before_fabricating_three_failures(tmp_path):
    runner = LighthouseRunner(lighthouse_path=str(tmp_path / "missing"))
    with pytest.raises(LighthouseUnavailable, match="npm install -g lighthouse"):
        runner.run_repeated("https://example.test", runs=3)


def test_missing_category_score_is_unknown_not_zero():
    report = _report_from_json(
        "https://example.test",
        {"categories": {"performance": {"score": None}, "seo": {"score": 0.9}}},
    )
    assert "performance" not in report.categories
    assert report.categories["seo"] == pytest.approx(0.9)


def test_oversized_output_is_rejected(tmp_path):
    binary = _fake_lighthouse(tmp_path, [_payload()])
    runner = LighthouseRunner(lighthouse_path=str(binary), max_output_bytes=20)
    with pytest.raises(RuntimeError, match="exceeded"):
        runner.run("https://example.test")


def test_build_report_is_deterministic_and_json_serializable(tmp_path):
    binary = _fake_lighthouse(tmp_path, [_payload(), _payload(lcp=1100.0)])
    report = LighthouseRunner(lighthouse_path=str(binary)).run_repeated(
        "https://example.test", runs=2, min_runs=1
    )
    first = report.to_dict()
    second = report.to_dict()
    assert first["schema_version"] == 1
    assert first["url"] == second["url"]
    assert first["metrics"]["lcp_ms"]["median"] == 1050.0
    json.dumps(first)


def test_cli_json_contract_with_budgets_and_exit_code(tmp_path):
    binary = _fake_lighthouse(tmp_path, [_payload(lcp=1000.0), _payload(lcp=1100.0)])
    result = CliRunner().invoke(
        main,
        [
            "lighthouse-ci",
            "https://example.test",
            "--lighthouse-path",
            str(binary),
            "--runs",
            "2",
            "--min-runs",
            "1",
            "--budget",
            "lcp_ms=5000",
            "--fail-on-budget",
            "--format",
            "json",
        ],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["status"] == "budget_passed"
    assert payload["metrics"]["lcp_ms"]["median"] == 1050.0
    assert payload["budget_results"][0]["passed"] is True


def test_cli_fails_budget_with_exit_code_one(tmp_path):
    binary = _fake_lighthouse(tmp_path, [_payload(lcp=3000.0), _payload(lcp=3100.0)])
    result = CliRunner().invoke(
        main,
        [
            "lighthouse-ci",
            "https://example.test",
            "--lighthouse-path",
            str(binary),
            "--runs",
            "2",
            "--min-runs",
            "1",
            "--budget",
            "lcp_ms=2000",
            "--fail-on-budget",
        ],
    )

    assert result.exit_code == 1
    assert "FAIL lcp_ms <= 2000" in result.output


def test_cli_insufficient_data_exits_two(tmp_path):
    binary = _fake_lighthouse(tmp_path, [_payload()], failing_indices={0, 1})
    result = CliRunner().invoke(
        main,
        [
            "lighthouse-ci",
            "https://example.test",
            "--lighthouse-path",
            str(binary),
            "--runs",
            "2",
            "--min-runs",
            "1",
        ],
    )

    assert result.exit_code == 2
    assert "INSUFFICIENT DATA" in result.output


def test_cli_rejects_unknown_budget_key(tmp_path):
    result = CliRunner().invoke(
        main,
        ["lighthouse-ci", "https://example.test", "--budget", "nope=1"],
    )
    assert result.exit_code == 2
    assert "unknown budget" in result.output
