from __future__ import annotations

import os

import pytest

from pytagmanager.control.errors import SecretError, ValidationError
from pytagmanager.control.secrets import (
    SecretRef,
    parse_secret_ref,
    resolve_secret_ref,
    secret_ref_from_dict,
    secret_ref_to_dict,
)


def test_secret_references_round_trip():
    ref = parse_secret_ref("env:GA4_API_SECRET")
    assert ref == SecretRef(scheme="env", target="GA4_API_SECRET")
    assert str(ref) == "env:GA4_API_SECRET"
    assert secret_ref_from_dict(secret_ref_to_dict(ref)) == ref


@pytest.mark.parametrize(
    "value",
    ["GA4_SECRET", "plain:text", "env:", "env:1BAD", "file:", "", "vault:thing"],
)
def test_invalid_secret_references_are_rejected(value):
    with pytest.raises(SecretError):
        parse_secret_ref(value)


def test_environment_secret_resolution_uses_the_supplied_environment():
    assert (
        resolve_secret_ref("env:TOKEN", environ={"TOKEN": "s3cr3t"}) == "s3cr3t"
    )
    with pytest.raises(SecretError):
        resolve_secret_ref("env:TOKEN", environ={})
    with pytest.raises(SecretError):
        resolve_secret_ref("env:TOKEN", environ={"TOKEN": ""})


def test_file_secret_resolution_relative_to_home(tmp_path):
    secret_file = tmp_path / "token"
    secret_file.write_text("file-secret\n", encoding="utf-8")
    if os.name == "posix":
        secret_file.chmod(0o600)
    resolved = resolve_secret_ref("file:token", home=tmp_path)
    assert resolved == "file-secret\n"


def test_file_secret_rejects_missing_symlink_and_loose_permissions(tmp_path):
    with pytest.raises(SecretError):
        resolve_secret_ref("file:missing", home=tmp_path)

    target = tmp_path / "target"
    target.write_text("secret", encoding="utf-8")
    if os.name == "posix":
        target.chmod(0o600)
        link = tmp_path / "link"
        link.symlink_to(target)
        with pytest.raises(SecretError):
            resolve_secret_ref("file:link", home=tmp_path)

        target.chmod(0o644)
        with pytest.raises(SecretError):
            resolve_secret_ref("file:target", home=tmp_path)


def test_secret_ref_from_dict_rejects_extra_fields():
    with pytest.raises(ValidationError):
        secret_ref_from_dict({"secret_ref": "env:TOKEN", "value": "raw"})
