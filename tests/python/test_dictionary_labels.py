"""Tests for Phase 1.7's presence-vs-availability labeling (docs/VISION.md
§4): Exists/Exposed/Accessible derived from a DictionaryVariable's source."""

from __future__ import annotations

from pytagmanager.dictionary.build import DictionaryVariable
from pytagmanager.dictionary.labels import (
    ACCESSIBLE,
    POSSIBLY_ACCESSIBLE,
    label_presence,
)


def _variable(source: str, path: str = "x") -> DictionaryVariable:
    return DictionaryVariable(
        source=source,
        path=path,
        value_types=("string",),
        pages_present=("https://example.com/",),
        pages_total=1,
        first_observed=1.0,
        last_observed=1.0,
    )


def test_datalayer_field_is_exposed_and_accessible():
    label = label_presence(_variable("datalayer_field", "purchase.transaction_id"))
    assert label.exists is True
    assert label.exposed is True
    assert label.accessibility == ACCESSIBLE
    assert "Data Layer Variable" in label.rationale


def test_datalayer_event_is_exposed_and_accessible():
    label = label_presence(_variable("datalayer_event", "purchase"))
    assert label.exposed is True
    assert label.accessibility == ACCESSIBLE


def test_cookie_is_not_exposed_but_accessible_via_builtin_variable():
    label = label_presence(_variable("cookie", "session_id"))
    assert label.exists is True
    assert label.exposed is False
    assert label.accessibility == ACCESSIBLE
    assert "1st Party Cookie" in label.rationale


def test_local_storage_is_only_possibly_accessible():
    label = label_presence(_variable("local_storage", "cart_id"))
    assert label.exposed is False
    assert label.accessibility == POSSIBLY_ACCESSIBLE
    assert "Custom JavaScript" in label.rationale


def test_session_storage_is_only_possibly_accessible():
    label = label_presence(_variable("session_storage", "draft_form"))
    assert label.accessibility == POSSIBLY_ACCESSIBLE
