"""Real-browser end-to-end test for Phase 1.9 items 4+5:
`pytagmanager diagnose --test-candidates` generating an evidence-backed
Test Candidate with a paired draft Playwright script from a real
diagnostic finding.
"""

from __future__ import annotations

import json

from click.testing import CliRunner

from pytagmanager.cli import main


def test_test_candidates_generated_from_a_real_missing_event_finding(fixture_server, tmp_path):
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
    url = f"{fixture_server}/missing_datalayer.html"
    result = CliRunner().invoke(
        main, ["diagnose", url, "--scenario", str(scenario_path), "--test-candidates", "--format", "json"]
    )

    assert result.exit_code == 0, result.output
    json_start = result.output.index("{")
    report = json.loads(result.output[json_start:])

    candidates = report.get("test_candidates", [])
    assert len(candidates) == 1
    candidate = candidates[0]
    assert candidate["category"] == "event_existence"
    assert candidate["severity"] != "Confirmed defect"
    assert candidate["evidence_count"] == 1
    assert url in candidate["evidence_pages"][0]
    assert "raise NotImplementedError" in candidate["playwright_draft"]


def test_without_flag_no_test_candidates_reported(fixture_server, tmp_path):
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
    url = f"{fixture_server}/missing_datalayer.html"
    result = CliRunner().invoke(main, ["diagnose", url, "--scenario", str(scenario_path), "--format", "json"])

    assert result.exit_code == 0, result.output
    json_start = result.output.index("{")
    report = json.loads(result.output[json_start:])
    assert "test_candidates" not in report
