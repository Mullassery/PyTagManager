"""Self-hosted control-plane foundation.

The package deliberately uses only the Python standard library. Discovery,
export, CLI, and real-browser verification behavior are unchanged.
"""

from pytagmanager.control.adapters import (
    Adapter,
    AdapterBuildResult,
    AdapterCapabilities,
    AdapterIssue,
    AdapterRegistry,
    default_adapter_registry,
)
from pytagmanager.control.checksums import canonical_json, checksum, verify_checksum
from pytagmanager.control.conditions import (
    evaluate_condition,
    pattern_matches,
    validate_condition,
)
from pytagmanager.control.config import (
    ConfigPayload,
    Destination,
    Tag,
    Trigger,
    Variable,
)
from pytagmanager.control.diff import ObjectChange, RevisionDiff, diff_revisions
from pytagmanager.control.draft import (
    DraftConversion,
    DraftPayload,
    draft_from_recommendation,
    draft_payload_from_recommendations,
)
from pytagmanager.control.errors import (
    ConflictError,
    ControlError,
    CorruptStoreError,
    NotFoundError,
    SchemaVersionError,
    SecretError,
    ValidationError,
)
from pytagmanager.control.ids import (
    container_storage_key,
    new_id,
    normalize_container_id,
    utc_now,
    validate_container_id,
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
from pytagmanager.control.preview import normalize_event, preview_event
from pytagmanager.control.pytagshield import (
    PytagshieldExport,
    PytagshieldIssue,
    project_to_pytagshield,
    validate_with_pytagshield,
)
from pytagmanager.control.schema import (
    CURRENT_SCHEMA_VERSION,
    migrate_document,
    unwrap_document,
    wrap_document,
)
from pytagmanager.control.secrets import (
    SecretRef,
    parse_secret_ref,
    resolve_secret_ref,
)
from pytagmanager.control.service import (
    ActivationResult,
    ControlPlaneService,
    DraftRevisionResult,
    ImportResult,
    ValidationReport,
)
from pytagmanager.control.store import DEFAULT_HOME_ENV, FileStore, default_home
from pytagmanager.control.validation import (
    ConfigValidationReport,
    ValidationIssue,
    validate_config_payload,
)
from pytagmanager.control.variables import ResolvedVariable, VariableResolver

__all__ = [
    "CURRENT_SCHEMA_VERSION",
    "DEFAULT_HOME_ENV",
    "ActivationResult",
    "Adapter",
    "AdapterBuildResult",
    "AdapterCapabilities",
    "AdapterIssue",
    "AdapterRegistry",
    "AuditEvent",
    "ConfigPayload",
    "ConfigRevision",
    "ConfigValidationReport",
    "ConflictError",
    "Container",
    "ControlError",
    "ControlPlaneService",
    "CorruptStoreError",
    "Destination",
    "DraftConversion",
    "DraftPayload",
    "DraftRevisionResult",
    "Environment",
    "FileStore",
    "ImportResult",
    "NotFoundError",
    "ObjectChange",
    "Organization",
    "PytagshieldExport",
    "PytagshieldIssue",
    "ResolvedVariable",
    "RevisionDiff",
    "SchemaVersionError",
    "SecretError",
    "SecretRef",
    "Tag",
    "Trigger",
    "ValidationError",
    "ValidationIssue",
    "ValidationReport",
    "Variable",
    "VariableResolver",
    "Workspace",
    "canonical_json",
    "checksum",
    "container_storage_key",
    "default_adapter_registry",
    "default_home",
    "diff_revisions",
    "draft_from_recommendation",
    "draft_payload_from_recommendations",
    "evaluate_condition",
    "migrate_document",
    "new_id",
    "normalize_container_id",
    "normalize_event",
    "parse_secret_ref",
    "pattern_matches",
    "preview_event",
    "project_to_pytagshield",
    "resolve_secret_ref",
    "unwrap_document",
    "utc_now",
    "validate_condition",
    "validate_config_payload",
    "validate_container_id",
    "validate_id",
    "validate_with_pytagshield",
    "verify_checksum",
    "wrap_document",
]
