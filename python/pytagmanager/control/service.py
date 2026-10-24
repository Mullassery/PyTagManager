"""Typed service API for the first control-plane foundation slice."""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, replace
from typing import Any

from pytagmanager.control.diff import RevisionDiff, diff_revisions
from pytagmanager.control.draft import draft_payload_from_recommendations
from pytagmanager.control.errors import (
    ConflictError,
    CorruptStoreError,
    NotFoundError,
    ValidationError,
)
from pytagmanager.control.ids import (
    new_id,
    normalize_container_id,
    utc_now,
    validate_container_id,
    validate_id,
    validate_name,
)
from pytagmanager.control.models import (
    AuditEvent,
    ConfigPayload,
    ConfigRevision,
    Container,
    Environment,
    Organization,
    Workspace,
)
from pytagmanager.control.preview import preview_event
from pytagmanager.control.pytagshield import PytagshieldExport, project_to_pytagshield
from pytagmanager.control.schema import (
    CURRENT_SCHEMA_VERSION,
    ensure_supported_schema,
    unwrap_document,
    wrap_document,
)
from pytagmanager.control.store import FileStore
from pytagmanager.control.validation import (
    ConfigValidationReport,
    validate_config_payload,
)

DEFAULT_ORGANIZATION_NAME = "Default organization"
DEFAULT_WORKSPACE_NAME = "Default workspace"


@dataclass(frozen=True)
class ImportResult:
    container: Container
    created: bool
    revision_count: int
    renamed_from: str | None = None


@dataclass(frozen=True)
class DraftRevisionResult:
    revision: ConfigRevision
    warnings: tuple[str, ...]
    tag_count: int
    trigger_count: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "config_version": self.revision.config_version,
            "revision_number": self.revision.revision_number,
            "status": self.revision.status,
            "checksum": self.revision.checksum,
            "warnings": list(self.warnings),
            "tag_count": self.tag_count,
            "trigger_count": self.trigger_count,
        }


@dataclass(frozen=True)
class ActivationResult:
    environment: Environment
    previous_config_version: str | None
    changed: bool
    audit_event: AuditEvent | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "environment": self.environment.to_dict(),
            "previous_config_version": self.previous_config_version,
            "changed": self.changed,
            "audit_event": self.audit_event.to_dict() if self.audit_event else None,
        }


@dataclass(frozen=True)
class ValidationReport:
    container_id: str
    revision_count: int
    latest_config_version: str | None
    latest_checksum: str | None
    payload_objects: int
    schema_version: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "container_id": self.container_id,
            "revision_count": self.revision_count,
            "latest_config_version": self.latest_config_version,
            "latest_checksum": self.latest_checksum,
            "payload_objects": self.payload_objects,
            "schema_version": self.schema_version,
            "valid": True,
        }


