"""Deterministic comparison between immutable configuration revisions."""

from __future__ import annotations

import copy
from dataclasses import dataclass
from typing import Any

from pytagmanager.control.checksums import canonical_json
from pytagmanager.control.models import ConfigPayload, ConfigRevision

_OBJECT_ORDER = {"tag": 0, "trigger": 1, "variable": 2, "destination": 3}


@dataclass(frozen=True)
class ObjectChange:
    object_type: str
    object_id: str
    change: str
    fields: tuple[str, ...]
    before: dict[str, Any] | None = None
    after: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "object_type": self.object_type,
            "object_id": self.object_id,
            "change": self.change,
            "fields": list(self.fields),
        }
        if self.before is not None:
            result["before"] = copy.deepcopy(self.before)
        if self.after is not None:
            result["after"] = copy.deepcopy(self.after)
        return result


@dataclass(frozen=True)
class RevisionDiff:
    container_id: str
    from_config_version: str
    to_config_version: str
    from_revision_number: int
    to_revision_number: int
    from_checksum: str
    to_checksum: str
    changes: tuple[ObjectChange, ...]

    @property
    def summary(self) -> dict[str, int]:
        result = {"added": 0, "removed": 0, "changed": 0}
        for change in self.changes:
            result[change.change] += 1
        return result

    @property
    def identical(self) -> bool:
        return not self.changes

    def to_dict(self) -> dict[str, Any]:
        return {
            "container_id": self.container_id,
            "from": {
                "config_version": self.from_config_version,
                "revision_number": self.from_revision_number,
                "checksum": self.from_checksum,
            },
            "to": {
                "config_version": self.to_config_version,
                "revision_number": self.to_revision_number,
                "checksum": self.to_checksum,
            },
            "identical": self.identical,
            "summary": self.summary,
            "changes": [change.to_dict() for change in self.changes],
        }


def _objects(payload: ConfigPayload) -> dict[tuple[str, str], dict[str, Any]]:
    result = {}
    for object_type, item in payload.all_objects():
        object_id = getattr(item, f"{object_type}_id")
        result[(object_type, object_id)] = item.to_dict()
    return result


def _changed_fields(before: dict[str, Any], after: dict[str, Any]) -> tuple[str, ...]:
    return tuple(sorted(key for key in set(before) | set(after) if before.get(key) != after.get(key)))


def diff_payloads(
    payload_from: ConfigPayload,
    payload_to: ConfigPayload,
) -> tuple[ObjectChange, ...]:
    before = _objects(payload_from)
    after = _objects(payload_to)
    changes = []
    for key in sorted(set(before) | set(after), key=lambda item: (_OBJECT_ORDER[item[0]], item[1])):
        old = before.get(key)
        new = after.get(key)
        object_type, object_id = key
        if old is None:
            changes.append(
                ObjectChange(object_type, object_id, "added", (), after=copy.deepcopy(new))
            )
        elif new is None:
            changes.append(
                ObjectChange(object_type, object_id, "removed", (), before=copy.deepcopy(old))
            )
        elif canonical_json(old) != canonical_json(new):
            changes.append(
                ObjectChange(
                    object_type,
                    object_id,
                    "changed",
                    _changed_fields(old, new),
                    before=copy.deepcopy(old),
                    after=copy.deepcopy(new),
                )
            )
    return tuple(changes)


def diff_revisions(revision_from: ConfigRevision, revision_to: ConfigRevision) -> RevisionDiff:
    if revision_from.container_id != revision_to.container_id:
        raise ValueError("cannot diff revisions from different containers")
    return RevisionDiff(
        container_id=revision_from.container_id,
        from_config_version=revision_from.config_version,
        to_config_version=revision_to.config_version,
        from_revision_number=revision_from.revision_number,
        to_revision_number=revision_to.revision_number,
        from_checksum=revision_from.checksum,
        to_checksum=revision_to.checksum,
        changes=diff_payloads(revision_from.payload, revision_to.payload),
    )
