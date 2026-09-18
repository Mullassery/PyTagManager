"""Performance regression detection (docs/VISION.md §16, Phase 1.95 item
8): ties into the same append-and-diff pattern `sitewide/history.py`
already established for tracking-health scores (a plain JSON file on
disk, compare the latest entry against the immediately preceding one) --
not a literal reuse of `HealthHistoryEntry`, whose fields are shaped for a
0-100 health score and don't fit raw performance metrics (LCP/TBT ms).
Same philosophy, adapted data shape, matching how `testintel/regression.py`
(Phase 1.9) already reused `dictionary/schema_drift.py`'s pattern rather
than force-fitting an unrelated type.

A newly-introduced script correlated with a regression is reported as a
*correlation*, per VISION.md §16's own framing -- "a newly-introduced
script correlated with a TBT/LCP delta between two crawls" -- never
worded as a proven cause.
"""

from __future__ import annotations

import datetime
import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import List, Optional, Sequence, Tuple

from pytagmanager.perf.measure import PerformanceBaseline

PERF_HISTORY_FORMAT_VERSION = 1
DEFAULT_LCP_REGRESSION_THRESHOLD_MS = 500.0
DEFAULT_TBT_REGRESSION_THRESHOLD_MS = 100.0


@dataclass(frozen=True)
class PerformanceHistoryEntry:
    timestamp: str
    url: str
    median_lcp_ms: Optional[float]
    median_tbt_ms: Optional[float]
    median_cls: Optional[float]
    median_inp_ms: Optional[float]
    script_urls: Tuple[str, ...] = field(default_factory=tuple)

    @classmethod
    def from_baseline(cls, baseline: PerformanceBaseline, script_urls: Sequence[str] = ()) -> "PerformanceHistoryEntry":
        return cls(
            timestamp=datetime.datetime.now(datetime.timezone.utc).isoformat(),
            url=baseline.url,
            median_lcp_ms=baseline.median_lcp_ms,
            median_tbt_ms=baseline.median_tbt_ms,
            median_cls=baseline.median_cls,
            median_inp_ms=baseline.median_inp_ms,
            script_urls=tuple(sorted(script_urls)),
        )

    @classmethod
    def from_dict(cls, data: dict) -> "PerformanceHistoryEntry":
        return cls(
            timestamp=data["timestamp"],
            url=data["url"],
            median_lcp_ms=data.get("median_lcp_ms"),
            median_tbt_ms=data.get("median_tbt_ms"),
            median_cls=data.get("median_cls"),
            median_inp_ms=data.get("median_inp_ms"),
            script_urls=tuple(data.get("script_urls", ())),
        )


@dataclass(frozen=True)
class PerformanceRegressionAlert:
    message: str
    metric: str
    previous_value: float
    current_value: float
    new_scripts: Tuple[str, ...] = field(default_factory=tuple)


def load_performance_history(path: str) -> List[PerformanceHistoryEntry]:
    file_path = Path(path)
    if not file_path.exists():
        return []
    data = json.loads(file_path.read_text())
    return [PerformanceHistoryEntry.from_dict(entry) for entry in data.get("entries", [])]


def append_performance_history_entry(path: str, entry: PerformanceHistoryEntry) -> None:
    entries = load_performance_history(path)
    entries.append(entry)
    Path(path).write_text(
        json.dumps({"format_version": PERF_HISTORY_FORMAT_VERSION, "entries": [asdict(e) for e in entries]}, indent=2)
    )


def detect_performance_regression(
    history: Sequence[PerformanceHistoryEntry],
    latest: PerformanceHistoryEntry,
    *,
    lcp_threshold_ms: float = DEFAULT_LCP_REGRESSION_THRESHOLD_MS,
    tbt_threshold_ms: float = DEFAULT_TBT_REGRESSION_THRESHOLD_MS,
) -> List[PerformanceRegressionAlert]:
    """Compares `latest` against the immediately preceding entry in
    `history` (which should not yet include `latest` -- call this before
    `append_performance_history_entry`, same calling convention as
    `sitewide.history.detect_regression`). Returns one alert per metric
    that regressed beyond its threshold; empty if there's no prior entry
    or nothing crossed a threshold."""
    if not history:
        return []
    previous = history[-1]
    new_scripts = tuple(sorted(set(latest.script_urls) - set(previous.script_urls)))

    alerts = []
    for metric, threshold in (("median_lcp_ms", lcp_threshold_ms), ("median_tbt_ms", tbt_threshold_ms)):
        prev_val = getattr(previous, metric)
        cur_val = getattr(latest, metric)
        if prev_val is None or cur_val is None:
            continue
        delta = cur_val - prev_val
        if delta < threshold:
            continue
        message = f"{metric} regressed by {delta:.1f} vs. the previous run ({prev_val:.1f} -> {cur_val:.1f})."
        if new_scripts:
            shown = ", ".join(new_scripts[:3]) + ("..." if len(new_scripts) > 3 else "")
            message += (
                f" Correlated with {len(new_scripts)} newly-introduced script(s) (not proven causal): {shown}."
            )
        alerts.append(
            PerformanceRegressionAlert(
                message=message, metric=metric, previous_value=prev_val, current_value=cur_val, new_scripts=new_scripts
            )
        )
    return alerts
