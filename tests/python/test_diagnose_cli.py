"""Smoke test for the `pytagmanager diagnose` command end to end: real
browser, real fixture server, --scenario overriding auto-discovery for a
single URL, both text and json --format outputs.
"""

import json

from click.testing import CliRunner
from pytagmanager.cli import main


def test_diagnose_text_format(fixture_server, tmp_path):
    scenario_path = tmp_path / "add_to_cart.yml"
    scenario_path.write_text(
        """
journey:
  name: Add To Cart
  steps:
    - action: click
      selector: "[data-testid='add-to-cart']"
    - expect:
        datalayer_event: "add_to_cart"
"""
    )
    url = f"{fixture_server}/healthy_tracking.html"
    result = CliRunner().invoke(
        main, ["diagnose", url, "--scenario", str(scenario_path), "--format", "text"]
    )

    assert result.exit_code == 0, result.output
    assert "PyTagManager Tracking Health" in result.output
    assert "Healthy" in result.output


def test_diagnose_json_format(fixture_server, tmp_path):
    scenario_path = tmp_path / "broken.yml"
    scenario_path.write_text(
        """
journey:
  name: Add To Cart
  steps:
    - action: click
      selector: "[data-testid='add-to-cart']"
    - expect:
        datalayer_event: "add_to_cart"
"""
    )
    url = f"{fixture_server}/missing_datalayer.html"
    result = CliRunner().invoke(
        main, ["diagnose", url, "--scenario", str(scenario_path), "--format", "json"]
    )

    assert result.exit_code == 0, result.output
    report = json.loads(result.output)
    assert report["schema_version"] == 1
    assert report["summary"]["failed"] == 1
    assert report["diagnostics"][0]["root_cause"] == "missing_datalayer_event"


def test_diagnose_trace_flag_includes_interaction_trace_json(fixture_server, tmp_path):
    scenario_path = tmp_path / "add_to_cart.yml"
    scenario_path.write_text(
        """
journey:
  name: Add To Cart
  steps:
    - action: click
      selector: "[data-testid='add-to-cart']"
    - expect:
        datalayer_event: "add_to_cart"
"""
    )
    url = f"{fixture_server}/healthy_tracking.html"
    result = CliRunner().invoke(
        main,
        [
            "diagnose",
            url,
            "--scenario",
            str(scenario_path),
            "--format",
            "json",
            "--trace",
        ],
    )

    assert result.exit_code == 0, result.output
    report = json.loads(result.output)
    assert "interaction_traces" in report
    assert len(report["interaction_traces"]) >= 1
    trace = report["interaction_traces"][0]
    assert trace["business_event"] == "add_to_cart"
    assert any(step["stage"] == "interaction" for step in trace["steps"])


def test_diagnose_without_trace_flag_omits_interaction_traces(fixture_server, tmp_path):
    scenario_path = tmp_path / "add_to_cart.yml"
    scenario_path.write_text(
        """
journey:
  name: Add To Cart
  steps:
    - action: click
      selector: "[data-testid='add-to-cart']"
    - expect:
        datalayer_event: "add_to_cart"
"""
    )
    url = f"{fixture_server}/healthy_tracking.html"
    result = CliRunner().invoke(
        main, ["diagnose", url, "--scenario", str(scenario_path), "--format", "json"]
    )

    assert result.exit_code == 0, result.output
    report = json.loads(result.output)
    assert "interaction_traces" not in report


def test_diagnose_track_scroll_depth_flag_is_accepted_and_does_not_break_the_run(
    fixture_server, tmp_path
):
    # ObservationSession-level tests (test_observability_extended_observers.py)
    # already cover the scroll-depth mechanism itself against a real tall
    # page; this is a CLI-plumbing smoke test -- the flag reaches
    # ObservationSession and the run still completes normally on a short
    # fixture page where no milestone besides an initial no-op fires.
    scenario_path = tmp_path / "add_to_cart.yml"
    scenario_path.write_text(
        """
journey:
  name: Add To Cart
  steps:
    - action: click
      selector: "[data-testid='add-to-cart']"
    - expect:
        datalayer_event: "add_to_cart"
"""
    )
    url = f"{fixture_server}/healthy_tracking.html"
    result = CliRunner().invoke(
        main,
        [
            "diagnose",
            url,
            "--scenario",
            str(scenario_path),
            "--track-scroll-depth",
            "--format",
            "json",
        ],
    )

    assert result.exit_code == 0, result.output
    report = json.loads(result.output)
    assert report["summary"]["journeys_total"] >= 1
