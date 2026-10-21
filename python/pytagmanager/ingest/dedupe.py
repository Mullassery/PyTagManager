"""Idempotency stores for collection retries and duplicate suppression."""

from __future__ import annotations

import os
import sqlite3
import threading
import time
from pathlib import Path
from typing import Callable, Protocol


class DedupeStore(Protocol):
    backend: str

    def claim(self, event_id: str, *, now: float | None = None) -> str: ...

    def complete(self, event_id: str, *, now: float | None = None) -> None: ...

    def release(self, event_id: str) -> None: ...

    def close(self) -> None: ...


class DedupeCache:
    """In-process, retry-aware event-id claims.

    A claim is released after a transient forwarding failure so a retry can
    make progress. Permanent outcomes are remembered until the TTL expires.
    This is not durable across restarts; use ``SQLiteDedupeStore`` when
    durability or cross-process dedupe is required.
    """

    backend = "memory"

    def __init__(self, ttl_seconds: int, capacity: int) -> None:
        self.ttl_seconds = ttl_seconds
        self.capacity = capacity
        self._completed: dict[str, float] = {}
        self._inflight: set[str] = set()
        self._lock = threading.Lock()

    def claim(self, event_id: str, *, now: float | None = None) -> str:
        current = time.monotonic() if now is None else now
        with self._lock:
            self._purge(current)
            if event_id in self._completed:
                return "completed"
            if event_id in self._inflight:
                return "inflight"
            self._inflight.add(event_id)
            return "claimed"

    def complete(self, event_id: str, *, now: float | None = None) -> None:
        current = time.monotonic() if now is None else now
        with self._lock:
            self._inflight.discard(event_id)
            self._completed[event_id] = current + self.ttl_seconds
            if len(self._completed) > self.capacity:
                oldest = min(self._completed, key=self._completed.get)
                self._completed.pop(oldest, None)

    def release(self, event_id: str) -> None:
        with self._lock:
            self._inflight.discard(event_id)

    def close(self) -> None:
        return None

    def _purge(self, now: float) -> None:
        expired = [key for key, expiry in self._completed.items() if expiry <= now]
        for key in expired:
            self._completed.pop(key, None)


