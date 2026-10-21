from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from pytagmanager.events import (
    SCHEMA_VERSION,
    EventValidationError,
    batch_document,
    is_sensitive_property,
    parse_event,
    validate_batch,
    validate_event,
)

SCHEMA_ROOT = Path(__file__).resolve().parents[2] / "schemas"
FIXTURES = SCHEMA_ROOT / "events" / "v1" / "fixtures"
NOW = datetime(2026, 10, 20, 12, 5, 0, tzinfo=timezone.utc)


def _fixture(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.mark.parametrize("path", sorted((FIXTURES / "valid").glob("*.json")))
def test_valid_fixtures_parse(path):
    event = parse_event(_fixture(path), now=NOW, max_skew_seconds=3600)
    assert event["schema_version"] == SCHEMA_VERSION
    assert event["event_id"]
    assert event["properties"] == _fixture(path)["properties"]


@pytest.mark.parametrize("path", sorted((FIXTURES / "invalid").glob("*.json")))
def test_invalid_fixtures_are_rejected(path):
    issues = validate_event(_fixture(path), now=NOW, max_skew_seconds=None)
    assert issues, f"{path.name} unexpectedly passed"


def test_validation_codes_are_specific():
    cases = {
        "missing_event_name.json": "required",
        "bad_timestamp.json": "invalid_timestamp",
        "unknown_platform.json": "invalid_platform",
        "sensitive_property.json": "sensitive_property",
        "bad_consent.json": "invalid_consent",
        "unknown_top_level.json": "unknown_field",
        "wrong_schema_version.json": "unsupported_schema",
    }
    for name, code in cases.items():
        issues = validate_event(
            _fixture(FIXTURES / "invalid" / name),
            now=NOW,
            max_skew_seconds=None,
        )
        assert code in {issue.code for issue in issues}, name


def test_parse_event_normalizes_timestamp_and_sorts_consent():
    raw = _fixture(FIXTURES / "valid" / "ios_purchase.json")
    event = parse_event(raw, now=NOW, max_skew_seconds=3600)
    assert event["timestamp"] == "2026-10-20T12:02:03.000Z"
    assert list(event["consent"]["purposes"]) == ["advertising", "analytics"]


def test_clock_skew_is_configurable():
    raw = _fixture(FIXTURES / "valid" / "web_page_view.json")
    assert any(
        issue.code == "timestamp_skew"
        for issue in validate_event(raw, now=NOW, max_skew_seconds=10)
    )
    assert not validate_event(raw, now=NOW, max_skew_seconds=None)


def test_oversized_event_is_rejected():
    raw = _fixture(FIXTURES / "valid" / "minimal_server.json")
    raw["properties"] = {"blob": "x" * 40_000}
    issues = validate_event(raw, now=NOW, max_skew_seconds=None)
    assert {issue.code for issue in issues} >= {"too_large", "too_long"}


def test_nested_sensitive_property_is_rejected():
    raw = _fixture(FIXTURES / "valid" / "minimal_server.json")
    raw["properties"] = {"profile": {"contact": {"email_address": "a@b.c"}}}
    assert any(
        issue.code == "sensitive_property"
        for issue in validate_event(raw, now=NOW, max_skew_seconds=None)
    )


def test_hashed_sensitive_properties_are_allowed():
    raw = _fixture(FIXTURES / "valid" / "minimal_server.json")
    raw["properties"] = {"email_sha256": "abc123", "hashed_phone": "def456"}
    assert not validate_event(raw, now=NOW, max_skew_seconds=None)
    assert is_sensitive_property("user_email")
    assert not is_sensitive_property("email_sha256")


def test_event_name_and_property_limits():
    raw = _fixture(FIXTURES / "valid" / "minimal_server.json")
    raw["event_name"] = "Bad Name"
    raw["properties"] = {"a" * 70: 1}
    codes = {
        issue.code
        for issue in validate_event(raw, now=NOW, max_skew_seconds=None)
    }
    assert "invalid_format" in codes
    assert "invalid_key" in codes


def test_batch_validation_is_partial():
    valid = _fixture(FIXTURES / "valid" / "minimal_server.json")
    invalid = _fixture(FIXTURES / "invalid" / "missing_event_name.json")
    accepted, rejected = validate_batch(
        batch_document([valid, invalid]), now=NOW, max_skew_seconds=None
    )
    assert len(accepted) == 1
    assert len(rejected) == 1
    assert rejected[0]["index"] == 1
    assert rejected[0]["issues"][0]["code"] == "required"


def test_batch_envelope_limits_and_unknown_fields():
    valid = _fixture(FIXTURES / "valid" / "minimal_server.json")
    with pytest.raises(EventValidationError):
        validate_batch({"events": []}, now=NOW)
    with pytest.raises(EventValidationError):
        validate_batch({"schema_version": "1.0", "events": [valid] * 101}, now=NOW)
    with pytest.raises(EventValidationError):
        validate_batch(
            {"schema_version": "1.0", "events": [valid], "destination": "https://bad"},
            now=NOW,
        )


def test_schema_files_are_valid_json_and_versioned():
    for path in (SCHEMA_ROOT / "events" / "v1").glob("*.schema.json"):
        document = json.loads(path.read_text(encoding="utf-8"))
        assert document["$schema"].startswith("https://json-schema.org/")
        assert "title" in document
