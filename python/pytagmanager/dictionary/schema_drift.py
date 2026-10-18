"""DataLayer schema drift detection (docs/VISION.md §5, Phase 1.7 item 3):
diff two `DataDictionary`s (a saved baseline vs. a fresh run) down to the
per-field level -- new/removed fields, type-distribution shifts (e.g.
"transaction_id: 96% string, 4% number"), and possible renames.

Deliberately lives in `dictionary/`, not `version_control/diff.py`:
`diff.py` diffs `CrawlSnapshot`s (DOM elements + recommendations), a
different domain object with a different identity/matching scheme
(`SnapshotNode.identity_key`) than a `DataDictionary`'s (source, path)
variables. Reusing its *pattern* (in-memory dataclass diff, no I/O) rather
than its types keeps both diffs simple instead of forcing one module to
understand two unrelated snapshot formats.

**Possible-rename detection is a hedged heuristic, not a claim of fact.**
A field disappearing from one dictionary while a similarly-named field
appears elsewhere under the same dataLayer event is *evidence* consistent
with a rename/restructure -- it is reported as `PossibleRename` with a
similarity score, never silently merged into "unchanged." The exit-criteria
case this is built for (`product.price` -> `product.pricing.amount`) is
exactly the kind of restructure `build.py`'s recursive dataLayer
flattening (see that module's docstring) makes visible as two ordinary
field paths in the first place.
"""

from __future__ import annotations

import difflib
from dataclasses import dataclass, field
from typing import Dict, List, Tuple

from pytagmanager.dictionary.build import DataDictionary, DictionaryVariable
from pytagmanager.dictionary.gtm_usage import GtmUsageIndex

# Minimum leaf-name similarity (difflib.SequenceMatcher ratio) to surface a
# possible rename. Below this, two unrelated fields disappearing/appearing
# in the same event are just an add and a remove, not flagged as related.
_RENAME_SIMILARITY_THRESHOLD = 0.5

# Minimum absolute change in a type's observed share to call it a
# "distribution shift" worth reporting, rather than sampling noise.
_TYPE_SHARE_SHIFT_THRESHOLD = 0.05


@dataclass(frozen=True)
class TypeDistributionShift:
    source: str
    path: str
    old_distribution: Dict[str, float]
    new_distribution: Dict[str, float]

    def render(self) -> str:
        types = sorted(set(self.old_distribution) | set(self.new_distribution))
        parts = [f"{t}: {self.old_distribution.get(t, 0.0):.0%} -> {self.new_distribution.get(t, 0.0):.0%}" for t in types]
        return f"{self.path} ({self.source}): " + ", ".join(parts)


@dataclass(frozen=True)
class PossibleRename:
    old_source: str
    old_path: str
    new_source: str
    new_path: str
    similarity: float

    def render(self) -> str:
        return f"{self.old_path} -> {self.new_path} (leaf-name similarity {self.similarity:.0%})"


@dataclass(frozen=True)
class DictionaryDrift:
    added_variables: List[DictionaryVariable] = field(default_factory=list)
    removed_variables: List[DictionaryVariable] = field(default_factory=list)
    type_distribution_shifts: List[TypeDistributionShift] = field(default_factory=list)
    possible_renames: List[PossibleRename] = field(default_factory=list)

    @property
    def has_changes(self) -> bool:
        return bool(
            self.added_variables or self.removed_variables or self.type_distribution_shifts or self.possible_renames
        )


def _leaf_name(path: str) -> str:
    return path.rsplit(".", 1)[-1]


def _event_prefix(path: str) -> str:
    return path.split(".", 1)[0]


def _type_shift(old: DictionaryVariable, new: DictionaryVariable) -> "TypeDistributionShift | None":
    old_dist = old.value_type_distribution
    new_dist = new.value_type_distribution
    if not old_dist or not new_dist:
        return None
    types = set(old_dist) | set(new_dist)
    shifted = any(abs(old_dist.get(t, 0.0) - new_dist.get(t, 0.0)) >= _TYPE_SHARE_SHIFT_THRESHOLD for t in types)
    if not shifted:
        return None
    return TypeDistributionShift(source=new.source, path=new.path, old_distribution=old_dist, new_distribution=new_dist)


