"""Website Data Dictionary (docs/VISION.md §3, Phase 1.7): aggregates
`RuntimeStateSnapshot`s (Phase 1.6) across a crawl into a per-variable
inventory -- every observed cookie/localStorage/sessionStorage key and
dataLayer field, where it was seen, how often, and on which pages.

Every count/frequency here is derived from snapshots an `ObservationSession`
actually captured -- there is no invented "expected but 0%" entry for a
variable this dictionary has never observed; it simply doesn't appear,
matching the "no fabricated placeholders" discipline `sitewide/aggregation.py`
already established.

Deliberately one level deep for dataLayer fields (`event_name.field`, not a
recursive flatten of nested objects like `ecommerce.items[]`) -- full schema
modeling of nested dataLayer structures is the schema-drift work later in
Phase 1.7, not this aggregation pass.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from pytagmanager.observability.state import RuntimeStateSnapshot

SOURCES = ("datalayer_event", "datalayer_field", "cookie", "local_storage", "session_storage")


@dataclass(frozen=True)
class DictionaryVariable:
    """One observed variable: a cookie/localStorage/sessionStorage key, a
    dataLayer event name, or a dataLayer event's field (`path` is
    "event_name.field_name" for the latter)."""

    source: str  # one of SOURCES
    path: str
    value_types: Tuple[str, ...]  # sorted, deduped, observed types
    pages_present: Tuple[str, ...]  # page URLs where observed (deduped, sorted)
    pages_total: int  # distinct pages considered across the whole run
    first_observed: float
    last_observed: float

    @property
    def observed_count(self) -> int:
        return len(self.pages_present)

    @property
    def presence_ratio(self) -> Optional[float]:
        return self.observed_count / self.pages_total if self.pages_total else None


@dataclass(frozen=True)
class DataDictionary:
    variables: Tuple[DictionaryVariable, ...] = field(default_factory=tuple)
    pages_total: int = 0

    def by_source(self, source: str) -> List[DictionaryVariable]:
        return [v for v in self.variables if v.source == source]


def _value_type(value) -> str:
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, (int, float)):
        return "number"
    if isinstance(value, dict):
        return "object"
    if isinstance(value, list):
        return "array"
    if value is None:
        return "null"
    return "string"


class _Accumulator:
    __slots__ = ("value_types", "pages", "first_observed", "last_observed")

    def __init__(self) -> None:
        self.value_types: set = set()
        self.pages: set = set()
        self.first_observed: Optional[float] = None
        self.last_observed: Optional[float] = None

    def record(self, page_url: str, value_type: str, timestamp: float) -> None:
        self.value_types.add(value_type)
        self.pages.add(page_url)
        if self.first_observed is None or timestamp < self.first_observed:
            self.first_observed = timestamp
        if self.last_observed is None or timestamp > self.last_observed:
            self.last_observed = timestamp


def build_data_dictionary(snapshots: List[RuntimeStateSnapshot]) -> DataDictionary:
    """`snapshots` may include multiple snapshots per page (e.g. `page_load`
    plus each interaction's before/after) -- `pages_total` dedupes by
    `page_url`, so passing every snapshot from a `--site-wide` run's
    `ObservationSession`s is correct, not double-counting."""
    accumulators: Dict[Tuple[str, str], _Accumulator] = {}
    pages_seen: set = set()

    for snapshot in snapshots:
        pages_seen.add(snapshot.page_url)

        for key, entry in snapshot.cookies.items():
            accumulators.setdefault(("cookie", key), _Accumulator()).record(
                snapshot.page_url, entry.value_type, snapshot.timestamp
            )
        for key, entry in snapshot.local_storage.items():
            accumulators.setdefault(("local_storage", key), _Accumulator()).record(
                snapshot.page_url, entry.value_type, snapshot.timestamp
            )
        for key, entry in snapshot.session_storage.items():
            accumulators.setdefault(("session_storage", key), _Accumulator()).record(
                snapshot.page_url, entry.value_type, snapshot.timestamp
            )
        for item in snapshot.data_layer:
            if not isinstance(item, dict):
                continue
            event_name = item.get("event") or "(unnamed)"
            accumulators.setdefault(("datalayer_event", event_name), _Accumulator()).record(
                snapshot.page_url, "event", snapshot.timestamp
            )
            for key, value in item.items():
                if key == "event":
                    continue
                path = f"{event_name}.{key}"
                accumulators.setdefault(("datalayer_field", path), _Accumulator()).record(
                    snapshot.page_url, _value_type(value), snapshot.timestamp
                )

    pages_total = len(pages_seen)
    variables = tuple(
        DictionaryVariable(
            source=source,
            path=path,
            value_types=tuple(sorted(acc.value_types)),
            pages_present=tuple(sorted(acc.pages)),
            pages_total=pages_total,
            first_observed=acc.first_observed or 0.0,
            last_observed=acc.last_observed or 0.0,
        )
        for (source, path), acc in sorted(accumulators.items())
    )
    return DataDictionary(variables=variables, pages_total=pages_total)
