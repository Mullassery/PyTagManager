"""Regression-category Test Candidates (docs/VISION.md §15, Phase 1.9 item
3): a specific event's specific dataLayer field flipping from present to
absent between two crawls.

Deliberately reuses `dictionary/schema_drift.py`'s `DictionaryDrift`
(Phase 1.7) rather than adding new diff logic to `version_control/diff.py`
-- VISION.md §15 itself calls this out: "Regression-category candidates
connect to existing infrastructure rather than needing new comparison
logic from scratch." `DictionaryDrift.removed_variables` (built from two
`dictionary --format json` snapshots via `data_dictionary_from_json()` +
`diff_dictionaries()`) already *is* the field-level, present-to-absent
diff this category needs.

Only `datalayer_field` removals become regression candidates -- a removed
cookie/localStorage/sessionStorage key is a real finding too, but it's not
what VISION.md §15's regression category is scoped to (a specific
*event's* field), and cookie/storage keys routinely come and go for
reasons (A/B tests, session rotation) that don't map to "a Playwright test
should assert this dataLayer field exists" the way an event field does.
Fields already explained by a `PossibleRename` are excluded -- a
restructure isn't the same claim as an outright removal, and
`dictionary/schema_drift.py`'s own rendering already treats them
separately; duplicating an unhedged "removed" claim on top of an already-
hedged "possible rename" would overclaim.
"""

from __future__ import annotations

from typing import List

from pytagmanager.dictionary.schema_drift import DictionaryDrift
from pytagmanager.testintel.candidates import (
    CATEGORY_REGRESSION,
    SEVERITY_REQUIRES_VERIFICATION,
    TestCandidate,
    format_verification_steps,
)


def generate_regression_candidates(drift: DictionaryDrift, old_crawl_label: str, new_crawl_label: str) -> List[TestCandidate]:
    renamed_paths = {(r.old_source, r.old_path) for r in drift.possible_renames}

    candidates = []
    for variable in drift.removed_variables:
        if variable.source != "datalayer_field":
            continue
        if (variable.source, variable.path) in renamed_paths:
            continue
        event_name, _, field_name = variable.path.partition(".")
        if not field_name:
            continue  # a bare event-name removal (datalayer_event source, not datalayer_field) never reaches here anyway
        candidates.append(
            TestCandidate(
                name=f"'{event_name}' should still include '{field_name}'",
                category=CATEGORY_REGRESSION,
                severity=SEVERITY_REQUIRES_VERIFICATION,
                observed=f"'{field_name}' was present in '{event_name}' as of {old_crawl_label}",
                observed_problem=(
                    f"'{field_name}' is no longer observed in '{event_name}' as of {new_crawl_label} "
                    f"(present on {len(variable.pages_present)} page(s) in {old_crawl_label})"
                ),
                evidence_pages=variable.pages_present,
                suggested_verification=format_verification_steps(
                    CATEGORY_REGRESSION, event_name, None, field=field_name
                ),
                source_root_causes=("datalayer_field_regression",),
            )
        )
    return candidates
