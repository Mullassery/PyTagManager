from __future__ import annotations

import re
import uuid

import pytest
from pytagmanager.control.errors import ValidationError
from pytagmanager.control.ids import (
    container_storage_key,
    new_id,
    normalize_container_id,
    utc_now,
    validate_container_id,
    validate_id,
    validate_name,
)


def test_new_id_is_a_unique_uuid():
    first = new_id()
    second = new_id()
    assert uuid.UUID(first).version == 4
    assert first != second
    assert validate_id(first) == first


def test_gtm_shaped_container_ids_are_preserved():
    value = "GTM-ABC1234"
    assert validate_container_id(value) == value


@pytest.mark.parametrize(
    "value",
    ["", ".GTM", "-GTM", "../escape", "GTM/ABC", "GTM ABC", "G" * 129],
)
def test_invalid_container_ids_are_rejected(value):
    with pytest.raises(ValidationError):
        validate_container_id(value)


def test_non_string_container_id_is_rejected():
    with pytest.raises(ValidationError):
        validate_container_id(123)


def test_container_ids_are_case_insensitively_normalized():
    assert normalize_container_id("GTM-ABC1234") == normalize_container_id("gtm-abc1234")


def test_validate_id_rejects_non_uuid():
    with pytest.raises(ValidationError):
        validate_id("not-a-uuid")
    with pytest.raises(ValidationError):
        validate_id(str(uuid.uuid4()).upper())


def test_container_storage_key_is_safe_stable_and_ids_are_not_paths():
    org_id = new_id()
    key = container_storage_key(org_id, "GTM-ABC1234")
    assert "/" not in key
    assert ".." not in key
    assert key == container_storage_key(org_id, "gtm-abc1234")
    assert key != container_storage_key(org_id, "GTM-OTHER")


def test_validate_name_rejects_control_characters_and_outer_whitespace():
    assert validate_name("Production tags") == "Production tags"
    for value in ("", " leading", "trailing ", "line\nbreak", "tab\tname"):
        with pytest.raises(ValidationError):
            validate_name(value)


def test_utc_now_is_rfc3339_utc():
    value = utc_now()
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z", value)