def _possible_renames(
    removed: List[DictionaryVariable], added: List[DictionaryVariable]
) -> List[PossibleRename]:
    """Only compares datalayer_field variables within the same event
    namespace (the part of the path before the first '.') -- a cookie
    disappearing and a localStorage key appearing is never a "rename"."""
    removed_fields = [v for v in removed if v.source == "datalayer_field"]
    added_fields = [v for v in added if v.source == "datalayer_field"]
    matches: List[PossibleRename] = []
    claimed_new: set = set()

    for old_var in removed_fields:
        best: "Tuple[float, DictionaryVariable] | None" = None
        for new_var in added_fields:
            if new_var.path in claimed_new:
                continue
            if _event_prefix(old_var.path) != _event_prefix(new_var.path):
                continue
            same_types = set(old_var.value_types) == set(new_var.value_types) and bool(old_var.value_types)
            similarity = difflib.SequenceMatcher(None, _leaf_name(old_var.path), _leaf_name(new_var.path)).ratio()
            score = similarity + (0.2 if same_types else 0.0)
            if similarity < _RENAME_SIMILARITY_THRESHOLD and not same_types:
                continue
            if best is None or score > best[0]:
                best = (score, new_var)
        if best is not None:
            _, new_var = best
            claimed_new.add(new_var.path)
            matches.append(
                PossibleRename(
                    old_source=old_var.source,
                    old_path=old_var.path,
                    new_source=new_var.source,
                    new_path=new_var.path,
                    similarity=difflib.SequenceMatcher(
                        None, _leaf_name(old_var.path), _leaf_name(new_var.path)
                    ).ratio(),
                )
            )
    return matches


def diff_dictionaries(old: DataDictionary, new: DataDictionary) -> DictionaryDrift:
    old_by_key = {(v.source, v.path): v for v in old.variables}
    new_by_key = {(v.source, v.path): v for v in new.variables}

    added_keys = new_by_key.keys() - old_by_key.keys()
    removed_keys = old_by_key.keys() - new_by_key.keys()
    common_keys = old_by_key.keys() & new_by_key.keys()

    added_variables = [new_by_key[k] for k in sorted(added_keys)]
    removed_variables = [old_by_key[k] for k in sorted(removed_keys)]

    type_shifts = []
    for key in sorted(common_keys):
        shift = _type_shift(old_by_key[key], new_by_key[key])
        if shift is not None:
            type_shifts.append(shift)

    possible_renames = _possible_renames(removed_variables, added_variables)

    return DictionaryDrift(
        added_variables=added_variables,
        removed_variables=removed_variables,
        type_distribution_shifts=type_shifts,
        possible_renames=possible_renames,
    )


def render_drift_report(
    drift: DictionaryDrift, gtm_usage: "GtmUsageIndex | None" = None
) -> str:
    lines = ["PyTagManager Data Dictionary Schema Drift", "=" * 42, ""]

    if drift.possible_renames:
        lines.append(f"Possible renames ({len(drift.possible_renames)}):")
        lines.extend(f"  ~ {r.render()}" for r in drift.possible_renames)
        lines.append("")

    renamed_paths = {(r.old_source, r.old_path) for r in drift.possible_renames} | {
        (r.new_source, r.new_path) for r in drift.possible_renames
    }

    remaining_added = [v for v in drift.added_variables if (v.source, v.path) not in renamed_paths]
    remaining_removed = [v for v in drift.removed_variables if (v.source, v.path) not in renamed_paths]

    if remaining_added:
        lines.append(f"Added ({len(remaining_added)}):")
        lines.extend(f"  + {v.source}: {v.path}" for v in remaining_added)
        lines.append("")

    if remaining_removed:
        lines.append(f"Removed ({len(remaining_removed)}):")
        lines.extend(f"  - {v.source}: {v.path}" for v in remaining_removed)
        lines.append("")

    if drift.type_distribution_shifts:
        lines.append(f"Type distribution shifts ({len(drift.type_distribution_shifts)}):")
        lines.extend(f"  ! {s.render()}" for s in drift.type_distribution_shifts)
        lines.append("")

    if not drift.has_changes:
        lines.append("No schema drift detected.")

    if gtm_usage is not None:
        blast_radius = gtm_usage.render_drift_blast_radius(drift)
        if blast_radius:
            lines.append("")
            lines.append(blast_radius)

    return "\n".join(lines)


def build_drift_json(
    drift: DictionaryDrift, gtm_usage: "GtmUsageIndex | None" = None
) -> dict:
    result = {
        "added_variables": [{"source": v.source, "path": v.path} for v in drift.added_variables],
        "removed_variables": [{"source": v.source, "path": v.path} for v in drift.removed_variables],
        "type_distribution_shifts": [
            {
                "source": s.source,
                "path": s.path,
                "old_distribution": s.old_distribution,
                "new_distribution": s.new_distribution,
            }
            for s in drift.type_distribution_shifts
        ],
        "possible_renames": [
            {
                "old_source": r.old_source,
                "old_path": r.old_path,
                "new_source": r.new_source,
                "new_path": r.new_path,
                "similarity": round(r.similarity, 4),
            }
            for r in drift.possible_renames
        ],
    }
    if gtm_usage is not None:
        blast_radius = gtm_usage.drift_blast_radius(drift)
        if blast_radius:
            result["gtm_blast_radius"] = blast_radius
    return result
