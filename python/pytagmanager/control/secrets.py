"""Secret references that keep raw credentials out of stored configuration."""

from __future__ import annotations

import os
import re
import stat
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

from pytagmanager.control.errors import SecretError, ValidationError

_ENV_NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_REF_RE = re.compile(r"^(env|file):(.+)$", re.DOTALL)


@dataclass(frozen=True)
class SecretRef:
    scheme: str
    target: str

    @classmethod
    def parse(cls, value: str) -> "SecretRef":
        if not isinstance(value, str):
            raise SecretError(f"secret reference must be a string, got {type(value).__name__}")
        match = _REF_RE.fullmatch(value)
        if not match:
            raise SecretError(
                f"invalid secret reference {value!r}; expected 'env:NAME' or 'file:PATH'"
            )
        scheme, target = match.group(1), match.group(2)
        if scheme == "env" and not _ENV_NAME_RE.fullmatch(target):
            raise SecretError(f"invalid environment variable name in secret reference: {target!r}")
        if scheme == "file" and not target:
            raise SecretError("file secret reference must include a path")
        return cls(scheme=scheme, target=target)

    def __str__(self) -> str:
        return f"{self.scheme}:{self.target}"


def parse_secret_ref(value: str) -> SecretRef:
    return SecretRef.parse(value)


def resolve_secret_ref(
    value: str | SecretRef,
    *,
    home: str | Path | None = None,
    environ: Mapping[str, str] | None = None,
) -> str:
    """Resolve a secret reference without ever persisting the resolved value."""
    ref = value if isinstance(value, SecretRef) else SecretRef.parse(value)
    environment = os.environ if environ is None else environ

    if ref.scheme == "env":
        try:
            secret = environment[ref.target]
        except KeyError:
            raise SecretError(f"environment variable {ref.target!r} is not set") from None
        if secret == "":
            raise SecretError(f"environment variable {ref.target!r} is empty")
        return secret

    path = Path(ref.target).expanduser()
    if not path.is_absolute():
        path = Path(home) / path if home is not None else path
    if path.is_symlink():
        raise SecretError(f"secret file must not be a symlink: {path}")
    path = path.resolve()
    try:
        metadata = path.stat()
    except OSError as exc:
        raise SecretError(f"cannot read secret file {path}: {exc}") from exc
    if not stat.S_ISREG(metadata.st_mode):
        raise SecretError(f"secret file is not a regular file: {path}")
    if os.name == "posix" and metadata.st_mode & 0o077:
        raise SecretError(
            f"secret file {path} is readable or writable by group/other; use chmod 600"
        )
    try:
        return path.read_text(encoding="utf-8")
    except OSError as exc:
        raise SecretError(f"cannot read secret file {path}: {exc}") from exc


def secret_ref_to_dict(value: str | SecretRef) -> dict[str, str]:
    ref = value if isinstance(value, SecretRef) else SecretRef.parse(value)
    return {"secret_ref": str(ref)}


def secret_ref_from_dict(value: Mapping[str, object]) -> SecretRef:
    if not isinstance(value, Mapping) or set(value) != {"secret_ref"}:
        raise ValidationError("secret reference object must contain only 'secret_ref'")
    raw = value["secret_ref"]
    if not isinstance(raw, str):
        raise ValidationError("'secret_ref' must be a string")
    return SecretRef.parse(raw)
