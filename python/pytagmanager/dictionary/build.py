"""Website Data Dictionary (docs/VISION.md §3, Phase 1.7): aggregates
`RuntimeStateSnapshot`s (Phase 1.6) across a crawl into a per-variable
inventory -- every observed cookie/localStorage/sessionStorage key and
dataLayer field, where it was seen, how often, and on which pages.

Every count/frequency here is derived from snapshots an `ObservationSession`
actually captured -- there is no invented "expected but 0%" entry for a
variable this dictionary has never observed; it simply doesn't appear,
matching the "no fabricated placeholders" discipline `sitewide/aggregation.py`
already established.

DataLayer fields are recursively flattened into dot-joined paths
(`event_name.field`, `event_name.field.nested_field`, ...) up to
`_MAX_DATALAYER_DEPTH` levels -- deep enough for schema_drift.py's
rename/restructure detection (docs/VISION.md §5) to see a field move from
`product.price` to `product.pricing.amount`, bounded so a pathological
dataLayer from a crawled third-party page can't blow the recursion stack.
Arrays are recorded as a single `"array"`-typed field at the path they
appear, not itemized (`ecommerce.items[]` stays one field, matching
VISION.md §3's own example) -- indexing into array elements isn't a stable
schema location the way an object key is.
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
    value_type_counts: Tuple[Tuple[str, int], ...] = ()  # (type, observation_count), sorted by type

    @property
    def observed_count(self) -> int:
        return len(self.pages_present)

    @property
    def presence_ratio(self) -> Optional[float]:
        return self.observed_count / self.pages_total if self.pages_total else None

    @property
    def value_type_distribution(self) -> Dict[str, float]:
        """Per-type share of observations, e.g. {"string": 0.96, "number": 0.04}
        -- the basis for dictionary/schema_drift.py's value-distribution-shift
        detection. Empty when there are no recorded observations (e.g. a
        variable built without per-observation counts)."""
        total = sum(count for _, count in self.value_type_counts)
        if not total:
            return {}
        return {value_type: count / total for value_type, count in self.value_type_counts}


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


_MAX_DATALAYER_DEPTH = 6


def _flatten_datalayer_fields(
    prefix: str,
    obj: dict,
    page_url: str,
    timestamp: float,
    accumulators: "Dict[Tuple[str, str], _Accumulator]",
    depth: int = 0,
) -> None:
    """Record `obj`'s keys as dot-joined fields under `prefix`, recursing
    into nested dicts up to `_MAX_DATALAYER_DEPTH` levels. Arrays and
    scalars are recorded but not recursed into further (see module
    docstring)."""
    for key, value in obj.items():
        path = f"{prefix}.{key}"
        accumulators.setdefault(("datalayer_field", path), _Accumulator()).record(
            page_url, _value_type(value), timestamp
        )
        if isinstance(value, dict) and depth < _MAX_DATALAYER_DEPTH:
            _flatten_datalayer_fields(path, value, page_url, timestamp, accumulators, depth + 1)


class _Accumulator:
    __slots__ = ("value_types", "value_type_counts", "pages", "first_observed", "last_observed")

    def __init__(self) -> None:
        self.value_types: set = set()
        self.value_type_counts: Dict[str, int] = {}
        self.pages: set = set()
        self.first_observed: Optional[float] = None
        self.last_observed: Optional[float] = None

    def record(self, page_url: str, value_type: str, timestamp: float) -> None:
        self.value_types.add(value_type)
        self.value_type_counts[value_type] = self.value_type_counts.get(value_type, 0) + 1
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
            _flatten_datalayer_fields(
                event_name,
                {k: v for k, v in item.items() if k != "event"},
                snapshot.page_url,
                snapshot.timestamp,
                accumulators,
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
            value_type_counts=tuple(sorted(acc.value_type_counts.items())),
        )
        for (source, path), acc in sorted(accumulators.items())
    )
    return DataDictionary(variables=variables, pages_total=pages_total)


def data_dictionary_from_json(data: dict) -> DataDictionary:
    """Inverse of `dictionary.report.build_dictionary_json` -- loads a
    previously-saved `pytagmanager dictionary --format json -o old.json`
    export back into a `DataDictionary`, so `dictionary/schema_drift.py` can
    diff it against a fresh run (`pytagmanager dictionary <url> --compare-to
    old.json`)."""
    variables = tuple(
        DictionaryVariable(
            source=v["source"],
            path=v["path"],
            value_types=tuple(v["value_types"]),
            pages_present=tuple(v["pages_present"]),
            pages_total=v["pages_total"],
            first_observed=v["first_observed"],
            last_observed=v["last_observed"],
            value_type_counts=tuple(sorted((t, c) for t, c in v.get("value_type_counts", []))),
        )
        for v in data.get("variables", [])
    )
    return DataDictionary(variables=variables, pages_total=data.get("pages_total", 0))
