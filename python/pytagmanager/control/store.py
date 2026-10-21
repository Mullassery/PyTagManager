"""Durable, atomic, file-backed storage for control-plane state."""

from __future__ import annotations

import json
import os
import tempfile
import time
from contextlib import contextmanager
from dataclasses import replace
from pathlib import Path
from typing import Any, Iterator, Mapping

from pytagmanager.control.checksums import canonical_json
from pytagmanager.control.errors import (
    ConflictError,
    ControlError,
    CorruptStoreError,
    NotFoundError,
    ValidationError,
)
from pytagmanager.control.ids import (
    container_storage_key,
    new_id,
    utc_now,
    validate_id,
)
from pytagmanager.control.models import (
    AuditEvent,
    ConfigRevision,
    Container,
    Environment,
    Organization,
    Workspace,
)
from pytagmanager.control.schema import migrate_document, unwrap_document, wrap_document

DEFAULT_HOME_ENV = "PYTAGMANAGER_HOME"


def default_home() -> Path:
    override = os.environ.get(DEFAULT_HOME_ENV)
    if override:
        return Path(override).expanduser()
    return Path.home() / ".pytagmanager"


def _acquire_lock(handle: Any, timeout: float) -> None:
    try:
        import fcntl
    except ImportError:
        fcntl = None
    if fcntl is not None:
        deadline = time.monotonic() + timeout
        while True:
            try:
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                return
            except (BlockingIOError, OSError):
                if time.monotonic() >= deadline:
                    raise ControlError("timed out waiting for the control-plane store lock")
                time.sleep(0.05)

    try:
        import msvcrt
    except ImportError:
        msvcrt = None
    if msvcrt is not None:
        deadline = time.monotonic() + timeout
        while True:
            try:
                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
                return
            except OSError:
                if time.monotonic() >= deadline:
                    raise ControlError("timed out waiting for the control-plane store lock")
                time.sleep(0.05)
    return


def _release_lock(handle: Any) -> None:
    try:
        import fcntl
    except ImportError:
        fcntl = None
    if fcntl is not None:
        fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        return
    try:
        import msvcrt
    except ImportError:
        msvcrt = None
    if msvcrt is not None:
        handle.seek(0)
        msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)


