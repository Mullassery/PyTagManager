"""Real-browser end-to-end tests for Phase 1.95 item 10:
`pytagmanager perf`, reproducing the phase's exit criteria live: a fixture
page with one deliberately heavy script produces a report naming that
script and its measured TBT contribution from an isolation run.
"""

from __future__ import annotations

import json

from click.testing import CliRunner

from pytagmanager.cli import main

_PAGE = "perf_isolate.html"


def test_perf_baseline_only_reports_real_metrics(fixture_server, tmp_path):
    url = f"{fixture_server}/{_PAGE}"
    out_path = tmp_path / "report.json"
    result = CliRunner().invoke(main, ["perf", url, "--runs", "1", "-o", str(out_path), "--format", "json"])

    assert result.exit_code == 0, result.output
    report = json.loads(out_path.read_text())
    assert report["url"] == url
    assert report["run_count"] == 1
    assert report["median_lcp_ms"] is not None
    assert "isolation_experiments" not in report


def test_perf_isolate_reproduces_exit_criteria(fixture_server, tmp_path):
    # Phase 1.95 exit criteria: a fixture page with one deliberately heavy
    # third-party (here: first-party, per the item 4 fixture's own scope
    # note) script produces a report naming that script and its measured
    # TBT contribution from an isolation run.
    url = f"{fixture_server}/{_PAGE}"
    out_path = tmp_path / "report.json"
    result = CliRunner().invoke(
        main,
        [
            "perf",
            url,
            "--runs",
            "1",
            "--isolate",
            f"{fixture_server}/heavy_first_party.js",
            "-o",
            str(out_path),
            "--format",
            "json",
        ],
    )

    assert result.exit_code == 0, result.output
    report = json.loads(out_path.read_text())
    experiments = report.get("isolation_experiments", [])
    assert len(experiments) == 1
    experiment = experiments[0]
    assert f"{fixture_server}/heavy_first_party.js" in experiment["blocked_urls"]
    assert experiment["tbt_delta_ms"] is not None
    assert experiment["tbt_delta_ms"] > 0
    assert "observed" in experiment["message"].lower()


def test_perf_isolate_group_targets_only_classified_scripts(fixture_server, tmp_path):
    url = f"{fixture_server}/{_PAGE}"
    out_path = tmp_path / "report.json"
    result = CliRunner().invoke(
        main, ["perf", url, "--runs", "1", "--isolate-group", "ads", "-o", str(out_path), "--format", "json"]
    )

    assert result.exit_code == 0, result.output
    report = json.loads(out_path.read_text())
    experiment = report["isolation_experiments"][0]
    assert any("fbevents.js" in u for u in experiment["blocked_urls"])
    assert not any("heavy_first_party.js" in u for u in experiment["blocked_urls"])


def test_perf_mutually_exclusive_isolate_flags_rejected(fixture_server):
    url = f"{fixture_server}/{_PAGE}"
    result = CliRunner().invoke(main, ["perf", url, "--isolate", "https://x.example.com/x.js", "--all-off"])
    assert result.exit_code != 0
    assert "mutually exclusive" in result.output


def test_perf_history_and_test_candidates_flow(fixture_server, tmp_path):
    url = f"{fixture_server}/{_PAGE}"
    history_path = tmp_path / "perf_history.json"
    out_path = tmp_path / "report.json"

    # First run: establishes history, no prior entry to regress against.
    result = CliRunner().invoke(
        main,
        [
            "perf",
            url,
            "--runs",
            "1",
            "--isolate",
            f"{fixture_server}/heavy_first_party.js",
            "--history",
            str(history_path),
            "--test-candidates",
            "-o",
            str(out_path),
            "--format",
            "json",
        ],
    )

    assert result.exit_code == 0, result.output
    assert history_path.exists()
    report = json.loads(out_path.read_text())
    assert "regression_alerts" not in report  # no prior entry yet
    # --test-candidates must not error even when nothing crosses the
    # default budget threshold (the fixture's ~150ms busy-wait is below
    # the 200ms default) -- exact threshold behavior is covered by
    # test_perf_test_candidates.py's unit tests with controlled deltas.
    history_entries = json.loads(history_path.read_text())["entries"]
    assert len(history_entries) == 1
