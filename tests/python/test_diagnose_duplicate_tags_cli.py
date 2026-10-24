"""Real-browser end-to-end test for Phase 1.85 item 2:
`pytagmanager diagnose --detect-duplicate-tags` against a fixture page
with two real GTM containers and two duplicate GA4-style network requests
firing for the same interaction.
"""

from __future__ import annotations

import json

from click.testing import CliRunner
from pytagmanager.cli import main


def test_detect_duplicate_tags_flags_finding_on_real_duplicate_page(fixture_server, tmp_path):
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
    url = f"{fixture_server}/tagexec_duplicate.html"
    result = CliRunner().invoke(
        main,
        [
            "diagnose",
            url,
            "--scenario",
            str(scenario_path),
            "--detect-duplicate-tags",
            "--format",
            "json",
        ],
    )

    assert result.exit_code == 0, result.output
    json_start = result.output.index("{")
    report = json.loads(result.output[json_start:])

    findings = report.get("duplicate_tag_findings", [])
    assert findings, "expected at least one duplicate-tag finding"
    finding = findings[0]
    assert finding["kind"] == "multiple_gtm_containers"
    assert set(finding["involved"]) == {"GTM-FIRST111", "GTM-SECOND222"}
    assert finding["runtime_evidence"][0]["request_count"] == 2


def test_without_flag_no_duplicate_tag_findings_reported(fixture_server, tmp_path):
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
    url = f"{fixture_server}/tagexec_duplicate.html"
    result = CliRunner().invoke(
        main, ["diagnose", url, "--scenario", str(scenario_path), "--format", "json"]
    )

    assert result.exit_code == 0, result.output
    json_start = result.output.index("{")
    report = json.loads(result.output[json_start:])
    assert "duplicate_tag_findings" not in report
