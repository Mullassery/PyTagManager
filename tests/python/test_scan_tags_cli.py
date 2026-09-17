"""End-to-end test for `pytagmanager scan-tags` (Phase 1.85 item 1)."""

from __future__ import annotations

import json

from click.testing import CliRunner

from pytagmanager.cli import main


def test_scan_tags_json_reports_gtm_container_and_vendor(fixture_server):
    url = f"{fixture_server}/tagexec_static.html"
    result = CliRunner().invoke(main, ["scan-tags", url, "--wait", "0.1", "--format", "json"])

    assert result.exit_code == 0, result.output
    json_start = result.output.index("{")
    report = json.loads(result.output[json_start:])
    container_ids = {c["container_id"] for c in report["gtm_containers"]}
    assert "GTM-TEST1234" in container_ids
    vendors = {v["vendor"] for v in report["vendors"]}
    assert "Meta Pixel" in vendors


def test_scan_tags_text_format_writes_readable_report(fixture_server, tmp_path):
    url = f"{fixture_server}/tagexec_static.html"
    out_path = tmp_path / "scan.txt"
    result = CliRunner().invoke(main, ["scan-tags", url, "--wait", "0.1", "-o", str(out_path)])

    assert result.exit_code == 0, result.output
    assert f"Wrote static scan report to {out_path}" in result.output
    content = out_path.read_text()
    assert "GTM-TEST1234" in content
    assert "Meta Pixel" in content
