"""Real-browser end-to-end test for Phase 1.85 items 5+6:
`pytagmanager diagnose --tag-graph` assembling the Tag Execution Graph
from a real page's static scan + Interaction Traces + duplicate findings.
"""

from __future__ import annotations

import json

from click.testing import CliRunner

from pytagmanager.cli import main


def test_tag_graph_assembles_nodes_and_edges_from_a_real_page(fixture_server, tmp_path):
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
            "--tag-graph",
            "--detect-duplicate-tags",
            "--format",
            "json",
        ],
    )

    assert result.exit_code == 0, result.output
    json_start = result.output.index("{")
    report = json.loads(result.output[json_start:])

    graph = report.get("tag_execution_graph")
    assert graph is not None
    node_ids = {n["id"] for n in graph["nodes"]}
    assert "gtm:GTM-FIRST111" in node_ids
    assert "gtm:GTM-SECOND222" in node_ids

    duplicate_edge = next(
        (
            e
            for e in graph["edges"]
            if {e["source"], e["target"]} == {"gtm:GTM-FIRST111", "gtm:GTM-SECOND222"}
        ),
        None,
    )
    assert duplicate_edge is not None
    assert duplicate_edge["evidence"] == "Observed"

    valid_evidence = {"Observed", "Inferred", "Suspected", "Unknown", "Not observed"}
    for edge in graph["edges"]:
        assert edge["evidence"] in valid_evidence


def test_without_tag_graph_flag_no_graph_reported(fixture_server, tmp_path):
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
    assert "tag_execution_graph" not in report