class ControlPlaneService:
    def __init__(self, store: FileStore | None = None) -> None:
        self.store = store if store is not None else FileStore()
        self.store.initialize()

    def ensure_default_scope(self) -> tuple[str, str]:
        with self.store.lock():
            return self._ensure_default_scope_locked()

    def _ensure_default_scope_locked(self) -> tuple[str, str]:
        meta = self.store.read_meta()
        org_id = meta["default_org_id"]
        workspace_id = meta["default_workspace_id"]
        if org_id is not None:
            try:
                organization = self.store.get_organization(org_id)
            except NotFoundError as exc:
                raise CorruptStoreError(
                    f"default organization {org_id} is missing from the store"
                ) from exc
            if workspace_id is not None:
                try:
                    workspace = self.store.get_workspace(org_id, workspace_id)
                except NotFoundError as exc:
                    raise CorruptStoreError(
                        f"default workspace {workspace_id} is missing from the store"
                    ) from exc
                return organization.org_id, workspace.workspace_id
            workspaces = self.store.list_workspaces(org_id)
            if workspaces:
                workspace = workspaces[0]
            else:
                workspace = Workspace.create(org_id, DEFAULT_WORKSPACE_NAME)
                self.store.save_workspace(workspace)
            meta["default_workspace_id"] = workspace.workspace_id
            self.store.write_meta(meta)
            return organization.org_id, workspace.workspace_id

        organizations = self.store.list_organizations()
        if organizations:
            organization = organizations[0]
        else:
            organization = Organization.create(DEFAULT_ORGANIZATION_NAME)
            self.store.save_organization(organization)
        workspaces = self.store.list_workspaces(organization.org_id)
        if workspaces:
            workspace = workspaces[0]
        else:
            workspace = Workspace.create(organization.org_id, DEFAULT_WORKSPACE_NAME)
            self.store.save_workspace(workspace)
        meta["default_org_id"] = organization.org_id
        meta["default_workspace_id"] = workspace.workspace_id
        self.store.write_meta(meta)
        return organization.org_id, workspace.workspace_id

    def create_organization(self, name: str, *, created_by: str = "local") -> Organization:
        with self.store.lock():
            organization = Organization.create(name, created_by=created_by)
            self.store.save_organization(organization)
            workspace = Workspace.create(organization.org_id, DEFAULT_WORKSPACE_NAME)
            self.store.save_workspace(workspace)
            meta = self.store.read_meta()
            if meta["default_org_id"] is None:
                meta["default_org_id"] = organization.org_id
                meta["default_workspace_id"] = workspace.workspace_id
                self.store.write_meta(meta)
            return organization

    def list_organizations(self) -> list[Organization]:
        return sorted(self.store.list_organizations(), key=lambda org: org.name.casefold())

    def create_workspace(
        self,
        org_id: str,
        name: str,
        *,
        created_by: str = "local",
    ) -> Workspace:
        with self.store.lock():
            self.store.get_organization(org_id)
            workspace = Workspace.create(org_id, name, created_by=created_by)
            self.store.save_workspace(workspace)
            meta = self.store.read_meta()
            if meta["default_org_id"] == org_id and meta["default_workspace_id"] is None:
                meta["default_workspace_id"] = workspace.workspace_id
                self.store.write_meta(meta)
            return workspace

    def list_workspaces(self, org_id: str) -> list[Workspace]:
        return sorted(
            self.store.list_workspaces(org_id),
            key=lambda workspace: workspace.name.casefold(),
        )

    def _resolve_scope_locked(
        self,
        org_id: str | None,
        workspace_id: str | None,
    ) -> tuple[str, str]:
        meta = self.store.read_meta()
        if org_id is None:
            org_id, default_workspace_id = self._ensure_default_scope_locked()
            if workspace_id is None:
                return org_id, default_workspace_id
        else:
            org_id = validate_id(org_id, field="org_id")
            self.store.get_organization(org_id)
            if workspace_id is None and meta["default_org_id"] == org_id:
                workspace_id = meta["default_workspace_id"]
            if workspace_id is None:
                workspaces = self.store.list_workspaces(org_id)
                if not workspaces:
                    raise NotFoundError(f"organization {org_id} has no workspaces")
                if len(workspaces) > 1:
                    raise ValidationError(
                        "multiple workspaces exist; specify workspace_id explicitly"
                    )
                workspace_id = workspaces[0].workspace_id

        workspace_id = validate_id(workspace_id, field="workspace_id")
        workspace = self.store.get_workspace(org_id, workspace_id)
        return workspace.org_id, workspace.workspace_id

    def create_container(
        self,
        container_id: str,
        *,
        name: str | None = None,
        org_id: str | None = None,
        workspace_id: str | None = None,
        description: str = "",
        site_urls: tuple[str, ...] | list[str] = (),
        external_refs: tuple[dict[str, Any], ...] | list[dict[str, Any]] = (),
        created_by: str = "local",
    ) -> Container:
        validate_container_id(container_id)
        with self.store.lock():
            org_id, workspace_id = self._resolve_scope_locked(org_id, workspace_id)
            self._assert_container_id_available(org_id, container_id)
            container = Container.create(
                container_id=container_id,
                org_id=org_id,
                workspace_id=workspace_id,
                name=name,
                description=description,
                site_urls=site_urls,
                external_refs=external_refs,
                created_by=created_by,
            )
            self.store.save_container(container)
            return container

    def _assert_container_id_available(
        self,
        org_id: str,
        container_id: str,
        *,
        ignore: str | None = None,
    ) -> None:
        normalized = normalize_container_id(container_id)
        ignored = ignore.casefold() if ignore is not None else None
        for existing in self.store.list_containers(org_id):
            if existing.uniqueness_key == normalized and existing.uniqueness_key != ignored:
                raise ConflictError(
                    f"container ID {container_id!r} already exists in organization {org_id}"
                )

    def list_containers(self, *, org_id: str | None = None) -> list[Container]:
        with self.store.lock():
            if org_id is None:
                org_id, _ = self._ensure_default_scope_locked()
            else:
                org_id = validate_id(org_id, field="org_id")
                self.store.get_organization(org_id)
            return sorted(
                self.store.list_containers(org_id),
                key=lambda container: container.container_id.casefold(),
            )

    def _get_container_locked(
        self,
        container_id: str,
        org_id: str | None,
    ) -> Container:
        if org_id is None:
            org_id, _ = self._ensure_default_scope_locked()
        else:
            org_id = validate_id(org_id, field="org_id")
            self.store.get_organization(org_id)
        try:
            return self.store.get_container(org_id, container_id)
        except NotFoundError as exc:
            raise NotFoundError(
                f"container {container_id!r} not found in organization {org_id}"
            ) from exc

    def get_container(
        self,
        container_id: str,
        *,
        org_id: str | None = None,
    ) -> Container:
        with self.store.lock():
            return self._get_container_locked(container_id, org_id)

    def create_revision(
        self,
        container_id: str,
        payload: Mapping[str, Any] | ConfigPayload | None = None,
        *,
        org_id: str | None = None,
        expected_parent: str | None = None,
        created_by: str = "local",
        notes: str = "",
        status: str = "draft",
    ) -> ConfigRevision:
        with self.store.lock():
            container = self._get_container_locked(container_id, org_id)
            revisions = self.store.list_revisions(container)
            latest = revisions[-1] if revisions else None
            latest_version = latest.config_version if latest is not None else None
            if expected_parent is not None:
                validate_id(expected_parent, field="expected_parent")
                if expected_parent != latest_version:
                    raise ConflictError(
                        f"expected parent {expected_parent} but latest revision is {latest_version}"
                    )
            revision = ConfigRevision.create(
                container_id=container.container_id,
                revision_number=(latest.revision_number + 1) if latest is not None else 1,
                parent_config_version=latest_version,
                payload=payload,
                status=status,
                created_by=created_by,
                notes=notes,
            )
            self.store.save_revision(container, revision)
            self.store.append_audit_event(
                container,
                AuditEvent.create(
                    container_id=container.container_id,
                    action="revision.created",
                    actor=created_by,
                    config_version=revision.config_version,
                    previous_config_version=revision.parent_config_version,
                    checksum=revision.checksum,
                    details={
                        "revision_number": revision.revision_number,
                        "status": revision.status,
                    },
                ),
            )
            return revision

    def get_revision(
        self,
        container_id: str,
        config_version: str,
        *,
        org_id: str | None = None,
    ) -> ConfigRevision:
        with self.store.lock():
            container = self._get_container_locked(container_id, org_id)
            try:
                return self.store.get_revision(container, config_version)
            except NotFoundError as exc:
                raise NotFoundError(
                    f"revision {config_version!r} not found for container {container_id!r}"
                ) from exc

    def list_revisions(
        self,
        container_id: str,
        *,
        org_id: str | None = None,
    ) -> list[ConfigRevision]:
        with self.store.lock():
            container = self._get_container_locked(container_id, org_id)
            return self.store.list_revisions(container)

    def create_environment(
        self,
        container_id: str,
        name: str,
        *,
        protected: bool = False,
        org_id: str | None = None,
        created_by: str = "local",
    ) -> Environment:
        with self.store.lock():
            container = self._get_container_locked(container_id, org_id)
            for existing in self.store.list_environments(container):
                if existing.name.casefold() == validate_name(name).casefold():
                    raise ConflictError(
                        f"environment name {name!r} already exists in container "
                        f"{container.container_id!r}"
                    )
            environment = Environment.create(
                org_id=container.org_id,
                container_id=container.container_id,
                name=name,
                protected=protected,
                created_by=created_by,
            )
            self.store.save_environment(container, environment)
            self.store.append_audit_event(
                container,
                AuditEvent.create(
                    container_id=container.container_id,
                    action="environment.created",
                    actor=created_by,
                    environment_id=environment.environment_id,
                    details={
                        "name": environment.name,
                        "protected": environment.protected,
                    },
                ),
            )
            return environment

    def list_environments(
        self,
        container_id: str,
        *,
        org_id: str | None = None,
    ) -> list[Environment]:
        with self.store.lock():
            container = self._get_container_locked(container_id, org_id)
            return self.store.list_environments(container)

    def _load_revision_locked(
        self,
        container_id: str,
        config_version: str | None,
        org_id: str | None,
    ) -> tuple[Container, ConfigRevision]:
        container = self._get_container_locked(container_id, org_id)
        revisions = self.store.list_revisions(container)
        if not revisions:
            raise NotFoundError(f"container {container_id!r} has no configuration revisions")
        if config_version is None:
            return container, revisions[-1]
        config_version = validate_id(config_version, field="config_version")
        try:
            return container, self.store.get_revision(container, config_version)
        except NotFoundError as exc:
            raise NotFoundError(
                f"revision {config_version!r} not found for container {container_id!r}"
            ) from exc

    def validate_config(
        self,
        container_id: str,
        *,
        config_version: str | None = None,
        org_id: str | None = None,
    ) -> ConfigValidationReport:
        with self.store.lock():
            _, revision = self._load_revision_locked(container_id, config_version, org_id)
            return validate_config_payload(revision.payload)

    def preview(
        self,
        container_id: str,
        event: Mapping[str, Any],
        *,
        config_version: str | None = None,
        org_id: str | None = None,
        default_consent: Mapping[str, bool] | None = None,
        consent: Mapping[str, bool] | None = None,
    ) -> dict[str, Any]:
        with self.store.lock():
            container, revision = self._load_revision_locked(container_id, config_version, org_id)
            return preview_event(
                revision.payload,
                event,
                container_id=container.container_id,
                config_version=revision.config_version,
                revision_status=revision.status,
                default_consent=default_consent,
                consent_override=consent,
            )

    def create_draft_from_recommendations(
        self,
        container_id: str,
        recommendations: Iterable[Any],
        *,
        adapter_key: str = "ga4_event",
        destination_ids: Iterable[str] = (),
        consent_purpose: str | None = None,
        org_id: str | None = None,
        expected_parent: str | None = None,
        created_by: str = "local",
        notes: str = "",
    ) -> DraftRevisionResult:
        draft = draft_payload_from_recommendations(
            recommendations,
            adapter_key=adapter_key,
            destination_ids=destination_ids,
            consent_purpose=consent_purpose,
        )
        revision = self.create_revision(
            container_id,
            draft.payload,
            org_id=org_id,
            expected_parent=expected_parent,
            created_by=created_by,
            notes=notes,
            status="draft",
        )
        return DraftRevisionResult(
            revision=revision,
            warnings=draft.warnings,
            tag_count=len(draft.payload.tags),
            trigger_count=len(draft.payload.triggers),
        )

    def diff_revisions(
        self,
        container_id: str,
        *,
        from_version: str | None = None,
        to_version: str | None = None,
        org_id: str | None = None,
    ) -> RevisionDiff:
        with self.store.lock():
            container = self._get_container_locked(container_id, org_id)
            revisions = self.store.list_revisions(container)
            if not revisions:
                raise NotFoundError(f"container {container_id!r} has no configuration revisions")
            if to_version is None:
                revision_to = revisions[-1]
            else:
                revision_to = self.store.get_revision(container, to_version)
            if from_version is None:
                if revision_to.parent_config_version is None:
                    raise ValidationError("revision has no parent; specify --from explicitly")
                revision_from = self.store.get_revision(
                    container, revision_to.parent_config_version
                )
            else:
                revision_from = self.store.get_revision(container, from_version)
            return diff_revisions(revision_from, revision_to)

    def _resolve_environment_locked(
        self,
        container: Container,
        environment_ref: str,
    ) -> Environment:
        try:
            environment_id = validate_id(environment_ref, field="environment_id")
        except ValidationError:
            environment_id = None
        if environment_id is not None:
            try:
                return self.store.get_environment(container, environment_id)
            except NotFoundError:
                pass
        matches = [
            environment
            for environment in self.store.list_environments(container)
            if environment.name.casefold() == environment_ref.casefold()
        ]
        if not matches:
            raise NotFoundError(
                f"environment {environment_ref!r} not found in container {container.container_id!r}"
            )
        if len(matches) > 1:
            raise ConflictError(
                f"environment name {environment_ref!r} is ambiguous in container "
                f"{container.container_id!r}"
            )
        return matches[0]

    def _get_environment_locked(
        self,
        container_id: str,
        environment_ref: str,
        org_id: str | None,
    ) -> tuple[Container, Environment]:
        container = self._get_container_locked(container_id, org_id)
        return container, self._resolve_environment_locked(container, environment_ref)

    def get_environment(
        self,
        container_id: str,
        environment_ref: str,
        *,
        org_id: str | None = None,
    ) -> Environment:
        with self.store.lock():
            _, environment = self._get_environment_locked(container_id, environment_ref, org_id)
            return environment

    def _validated_revision_locked(
        self,
        container: Container,
        config_version: str,
    ) -> tuple[ConfigRevision, ConfigValidationReport]:
        try:
            revision = self.store.get_revision(container, config_version)
        except NotFoundError as exc:
            raise NotFoundError(
                f"revision {config_version!r} not found for container {container.container_id!r}"
            ) from exc
        report = validate_config_payload(revision.payload)
        return revision, report

    def _record_activation_failure(
        self,
        container: Container,
        environment: Environment,
        action: str,
        actor: str,
        reason: str,
        target_version: str | None,
    ) -> None:
        self.store.append_audit_event(
            container,
            AuditEvent.create(
                container_id=container.container_id,
                action=action,
                actor=actor,
                result="failed",
                environment_id=environment.environment_id,
                config_version=target_version,
                previous_config_version=environment.current_config_version,
                details={"reason": reason},
            ),
        )

    def activate_environment(
        self,
        container_id: str,
        environment_ref: str,
        *,
        config_version: str | None = None,
        expected_current: str | None = None,
        allow_protected: bool = False,
        org_id: str | None = None,
        activated_by: str = "local",
    ) -> ActivationResult:
        with self.store.lock():
            container, environment = self._get_environment_locked(
                container_id, environment_ref, org_id
            )
            target_version = config_version
            if target_version is None:
                latest = self.store.latest_revision(container)
                if latest is None:
                    raise NotFoundError(
                        f"container {container.container_id!r} has no configuration revisions"
                    )
                target_version = latest.config_version
            target_version = validate_id(target_version, field="config_version")

            if environment.protected and not allow_protected:
                self._record_activation_failure(
                    container,
                    environment,
                    "environment.activated",
                    activated_by,
                    "protected_environment",
                    target_version,
                )
                raise ValidationError(
                    f"environment {environment.name!r} is protected; "
                    "explicit allow_protected is required"
                )
            if expected_current is not None:
                expected_current = validate_id(expected_current, field="expected_current")
                if expected_current != environment.current_config_version:
                    self._record_activation_failure(
                        container,
                        environment,
                        "environment.activated",
                        activated_by,
                        "stale_environment",
                        target_version,
                    )
                    raise ConflictError(
                        f"expected current {expected_current} but environment is at "
                        f"{environment.current_config_version}"
                    )

            revision, report = self._validated_revision_locked(container, target_version)
            if not report.valid:
                self._record_activation_failure(
                    container,
                    environment,
                    "environment.activated",
                    activated_by,
                    "invalid_revision",
                    target_version,
                )
                messages = "; ".join(issue.message for issue in report.errors)
                raise ValidationError(f"revision {target_version!r} failed validation: {messages}")
            if environment.current_config_version == target_version:
                return ActivationResult(
                    environment=environment,
                    previous_config_version=environment.previous_config_version,
                    changed=False,
                )

            previous_version = environment.current_config_version
            previous_revision = (
                self.store.get_revision(container, previous_version)
                if previous_version is not None
                else None
            )
            updated = replace(
                environment,
                previous_config_version=previous_version,
                current_config_version=target_version,
                updated_at=utc_now(),
                updated_by=activated_by,
            )
            self.store.save_environment(container, updated)
            audit_event = AuditEvent.create(
                container_id=container.container_id,
                action="environment.activated",
                actor=activated_by,
                environment_id=environment.environment_id,
                config_version=target_version,
                previous_config_version=previous_version,
                checksum=revision.checksum,
                previous_checksum=previous_revision.checksum if previous_revision else None,
                details={
                    "environment": environment.name,
                    "protected": environment.protected,
                },
            )
            audit_event = self.store.append_audit_event(container, audit_event)
            return ActivationResult(
                environment=updated,
                previous_config_version=previous_version,
                changed=True,
                audit_event=audit_event,
            )

    def rollback_environment(
        self,
        container_id: str,
        environment_ref: str,
        *,
        expected_current: str | None = None,
        allow_protected: bool = False,
        org_id: str | None = None,
        rolled_back_by: str = "local",
    ) -> ActivationResult:
        with self.store.lock():
            container, environment = self._get_environment_locked(
                container_id, environment_ref, org_id
            )
            target_version = environment.previous_config_version
            if target_version is None:
                self._record_activation_failure(
                    container,
                    environment,
                    "environment.rolled_back",
                    rolled_back_by,
                    "no_previous_revision",
                    None,
                )
                raise ValidationError(
                    f"environment {environment.name!r} has no previous revision to roll back to"
                )
            if environment.protected and not allow_protected:
                self._record_activation_failure(
                    container,
                    environment,
                    "environment.rolled_back",
                    rolled_back_by,
                    "protected_environment",
                    target_version,
                )
                raise ValidationError(
                    f"environment {environment.name!r} is protected; "
                    "explicit allow_protected is required"
                )
            if expected_current is not None:
                expected_current = validate_id(expected_current, field="expected_current")
                if expected_current != environment.current_config_version:
                    self._record_activation_failure(
                        container,
                        environment,
                        "environment.rolled_back",
                        rolled_back_by,
                        "stale_environment",
                        target_version,
                    )
                    raise ConflictError(
                        f"expected current {expected_current} but environment is at "
                        f"{environment.current_config_version}"
                    )

            revision, report = self._validated_revision_locked(container, target_version)
            if not report.valid:
                self._record_activation_failure(
                    container,
                    environment,
                    "environment.rolled_back",
                    rolled_back_by,
                    "invalid_revision",
                    target_version,
                )
                messages = "; ".join(issue.message for issue in report.errors)
                raise ValidationError(f"revision {target_version!r} failed validation: {messages}")
            current_version = environment.current_config_version
            current_revision = (
                self.store.get_revision(container, current_version)
                if current_version is not None
                else None
            )
            updated = replace(
                environment,
                previous_config_version=current_version,
                current_config_version=target_version,
                updated_at=utc_now(),
                updated_by=rolled_back_by,
            )
            self.store.save_environment(container, updated)
            audit_event = AuditEvent.create(
                container_id=container.container_id,
                action="environment.rolled_back",
                actor=rolled_back_by,
                environment_id=environment.environment_id,
                config_version=target_version,
                previous_config_version=current_version,
                checksum=revision.checksum,
                previous_checksum=current_revision.checksum if current_revision else None,
                details={
                    "environment": environment.name,
                    "protected": environment.protected,
                },
            )
            audit_event = self.store.append_audit_event(container, audit_event)
            return ActivationResult(
                environment=updated,
                previous_config_version=current_version,
                changed=True,
                audit_event=audit_event,
            )

    def list_audit_events(
        self,
        container_id: str,
        *,
        limit: int | None = None,
        org_id: str | None = None,
    ) -> list[AuditEvent]:
        if limit is not None and (not isinstance(limit, int) or limit < 1):
            raise ValidationError("limit must be a positive integer")
        with self.store.lock():
            container = self._get_container_locked(container_id, org_id)
            events = self.store.list_audit_events(container)
            events.reverse()
            return events[:limit] if limit is not None else events

    def export_pytagshield(
        self,
        container_id: str,
        *,
        pseudonymize_salt: str,
        config_version: str | None = None,
        default_policy: str = "deny",
        secret_resolver: Callable[[str], str] | None = None,
        org_id: str | None = None,
    ) -> PytagshieldExport:
        with self.store.lock():
            _, revision = self._load_revision_locked(container_id, config_version, org_id)
            return project_to_pytagshield(
                revision.payload,
                pseudonymize_salt=pseudonymize_salt,
                default_policy=default_policy,
                secret_resolver=secret_resolver,
            )

    def validate_container(
        self,
        container_id: str,
        *,
        org_id: str | None = None,
    ) -> ValidationReport:
        with self.store.lock():
            container = self._get_container_locked(container_id, org_id)
            revisions = self.store.list_revisions(container)
            latest = revisions[-1] if revisions else None
            for revision in revisions:
                revision.verify()
                ensure_supported_schema(revision.schema_version)
            return ValidationReport(
                container_id=container.container_id,
                revision_count=len(revisions),
                latest_config_version=(latest.config_version if latest is not None else None),
                latest_checksum=latest.checksum if latest is not None else None,
                payload_objects=latest.payload.object_count() if latest is not None else 0,
                schema_version=CURRENT_SCHEMA_VERSION,
            )

    def export_container(
        self,
        container_id: str,
        *,
        org_id: str | None = None,
        include_environments: bool = True,
    ) -> dict[str, Any]:
        with self.store.lock():
            container = self._get_container_locked(container_id, org_id)
            revisions = self.store.list_revisions(container)
            environments = self.store.list_environments(container) if include_environments else []
            return wrap_document(
                "container_export",
                {
                    "container": container.to_dict(),
                    "revisions": [revision.to_dict() for revision in revisions],
                    "environments": [environment.to_dict() for environment in environments],
                },
            )

    def clone_container(
        self,
        source_container_id: str,
        new_container_id: str,
        *,
        name: str | None = None,
        org_id: str | None = None,
        workspace_id: str | None = None,
        created_by: str = "local",
    ) -> ImportResult:
        document = self.export_container(source_container_id, org_id=org_id)
        return self.import_container(
            document,
            as_container_id=new_container_id,
            name=name,
            org_id=org_id,
            workspace_id=workspace_id,
            created_by=created_by,
        )

    def import_container(
        self,
        document: Mapping[str, Any],
        *,
        as_container_id: str | None = None,
        name: str | None = None,
        org_id: str | None = None,
        workspace_id: str | None = None,
        created_by: str = "local",
    ) -> ImportResult:
        data = unwrap_document(document, expected_kind="container_export")
        expected = {"container", "revisions", "environments"}
        unknown = sorted(set(data) - expected)
        missing = sorted({"container", "revisions"} - set(data))
        if unknown:
            raise ValidationError(
                f"container export contains unknown field(s): {', '.join(unknown)}"
            )
        if missing:
            raise ValidationError(f"container export is missing field(s): {', '.join(missing)}")
        source_container = Container.from_dict(data["container"])
        if as_container_id is not None:
            validate_container_id(as_container_id)
        revisions = self._parse_export_revisions(data["revisions"], source_container)
        environments = self._parse_export_environments(
            data.get("environments", []),
            source_container,
            revisions,
        )

        with self.store.lock():
            target_org_id, target_workspace_id = self._resolve_scope_locked(org_id, workspace_id)
            target_id = as_container_id or source_container.container_id
            if self.store.container_exists(target_org_id, target_id):
                if as_container_id is not None:
                    raise ConflictError(
                        f"container ID {target_id!r} already exists in organization {target_org_id}"
                    )
                existing = self.store.get_container(target_org_id, target_id)
                existing_revisions = self.store.list_revisions(existing)
                if self._revision_fingerprints(existing_revisions) != self._revision_fingerprints(
                    revisions
                ):
                    raise ConflictError(
                        f"container {target_id!r} already exists with different revisions"
                    )
                return ImportResult(
                    container=existing,
                    created=False,
                    revision_count=len(existing_revisions),
                )

            self._assert_container_id_available(target_org_id, target_id)
            if as_container_id is None:
                target_container = replace(
                    source_container,
                    org_id=target_org_id,
                    workspace_id=target_workspace_id,
                    name=validate_name(name) if name is not None else source_container.name,
                )
                target_revisions = revisions
                target_environments = [
                    replace(
                        environment,
                        org_id=target_org_id,
                        container_id=target_container.container_id,
                    )
                    for environment in environments
                ]
            else:
                target_container = replace(
                    source_container,
                    container_id=as_container_id,
                    org_id=target_org_id,
                    workspace_id=target_workspace_id,
                    name=(
                        validate_name(name)
                        if name is not None
                        else f"{source_container.name} (imported)"
                    ),
                    created_at=utc_now(),
                    created_by=created_by,
                    external_refs=(),
                )
                target_revisions, version_map = self._remap_revisions(
                    revisions,
                    target_container.container_id,
                    created_by=created_by,
                )
                target_environments = self._remap_environments(
                    environments,
                    target_container,
                    version_map,
                )

            try:
                self.store.save_container(target_container)
                for revision in target_revisions:
                    self.store.save_revision(target_container, revision)
                for environment in target_environments:
                    self.store.save_environment(target_container, environment)
            except BaseException:
                self.store.remove_container_tree(
                    target_container.org_id,
                    target_container.container_id,
                )
                raise

            return ImportResult(
                container=target_container,
                created=True,
                revision_count=len(target_revisions),
                renamed_from=(
                    source_container.container_id
                    if as_container_id is not None
                    and as_container_id.casefold() != source_container.container_id.casefold()
                    else None
                ),
            )

    @staticmethod
    def _parse_export_revisions(
        raw_revisions: Any,
        source_container: Container,
    ) -> list[ConfigRevision]:
        if not isinstance(raw_revisions, (list, tuple)):
            raise ValidationError("container export revisions must be a list")
        revisions = []
        seen_versions = set()
        seen_numbers = set()
        for index, raw in enumerate(raw_revisions):
            revision = ConfigRevision.from_dict(raw)
            ensure_supported_schema(revision.schema_version)
            if revision.container_id != source_container.container_id:
                raise ValidationError(
                    f"revisions[{index}] belongs to {revision.container_id!r}, "
                    f"not {source_container.container_id!r}"
                )
            if revision.config_version in seen_versions:
                raise ValidationError(
                    f"container export contains duplicate config_version "
                    f"{revision.config_version!r}"
                )
            if revision.revision_number in seen_numbers:
                raise ValidationError(
                    f"container export contains duplicate revision_number "
                    f"{revision.revision_number!r}"
                )
            seen_versions.add(revision.config_version)
            seen_numbers.add(revision.revision_number)
            revisions.append(revision)
        revisions.sort(key=lambda item: item.revision_number)
        parent_references = {revision.parent_config_version for revision in revisions}
        parent_references.discard(None)
        missing_parents = parent_references - seen_versions
        if missing_parents:
            raise ValidationError(
                "container export references missing parent revision(s): "
                + ", ".join(sorted(missing_parents))
            )
        return revisions

    @staticmethod
    def _parse_export_environments(
        raw_environments: Any,
        source_container: Container,
        revisions: list[ConfigRevision],
    ) -> list[Environment]:
        if not isinstance(raw_environments, (list, tuple)):
            raise ValidationError("container export environments must be a list")
        versions = {revision.config_version for revision in revisions}
        environments = []
        seen_names = set()
        for index, raw in enumerate(raw_environments):
            environment = Environment.from_dict(raw)
            if environment.container_id != source_container.container_id:
                raise ValidationError(
                    f"environments[{index}] belongs to {environment.container_id!r}, "
                    f"not {source_container.container_id!r}"
                )
            if environment.name.casefold() in seen_names:
                raise ValidationError(
                    f"container export contains duplicate environment name {environment.name!r}"
                )
            for field, referenced in (
                ("current_config_version", environment.current_config_version),
                ("previous_config_version", environment.previous_config_version),
            ):
                if referenced is not None and referenced not in versions:
                    raise ValidationError(
                        f"environments[{index}] references missing config version "
                        f"{referenced!r} in {field}"
                    )
            seen_names.add(environment.name.casefold())
            environments.append(environment)
        return environments

    @staticmethod
    def _revision_fingerprints(
        revisions: list[ConfigRevision],
    ) -> list[tuple[int, str]]:
        return [
            (revision.revision_number, revision.checksum)
            for revision in sorted(revisions, key=lambda item: item.revision_number)
        ]

    @staticmethod
    def _remap_revisions(
        revisions: list[ConfigRevision],
        target_container_id: str,
        *,
        created_by: str,
    ) -> tuple[list[ConfigRevision], dict[str, str]]:
        version_map: dict[str, str] = {}
        remapped = []
        for revision in revisions:
            new_parent = None
            if revision.parent_config_version is not None:
                if revision.parent_config_version not in version_map:
                    raise ValidationError(
                        "revision parent must appear before its child: "
                        f"{revision.parent_config_version!r}"
                    )
                new_parent = version_map[revision.parent_config_version]
            new_revision = ConfigRevision.create(
                container_id=target_container_id,
                revision_number=revision.revision_number,
                parent_config_version=new_parent,
                payload=revision.payload,
                status="draft",
                created_by=created_by,
                notes=revision.notes,
            )
            version_map[revision.config_version] = new_revision.config_version
            remapped.append(new_revision)
        return remapped, version_map

    @staticmethod
    def _remap_environments(
        environments: list[Environment],
        target_container: Container,
        version_map: Mapping[str, str],
    ) -> list[Environment]:
        remapped = []
        for environment in environments:
            new_current = (
                version_map[environment.current_config_version]
                if environment.current_config_version is not None
                else None
            )
            new_previous = (
                version_map[environment.previous_config_version]
                if environment.previous_config_version is not None
                else None
            )
            remapped.append(
                Environment(
                    environment_id=new_id(),
                    org_id=target_container.org_id,
                    container_id=target_container.container_id,
                    name=environment.name,
                    protected=environment.protected,
                    current_config_version=new_current,
                    created_at=utc_now(),
                    created_by=environment.created_by,
                    previous_config_version=new_previous,
                    updated_at=utc_now(),
                    updated_by=environment.updated_by or environment.created_by,
                )
            )
        return remapped
