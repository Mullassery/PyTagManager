"""Real-browser end-to-end test for Phase 1.85 item 3:
`pytagmanager diagnose --detect-server-side-tagging` against a fixture
page with a first-party GA4-Measurement-Protocol-shaped request and a
fan-out to two distinct external hosts for the same interaction.
"""

from __future__ import annotations

import json

from click.testing import CliRunner

from pytagmanager.cli import main


def test_detect_server_side_tagging_flags_indicators_on_real_page(fixture_server, tmp_path):
    scenario_path = tmp_path / "add_to_cart.yml"
    scenario_path.write_text(
        """
journey:
  name: Add To Cart
  steps:
    - action: click
      selector: "[data-testid='add-to-cart']"
"""
    )
    url = f"{fixture_server}/tagexec_server_side.html"
    result = CliRunner().invoke(
        main,
        ["diagnose", url, "--scenario", str(scenario_path), "--detect-server-side-tagging", "--format", "json"],
    )

    assert result.exit_code == 0, result.output
    json_start = result.output.index("{")
    report = json.loads(result.output[json_start:])

    indicators = report.get("server_side_tagging_indicators", [])
    assert indicators, "expected at least one server-side tagging indicator"
    kinds = {i["kind"] for i in indicators}
    assert "first_party_collection_endpoint" in kinds
    assert "fanout_to_multiple_destinations" in kinds
    for indicator in indicators:
        assert indicator["confidence"] != "Confirmed"
        assert indicator["confidence"] in ("Likely", "Possible")


def test_without_flag_no_server_side_indicators_reported(fixture_server, tmp_path):
    scenario_path = tmp_path / "add_to_cart.yml"
    scenario_path.write_text(
        """
journey:
  name: Add To Cart
  steps:
    - action: click
      selector: "[data-testid='add-to-cart']"
"""
    )
    url = f"{fixture_server}/tagexec_server_side.html"
    result = CliRunner().invoke(
        main, ["diagnose", url, "--scenario", str(scenario_path), "--format", "json"]
    )

    assert result.exit_code == 0, result.output
    json_start = result.output.index("{")
    report = json.loads(result.output[json_start:])
    assert "server_side_tagging_indicators" not in report