def _fsync_dir(path: Path) -> None:
    if os.name != "posix":
        return
    try:
        descriptor = os.open(path, os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


class FileStore:
    """Local state store with immutable revisions and compare-and-swap support."""

    def __init__(self, home: str | Path | None = None) -> None:
        self.root = Path(home).expanduser() if home is not None else default_home()

    @property
    def metadata_path(self) -> Path:
        return self.root / "store.json"

    @property
    def organizations_dir(self) -> Path:
        return self.root / "orgs"

    def container_dir(self, org_id: str, container_id: str) -> Path:
        org_id = validate_id(org_id, field="org_id")
        return self.organizations_dir / org_id / "containers" / container_storage_key(org_id, container_id)

    def _ensure_layout(self) -> None:
        (self.root / ".locks").mkdir(parents=True, exist_ok=True)
        self.organizations_dir.mkdir(parents=True, exist_ok=True)
        self._chmod(self.root, 0o700)
        self._chmod(self.root / ".locks", 0o700)
        self._chmod(self.organizations_dir, 0o700)

    @staticmethod
    def _chmod(path: Path, mode: int) -> None:
        if os.name == "posix":
            try:
                path.chmod(mode)
            except OSError:
                pass

    @contextmanager
    def lock(self, *, timeout: float = 10.0) -> Iterator[None]:
        self._ensure_layout()
        lock_path = self.root / ".locks" / "store.lock"
        with open(lock_path, "a+", encoding="utf-8") as handle:
            _acquire_lock(handle, timeout)
            try:
                yield
            finally:
                _release_lock(handle)

    def initialize(self) -> dict[str, Any]:
        with self.lock():
            if not self.metadata_path.exists():
                self._write_document(
                    self.metadata_path,
                    "store",
                    {
                        "store_id": new_id(),
                        "created_at": utc_now(),
                        "default_org_id": None,
                        "default_workspace_id": None,
                    },
                )
            return self.read_meta()

    def read_meta(self) -> dict[str, Any]:
        data = self._read_document(self.metadata_path, "store")
        expected = {"store_id", "created_at", "default_org_id", "default_workspace_id"}
        if set(data) != expected:
            raise CorruptStoreError("store metadata has an unexpected shape")
        validate_id(data["store_id"], field="store_id")
        for key in ("default_org_id", "default_workspace_id"):
            if data[key] is not None:
                validate_id(data[key], field=key)
        return dict(data)

    def write_meta(self, data: Mapping[str, Any]) -> None:
        expected = {"store_id", "created_at", "default_org_id", "default_workspace_id"}
        if set(data) != expected:
            raise ValidationError("store metadata has an unexpected shape")
        self._write_document(self.metadata_path, "store", data)

    def save_organization(self, organization: Organization) -> None:
        path = self.organizations_dir / organization.org_id / "organization.json"
        self._write_document(path, "organization", organization.to_dict())

    def get_organization(self, org_id: str) -> Organization:
        org_id = validate_id(org_id, field="org_id")
        path = self.organizations_dir / org_id / "organization.json"
        data = self._read_document(path, "organization")
        organization = Organization.from_dict(data)
        if organization.org_id != org_id:
            raise CorruptStoreError(f"organization file {path} belongs to {organization.org_id}")
        return organization

    def list_organizations(self) -> list[Organization]:
        result = []
        for path in sorted(self.organizations_dir.glob("*/organization.json")):
            result.append(Organization.from_dict(self._read_document(path, "organization")))
        return result

    def workspace_dir(self, org_id: str) -> Path:
        return self.organizations_dir / validate_id(org_id, field="org_id") / "workspaces"

    def save_workspace(self, workspace: Workspace) -> None:
        path = self.workspace_dir(workspace.org_id) / f"{workspace.workspace_id}.json"
        self._write_document(path, "workspace", workspace.to_dict())

    def get_workspace(self, org_id: str, workspace_id: str) -> Workspace:
        org_id = validate_id(org_id, field="org_id")
        workspace_id = validate_id(workspace_id, field="workspace_id")
        path = self.workspace_dir(org_id) / f"{workspace_id}.json"
        workspace = Workspace.from_dict(self._read_document(path, "workspace"))
        if workspace.org_id != org_id or workspace.workspace_id != workspace_id:
            raise CorruptStoreError(f"workspace file {path} has inconsistent identity")
        return workspace

    def list_workspaces(self, org_id: str) -> list[Workspace]:
        result = []
        for path in sorted(self.workspace_dir(org_id).glob("*.json")):
            result.append(Workspace.from_dict(self._read_document(path, "workspace")))
        return result

    def save_container(self, container: Container) -> None:
        path = self.container_dir(container.org_id, container.container_id) / "container.json"
        self._write_document(path, "container", container.to_dict())

    def get_container(self, org_id: str, container_id: str) -> Container:
        path = self.container_dir(org_id, container_id) / "container.json"
        container = Container.from_dict(self._read_document(path, "container"))
        if container.org_id != org_id or container.uniqueness_key != container_id.casefold():
            raise CorruptStoreError(f"container file {path} has inconsistent identity")
        return container

    def container_exists(self, org_id: str, container_id: str) -> bool:
        path = self.container_dir(org_id, container_id) / "container.json"
        return path.exists()

    def list_containers(self, org_id: str) -> list[Container]:
        org_id = validate_id(org_id, field="org_id")
        result = []
        base = self.organizations_dir / org_id / "containers"
        for path in sorted(base.glob("*/container.json")):
            result.append(Container.from_dict(self._read_document(path, "container")))
        return result

    def remove_container_tree(self, org_id: str, container_id: str) -> None:
        import shutil

        path = self.container_dir(org_id, container_id)
        if path.exists():
            shutil.rmtree(path)

    def revision_dir(self, container: Container) -> Path:
        return self.container_dir(container.org_id, container.container_id) / "revisions"

    def save_revision(self, container: Container, revision: ConfigRevision) -> None:
        if revision.container_id != container.container_id:
            raise ValidationError("revision container_id does not match container")
        revision.verify()
        path = self.revision_dir(container) / f"{revision.config_version}.json"
        self._write_document_exclusive(path, "config_revision", revision.to_dict())

    def get_revision(
        self,
        container: Container,
        config_version: str,
    ) -> ConfigRevision:
        config_version = validate_id(config_version, field="config_version")
        path = self.revision_dir(container) / f"{config_version}.json"
        revision = ConfigRevision.from_dict(self._read_document(path, "config_revision"))
        if revision.container_id != container.container_id:
            raise CorruptStoreError(f"revision file {path} belongs to another container")
        return revision

    def list_revisions(self, container: Container) -> list[ConfigRevision]:
        result = []
        for path in sorted(self.revision_dir(container).glob("*.json")):
            result.append(ConfigRevision.from_dict(self._read_document(path, "config_revision")))
        result.sort(key=lambda revision: revision.revision_number)
        return result

    def latest_revision(self, container: Container) -> ConfigRevision | None:
        revisions = self.list_revisions(container)
        return revisions[-1] if revisions else None

    def environment_dir(self, container: Container) -> Path:
        return self.container_dir(container.org_id, container.container_id) / "environments"

    def save_environment(self, container: Container, environment: Environment) -> None:
        if environment.container_id != container.container_id:
            raise ValidationError("environment container_id does not match container")
        path = self.environment_dir(container) / f"{environment.environment_id}.json"
        self._write_document(path, "environment", environment.to_dict())

    def get_environment(self, container: Container, environment_id: str) -> Environment:
        environment_id = validate_id(environment_id, field="environment_id")
        path = self.environment_dir(container) / f"{environment_id}.json"
        environment = Environment.from_dict(self._read_document(path, "environment"))
        if environment.container_id != container.container_id:
            raise CorruptStoreError(f"environment file {path} belongs to another container")
        return environment

    def list_environments(self, container: Container) -> list[Environment]:
        result = []
        for path in sorted(self.environment_dir(container).glob("*.json")):
            result.append(Environment.from_dict(self._read_document(path, "environment")))
        return result

    def audit_dir(self, container: Container) -> Path:
        return self.container_dir(container.org_id, container.container_id) / "audit"

    def append_audit_event(self, container: Container, event: AuditEvent) -> AuditEvent:
        if event.container_id != container.container_id:
            raise ValidationError("audit event container_id does not match container")
        existing = self.list_audit_events(container)
        sequence = max((item.sequence for item in existing), default=0) + 1
        stored = replace(event, sequence=sequence)
        path = self.audit_dir(container) / f"{event.event_id}.json"
        self._write_document_exclusive(path, "audit_event", stored.to_dict())
        return stored

    def list_audit_events(self, container: Container) -> list[AuditEvent]:
        result = []
        for path in sorted(self.audit_dir(container).glob("*.json")):
            event = AuditEvent.from_dict(self._read_document(path, "audit_event"))
            if event.container_id != container.container_id:
                raise CorruptStoreError(f"audit file {path} belongs to another container")
            result.append(event)
        result.sort(key=lambda event: (event.sequence, event.created_at, event.event_id))
        return result

    def _read_document(self, path: Path, expected_kind: str) -> Mapping[str, Any]:
        try:
            with path.open("r", encoding="utf-8") as handle:
                raw = json.load(handle)
        except FileNotFoundError:
            raise NotFoundError(f"not found: {path}") from None
        except (OSError, json.JSONDecodeError) as exc:
            raise CorruptStoreError(f"cannot read {path}: {exc}") from exc
        if not isinstance(raw, Mapping):
            raise CorruptStoreError(f"{path} does not contain a JSON object")
        migrated = migrate_document(raw)
        return unwrap_document(migrated, expected_kind=expected_kind)

    def _write_document(self, path: Path, kind: str, data: Mapping[str, Any]) -> None:
        document = wrap_document(kind, data)
        self._atomic_write(path, document)

    def _write_document_exclusive(self, path: Path, kind: str, data: Mapping[str, Any]) -> None:
        document = wrap_document(kind, data)
        path.parent.mkdir(parents=True, exist_ok=True)
        self._chmod(path.parent, 0o700)
        payload = (canonical_json(document) + "\n").encode("utf-8")
        try:
            descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        except FileExistsError:
            raise ConflictError(f"immutable document already exists: {path}") from None
        try:
            with os.fdopen(descriptor, "wb") as handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
        except BaseException:
            try:
                path.unlink()
            except OSError:
                pass
            raise
        _fsync_dir(path.parent)

    def _atomic_write(self, path: Path, document: Mapping[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self._chmod(path.parent, 0o700)
        payload = (canonical_json(document) + "\n").encode("utf-8")
        descriptor, temporary = tempfile.mkstemp(
            prefix=f".{path.name}.",
            suffix=".tmp",
            dir=str(path.parent),
        )
        try:
            if os.name == "posix":
                os.fchmod(descriptor, 0o600)
            with os.fdopen(descriptor, "wb") as handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, path)
            _fsync_dir(path.parent)
        except BaseException:
            try:
                os.unlink(temporary)
            except OSError:
                pass
            raise
