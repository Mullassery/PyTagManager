"""Historical tracking-health scores across `--site-wide` runs, and
regression detection between them -- the ObservePoint-inspired "weekly
audits; if the score declines, go inspect and repair" idea noted (and
deliberately deferred) during this feature's original design.

A plain JSON file on disk, same append-and-diff philosophy as
`pytagmanager.version_control.snapshot` -- no database required. This
module only records and compares; *scheduling* recurring runs is left to
the caller's own cron/CI (see README) -- a CLI tool that runs once and
exits is the wrong place to embed a scheduler.
"""

from __future__ import annotations

import datetime
import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

from pytagmanager.sitewide.aggregation import SiteHealthReport

HISTORY_FORMAT_VERSION = 1


@dataclass(frozen=True)
class HealthHistoryEntry:
    timestamp: str
    url: str
    overall_score: int
    pages_scanned: int
    template_scores: Dict[str, int] = field(default_factory=dict)

    @classmethod
    def from_site_health(cls, url: str, site_health: SiteHealthReport) -> "HealthHistoryEntry":
        return cls(
            timestamp=datetime.datetime.now(datetime.timezone.utc).isoformat(),
            url=url,
            overall_score=site_health.overall_score,
            pages_scanned=site_health.pages_scanned,
            template_scores={th.template.label: th.score for th in site_health.template_healths},
        )

    @classmethod
    def from_dict(cls, data: dict) -> "HealthHistoryEntry":
        return cls(
            timestamp=data["timestamp"],
            url=data["url"],
            overall_score=data["overall_score"],
            pages_scanned=data["pages_scanned"],
            template_scores=dict(data.get("template_scores", {})),
        )


@dataclass(frozen=True)
class RegressionAlert:
    message: str
    previous_score: int
    current_score: int
    site_score_drop: int
    template_drops: Dict[str, int] = field(default_factory=dict)


def load_history(path: str) -> List[HealthHistoryEntry]:
    file_path = Path(path)
    if not file_path.exists():
        return []
    data = json.loads(file_path.read_text())
    return [HealthHistoryEntry.from_dict(entry) for entry in data.get("entries", [])]


def append_history_entry(path: str, entry: HealthHistoryEntry) -> None:
    entries = load_history(path)
    entries.append(entry)
    Path(path).write_text(
        json.dumps(
            {"format_version": HISTORY_FORMAT_VERSION, "entries": [asdict(e) for e in entries]},
            indent=2,
        )
    )


def detect_regression(
    history: List[HealthHistoryEntry],
    latest: HealthHistoryEntry,
    threshold: int = 5,
) -> Optional[RegressionAlert]:
    """Compares `latest` against the immediately preceding entry in
    `history` (which should not yet include `latest` itself -- call this
    before `append_history_entry`). Returns None if there's no prior run
    to compare against, or no drop >= `threshold` at either the site or
    template level.
    """
    if not history:
        return None
    previous = history[-1]
    site_drop = previous.overall_score - latest.overall_score

    template_drops = {
        label: previous.template_scores[label] - latest.template_scores[label]
        for label in previous.template_scores
        if label in latest.template_scores
        and (previous.template_scores[label] - latest.template_scores[label]) >= threshold
    }

    if site_drop < threshold and not template_drops:
        return None

    parts = []
    if site_drop >= threshold:
        parts.append(
            f"Overall tracking health score dropped {site_drop} points "
            f"({previous.overall_score} -> {latest.overall_score})."
        )
    for label, drop in template_drops.items():
        parts.append(
            f"{label} template score dropped {drop} points "
            f"({previous.template_scores[label]} -> {latest.template_scores[label]})."
        )

    return RegressionAlert(
        message=" ".join(parts),
        previous_score=previous.overall_score,
        current_score=latest.overall_score,
        site_score_drop=site_drop,
        template_drops=template_drops,
    )
