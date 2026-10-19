"""Lighthouse adapter tests use a fake executable; no browser is launched."""

from __future__ import annotations

import json
import stat
from pathlib import Path

import pytest
from pytagmanager.audit.lighthouse import LighthouseRunner, LighthouseUnavailable


def _fake_lighthouse(tmp_path: Path) -> Path:
    payload = {
        "categories": {
            "performance": {"score": 0.82},
            "accessibility": {"score": 0.95},
        },
        "audits": {
            "largest-contentful-paint": {"numericValue": 2100.0, "score": 0.8},
            "total-blocking-time": {"numericValue": 320.0, "score": 0.6},
            "unused-javascript": {
                "title": "Reduce unused JavaScript",
                "score": 0.2,
                "displayValue": "Potential savings of 120 KB",
            },
        },
    }
    script = tmp_path / "lighthouse"
    script.write_text(
        "#!/usr/bin/env python3\n"
        "import sys\n"
        f"sys.stdout.write({json.dumps(payload)!r})\n"
    )
    script.chmod(script.stat().st_mode | stat.S_IEXEC)
    return script


def test_run_normalizes_scores_and_metrics(tmp_path):
    binary = _fake_lighthouse(tmp_path)
    report = LighthouseRunner(lighthouse_path=str(binary)).run("https://example.test")
    assert report.categories["performance"] == pytest.approx(0.82)
    assert report.metrics["lcp_ms"] == pytest.approx(2100.0)
    assert report.metrics["tbt_ms"] == pytest.approx(320.0)
    assert report.audits[0]["id"] == "unused-javascript"


def test_missing_binary_is_actionable(tmp_path):
    runner = LighthouseRunner(lighthouse_path=str(tmp_path / "missing"))
    with pytest.raises(LighthouseUnavailable, match="npm install -g lighthouse"):
        runner.run("https://example.test")
