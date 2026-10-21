"""Collection and PyTagShield forwarding primitives."""

from .dedupe import DedupeCache, DedupeStore, SQLiteDedupeStore
from .http import IngestHTTPServer, create_server, make_ssl_context, serve
from .pytagshield import (
    ForwardResult,
    PyTagShieldClient,
    to_pytagshield_event,
    validate_pytagshield_url,
)
from .service import IngestConfig, IngestResult, IngestService

__all__ = [
    "DedupeCache",
    "DedupeStore",
    "ForwardResult",
    "IngestConfig",
    "IngestHTTPServer",
    "IngestResult",
    "IngestService",
    "PyTagShieldClient",
    "SQLiteDedupeStore",
    "create_server",
    "make_ssl_context",
    "serve",
    "to_pytagshield_event",
    "validate_pytagshield_url",
]
