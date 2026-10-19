"""Optional Lighthouse audit ingestion.

Lighthouse (Apache-2.0) measures performance/accessibility/best-practices and
returns a JSON report. This adapter runs the installed CLI and normalizes the
scores and Core Web Vitals so they can be joined with tag diagnostics.

It does not vendor Chromium or Lighthouse. A missing binary raises
``LighthouseUnavailable`` instead of returning fabricated scores.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from dataclasses import dataclass, field
from typing import Any


class LighthouseUnavailable(RuntimeError):
    """Raised when the Lighthouse CLI is not installed."""


@dataclass
class LighthouseReport:
    url: str
    categories: dict[str, float] = field(default_factory=dict)
    metrics: dict[str, float] = field(default_factory=dict)
    audits: list[dict[str, Any]] = field(default_factory=list)
    raw: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "url": self.url,
            "categories": self.categories,
            "metrics": self.metrics,
            "audits": self.audits,
        }


_METRIC_AUDITS = {
    "largest-contentful-paint": "lcp_ms",
    "total-blocking-time": "tbt_ms",
    "cumulative-layout-shift": "cls",
    "interaction-to-next-paint": "inp_ms",
    "first-contentful-paint": "fcp_ms",
    "speed-index": "speed_index_ms",
}


def _report_from_json(url: str, payload: dict[str, Any]) -> LighthouseReport:
    categories = {
        str(name): float(data.get("score") or 0.0)
        for name, data in (payload.get("categories") or {}).items()
        if isinstance(data, dict)
    }
    metrics: dict[str, float] = {}
    audits: list[dict[str, Any]] = []
    for audit_id, audit in (payload.get("audits") or {}).items():
        if not isinstance(audit, dict):
            continue
        if audit_id in _METRIC_AUDITS and audit.get("numericValue") is not None:
            metrics[_METRIC_AUDITS[audit_id]] = float(audit["numericValue"])
        score = audit.get("score")
        if score is not None and float(score) < 1.0:
            audits.append(
                {
                    "id": audit_id,
                    "title": audit.get("title"),
                    "score": float(score),
                    "displayValue": audit.get("displayValue"),
                    "description": audit.get("description"),
                }
            )
    audits.sort(key=lambda item: item["score"])
    return LighthouseReport(
        url=url, categories=categories, metrics=metrics, audits=audits, raw=payload
    )


class LighthouseRunner:
    """Run Lighthouse and return normalized scores/metrics."""

    def __init__(
        self,
        lighthouse_path: str = "lighthouse",
        chrome_path: str | None = None,
        timeout: int = 120,
        extra_args: list[str] | None = None,
    ):
        self.lighthouse_path = lighthouse_path
        self.chrome_path = chrome_path
        self.timeout = timeout
        self.extra_args = list(extra_args or [])

    def is_available(self) -> bool:
        return shutil.which(self.lighthouse_path) is not None

    def _binary(self) -> str:
        resolved = shutil.which(self.lighthouse_path)
        if resolved is None:
            raise LighthouseUnavailable(
                "lighthouse was not found on PATH. Install the Apache-2.0 CLI "
                "with `npm install -g lighthouse` or pass lighthouse_path=..."
            )
        return resolved

    def run(
        self, url: str, *, only_categories: list[str] | None = None
    ) -> LighthouseReport:
        binary = self._binary()
        command = [
            binary,
            url,
            "--output",
            "json",
            "--output-path",
            "stdout",
            "--quiet",
            "--chrome-flags=--headless=new --no-sandbox",
        ]
        if only_categories:
            command.append("--only-categories=" + ",".join(only_categories))
        if self.chrome_path:
            command.append(f"--chrome-path={self.chrome_path}")
        command.extend(self.extra_args)

        try:
            completed = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=self.timeout,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError(f"lighthouse timed out after {self.timeout}s") from exc

        if completed.returncode != 0:
            detail = (completed.stderr or completed.stdout or "").strip()
            raise RuntimeError(
                f"lighthouse failed ({completed.returncode}): {detail[:800]}"
            )
        try:
            payload = json.loads(completed.stdout)
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"lighthouse emitted invalid JSON: {exc}") from exc
        return _report_from_json(url, payload)


def run_lighthouse(url: str, **kwargs: Any) -> LighthouseReport:
    return LighthouseRunner(**kwargs).run(url)


__all__ = [
    "LighthouseReport",
    "LighthouseRunner",
    "LighthouseUnavailable",
    "run_lighthouse",
]