class SQLiteDedupeStore:
    """Durable, cross-process event-id claims backed by SQLite.

    The store records only event ids, state and expiry timestamps. It never
    stores event properties or consent data. WAL mode and ``BEGIN IMMEDIATE``
    make claims serializable across processes on one host; the store is not a
    distributed lock and should not live on an unsupported network filesystem.
    """

    backend = "sqlite"

    def __init__(
        self,
        path: str | os.PathLike[str],
        ttl_seconds: int,
        capacity: int,
        *,
        claim_ttl_seconds: int = 60,
        clock: Callable[[], float] = time.time,
    ) -> None:
        if ttl_seconds < 1:
            raise ValueError("dedupe TTL must be positive")
        if capacity < 1:
            raise ValueError("dedupe capacity must be positive")
        if claim_ttl_seconds < 1:
            raise ValueError("dedupe claim TTL must be positive")
        raw_path = str(path)
        if raw_path == ":memory:":
            raise ValueError("durable dedupe requires a file-backed SQLite path")
        self.path = Path(raw_path)
        if self.path.exists() and self.path.is_dir():
            raise ValueError("dedupe database path must be a file, not a directory")
        self.ttl_seconds = ttl_seconds
        self.capacity = capacity
        self.claim_ttl_seconds = claim_ttl_seconds
        self._clock = clock
        self._local = threading.local()
        self._closed = False
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()
        self._secure_files()

    def _connection(self) -> sqlite3.Connection:
        if self._closed:
            raise RuntimeError("dedupe store is closed")
        connection = getattr(self._local, "connection", None)
        if connection is None:
            connection = sqlite3.connect(
                str(self.path), timeout=5.0, isolation_level=None
            )
            connection.execute("PRAGMA busy_timeout = 5000")
            connection.execute("PRAGMA synchronous = NORMAL")
            self._local.connection = connection
        return connection

    def _initialize(self) -> None:
        connection = self._connection()
        connection.execute("PRAGMA journal_mode = WAL")
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS event_dedupe (
                event_id TEXT PRIMARY KEY,
                state TEXT NOT NULL CHECK (state IN ('inflight', 'completed')),
                expires_at REAL NOT NULL,
                updated_at REAL NOT NULL
            )
            """
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS event_dedupe_expiry "
            "ON event_dedupe (state, expires_at)"
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS event_dedupe_updated "
            "ON event_dedupe (state, updated_at)"
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS event_dedupe_expires_only "
            "ON event_dedupe (expires_at)"
        )

    def claim(self, event_id: str, *, now: float | None = None) -> str:
        current = self._clock() if now is None else now
        connection = self._connection()
        connection.execute("BEGIN IMMEDIATE")
        try:
            self._purge(connection, current)
            row = connection.execute(
                "SELECT state FROM event_dedupe WHERE event_id = ?", (event_id,)
            ).fetchone()
            if row is not None:
                connection.execute("COMMIT")
                self._secure_files()
                return "completed" if row[0] == "completed" else "inflight"
            connection.execute(
                "INSERT INTO event_dedupe (event_id, state, expires_at, updated_at) "
                "VALUES (?, 'inflight', ?, ?)",
                (event_id, current + self.claim_ttl_seconds, current),
            )
            connection.execute("COMMIT")
            self._secure_files()
            return "claimed"
        except Exception:
            connection.execute("ROLLBACK")
            raise

    def complete(self, event_id: str, *, now: float | None = None) -> None:
        current = self._clock() if now is None else now
        connection = self._connection()
        connection.execute("BEGIN IMMEDIATE")
        try:
            self._purge(connection, current)
            connection.execute(
                """
                INSERT INTO event_dedupe (event_id, state, expires_at, updated_at)
                VALUES (?, 'completed', ?, ?)
                ON CONFLICT(event_id) DO UPDATE SET
                    state = 'completed',
                    expires_at = excluded.expires_at,
                    updated_at = excluded.updated_at
                """,
                (event_id, current + self.ttl_seconds, current),
            )
            self._prune_capacity(connection)
            connection.execute("COMMIT")
            self._secure_files()
        except Exception:
            connection.execute("ROLLBACK")
            raise

    def release(self, event_id: str) -> None:
        connection = self._connection()
        connection.execute(
            "DELETE FROM event_dedupe WHERE event_id = ? AND state = 'inflight'",
            (event_id,),
        )
        self._secure_files()

    def count(self, state: str | None = None) -> int:
        connection = self._connection()
        if state is None:
            row = connection.execute("SELECT COUNT(*) FROM event_dedupe").fetchone()
        else:
            row = connection.execute(
                "SELECT COUNT(*) FROM event_dedupe WHERE state = ?", (state,)
            ).fetchone()
        return int(row[0]) if row else 0

    def close(self) -> None:
        connection = getattr(self._local, "connection", None)
        if connection is not None:
            connection.close()
            self._local.connection = None
        self._closed = True

    def _secure_files(self) -> None:
        for path in (
            self.path,
            Path(str(self.path) + "-wal"),
            Path(str(self.path) + "-shm"),
        ):
            try:
                os.chmod(path, 0o600)
            except OSError:
                pass

    def _purge(self, connection: sqlite3.Connection, now: float) -> None:
        connection.execute("DELETE FROM event_dedupe WHERE expires_at <= ?", (now,))

    def _prune_capacity(self, connection: sqlite3.Connection) -> None:
        row = connection.execute(
            "SELECT COUNT(*) FROM event_dedupe WHERE state = 'completed'"
        ).fetchone()
        count = int(row[0]) if row else 0
        excess = count - self.capacity
        if excess <= 0:
            return
        connection.execute(
            """
            DELETE FROM event_dedupe
            WHERE event_id IN (
                SELECT event_id FROM event_dedupe
                WHERE state = 'completed'
                ORDER BY updated_at ASC
                LIMIT ?
            )
            """,
            (excess,),
        )
