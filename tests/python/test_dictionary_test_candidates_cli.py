"""Real-browser end-to-end test for Phase 1.9 item 5's regression-category
wiring: `pytagmanager dictionary --compare-to --test-candidates` against
two real crawls where a dataLayer field was removed.
"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from click.testing import CliRunner
from pytagmanager import _core, cli

_FIXTURES_DIR = Path(__file__).parent / "fixtures" / "observability"


def _fake_page(fixture_server: str, filename: str):
    url = f"{fixture_server}/{filename}"
    html = (_FIXTURES_DIR / filename).read_text()
    graph = _core.parse_html(html, url)
    return SimpleNamespace(url=url, status=200, graph=graph)


def test_regression_test_candidate_generated_for_removed_price_field(
    fixture_server, monkeypatch, tmp_path
):
    runner = CliRunner()
    baseline_path = tmp_path / "baseline.json"

    monkeypatch.setattr(
        "pytagmanager.cli.crawl_site",
        lambda *a, **k: [_fake_page(fixture_server, "runtime_state.html")],
    )
    baseline_url = f"{fixture_server}/runtime_state.html"
    result = runner.invoke(
        cli.main,
        ["dictionary", baseline_url, "--format", "json", "-o", str(baseline_path)],
    )
    assert result.exit_code == 0, result.output

    monkeypatch.setattr(
        "pytagmanager.cli.crawl_site",
        lambda *a, **k: [_fake_page(fixture_server, "runtime_state_regression.html")],
    )
    new_url = f"{fixture_server}/runtime_state_regression.html"
    result = runner.invoke(
        cli.main,
        [
            "dictionary",
            new_url,
            "--compare-to",
            str(baseline_path),
            "--test-candidates",
            "--format",
            "json",
        ],
    )

    assert result.exit_code == 0, result.output
    json_start = result.output.index("{")
    report = json.loads(result.output[json_start:])

    candidates = report.get("test_candidates", [])
    assert len(candidates) == 1
    candidate = candidates[0]
    assert candidate["category"] == "regression"
    assert "price" in candidate["name"]
    assert "add_to_cart" in candidate["name"]
    assert candidate["severity"] != "Confirmed defect"
    assert "raise NotImplementedError" in candidate["playwright_draft"]


def test_without_test_candidates_flag_compare_to_omits_the_key(
    fixture_server, monkeypatch, tmp_path
):
    runner = CliRunner()
    baseline_path = tmp_path / "baseline.json"

    monkeypatch.setattr(
        "pytagmanager.cli.crawl_site",
        lambda *a, **k: [_fake_page(fixture_server, "runtime_state.html")],
    )
    baseline_url = f"{fixture_server}/runtime_state.html"
    runner.invoke(
        cli.main,
        ["dictionary", baseline_url, "--format", "json", "-o", str(baseline_path)],
    )

    monkeypatch.setattr(
        "pytagmanager.cli.crawl_site",
        lambda *a, **k: [_fake_page(fixture_server, "runtime_state_regression.html")],
    )
    new_url = f"{fixture_server}/runtime_state_regression.html"
    result = runner.invoke(
        cli.main,
        ["dictionary", new_url, "--compare-to", str(baseline_path), "--format", "json"],
    )

    assert result.exit_code == 0, result.output
    json_start = result.output.index("{")
    report = json.loads(result.output[json_start:])
    assert "test_candidates" not in report
