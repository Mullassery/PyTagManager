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
    result = CliRunner().invoke(main, ["diagnose", url, "--scenario", str(scenario_path), "--format", "text"])

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
    result = CliRunner().invoke(main, ["diagnose", url, "--scenario", str(scenario_path), "--format", "json"])

    assert result.exit_code == 0, result.output
    report = json.loads(result.output)
    assert report["schema_version"] == 1
    assert report["summary"]["failed"] == 1
    assert report["diagnostics"][0]["root_cause"] == "missing_datalayer_event"
