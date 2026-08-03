"""Title: Hot store

Append-only hot store for sealed ActionRecords.

Author: Eric Blaudez

Copyright (c) 2026 Thales
Licensed under the MIT License.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any, Protocol
from urllib.parse import urlparse

from thot.action.models import ActionRecord


class HotStore(Protocol):
    """Query and append interface for the audit hot tier.

    Example:
        >>> from thot.audit.hot_store import HotStore, SqliteHotStore
        >>> issubclass(SqliteHotStore, object) and hasattr(SqliteHotStore, "append")
        True
    """

    def append(self, record: ActionRecord) -> ActionRecord:
        """Persist one sealed record; return stored copy.

        Example:
            >>> import tempfile
            >>> from pathlib import Path
            >>> from thot.action.models import ActionRecord
            >>> from thot.audit.hot_store import SqliteHotStore
            >>> with tempfile.TemporaryDirectory() as td:
            ...     store = SqliteHotStore(Path(td) / "hot.db")
            ...     r = store.append(ActionRecord(correlation_id="a" * 32))
            ...     store.close()
            ...     r.evidence.record_hash != ""
            True
        """

    @property
    def prev_hash(self) -> str:
        """Latest ``record_hash`` in the chain.

        Example:
            >>> import tempfile
            >>> from pathlib import Path
            >>> from thot.action.models import ActionRecord
            >>> from thot.audit.hot_store import SqliteHotStore
            >>> with tempfile.TemporaryDirectory() as td:
            ...     store = SqliteHotStore(Path(td) / "hot.db")
            ...     _ = store.append(ActionRecord(correlation_id="b" * 32))
            ...     h = store.prev_hash
            ...     store.close()
            ...     len(h) > 0
            True
        """

    def get_by_correlation(self, correlation_id: str) -> list[ActionRecord]:
        """Return records for a correlation id ordered by id.

        Example:
            >>> import tempfile
            >>> from pathlib import Path
            >>> from thot.action.models import ActionRecord
            >>> from thot.audit.hot_store import SqliteHotStore
            >>> cid = "c" * 32
            >>> with tempfile.TemporaryDirectory() as td:
            ...     store = SqliteHotStore(Path(td) / "hot.db")
            ...     _ = store.append(ActionRecord(correlation_id=cid))
            ...     n = len(store.get_by_correlation(cid))
            ...     store.close()
            ...     n
            1
        """

    def query(
        self,
        *,
        correlation_id: str | None = None,
        actor_id: str | None = None,
        occurred_from: str | None = None,
        occurred_to: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[ActionRecord]:
        """Paginated search.

        Example:
            >>> import tempfile
            >>> from pathlib import Path
            >>> from thot.action.models import ActionRecord
            >>> from thot.audit.hot_store import SqliteHotStore
            >>> with tempfile.TemporaryDirectory() as td:
            ...     store = SqliteHotStore(Path(td) / "hot.db")
            ...     _ = store.append(ActionRecord(correlation_id="d" * 32))
            ...     n = len(store.query(limit=10))
            ...     store.close()
            ...     n
            1
        """

    def iter_all(self) -> list[ActionRecord]:
        """Return all records in chain order (verification).

        Example:
            >>> import tempfile
            >>> from pathlib import Path
            >>> from thot.action.models import ActionRecord
            >>> from thot.audit.hot_store import SqliteHotStore
            >>> with tempfile.TemporaryDirectory() as td:
            ...     store = SqliteHotStore(Path(td) / "hot.db")
            ...     _ = store.append(ActionRecord(correlation_id="e" * 32))
            ...     n = len(store.iter_all())
            ...     store.close()
            ...     n
            1
        """

    def count(self) -> int:
        """Total stored records.

        Example:
            >>> import tempfile
            >>> from pathlib import Path
            >>> from thot.audit.hot_store import SqliteHotStore
            >>> with tempfile.TemporaryDirectory() as td:
            ...     store = SqliteHotStore(Path(td) / "hot.db")
            ...     n = store.count()
            ...     store.close()
            ...     n
            0
        """

    def unarchived(self, *, limit: int = 1000) -> list[ActionRecord]:
        """Records not yet assigned a WORM segment.

        Example:
            >>> import tempfile
            >>> from pathlib import Path
            >>> from thot.action.models import ActionRecord
            >>> from thot.audit.hot_store import SqliteHotStore
            >>> with tempfile.TemporaryDirectory() as td:
            ...     store = SqliteHotStore(Path(td) / "hot.db")
            ...     _ = store.append(ActionRecord(correlation_id="f" * 32))
            ...     n = len(store.unarchived())
            ...     store.close()
            ...     n
            1
        """

    def mark_archived(
        self,
        action_ids: list[str],
        *,
        worm_segment: str,
        archived_at: str,
    ) -> None:
        """Stamp WORM segment refs on exported records.

        Example:
            >>> import tempfile
            >>> from pathlib import Path
            >>> from thot.action.models import ActionRecord
            >>> from thot.audit.hot_store import SqliteHotStore
            >>> with tempfile.TemporaryDirectory() as td:
            ...     store = SqliteHotStore(Path(td) / "hot.db")
            ...     r = store.append(ActionRecord(correlation_id="g" * 32))
            ...     store.mark_archived(
            ...         [r.action_id], worm_segment="worm://s1",
            ...         archived_at="2026-01-01T00:00:00Z",
            ...     )
            ...     n = len(store.unarchived())
            ...     store.close()
            ...     n
            0
        """

    def close(self) -> None:
        """Release connections.

        Example:
            >>> import tempfile
            >>> from pathlib import Path
            >>> from thot.audit.hot_store import SqliteHotStore
            >>> with tempfile.TemporaryDirectory() as td:
            ...     store = SqliteHotStore(Path(td) / "hot.db")
            ...     store.close()
            ...     True
            True
        """


_SCHEMA = """
CREATE TABLE IF NOT EXISTS action_records (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    action_id TEXT NOT NULL UNIQUE,
    correlation_id TEXT NOT NULL,
    occurred_at TEXT NOT NULL,
    actor_id TEXT NOT NULL,
    actor_type TEXT NOT NULL,
    intent TEXT NOT NULL,
    record_json TEXT NOT NULL,
    prev_hash TEXT NOT NULL,
    record_hash TEXT NOT NULL UNIQUE
);
CREATE TABLE IF NOT EXISTS archive_refs (
    action_id TEXT PRIMARY KEY,
    worm_segment TEXT NOT NULL,
    archived_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_action_correlation
    ON action_records(correlation_id);
CREATE INDEX IF NOT EXISTS idx_action_actor_time
    ON action_records(actor_id, occurred_at);
CREATE INDEX IF NOT EXISTS idx_action_occurred
    ON action_records(occurred_at);
"""

_POSTGRES_SCHEMA = """
CREATE TABLE IF NOT EXISTS action_records (
    id SERIAL PRIMARY KEY,
    action_id TEXT NOT NULL UNIQUE,
    correlation_id TEXT NOT NULL,
    occurred_at TEXT NOT NULL,
    actor_id TEXT NOT NULL,
    actor_type TEXT NOT NULL,
    intent TEXT NOT NULL,
    record_json TEXT NOT NULL,
    prev_hash TEXT NOT NULL,
    record_hash TEXT NOT NULL UNIQUE
);
CREATE TABLE IF NOT EXISTS archive_refs (
    action_id TEXT PRIMARY KEY,
    worm_segment TEXT NOT NULL,
    archived_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_action_correlation
    ON action_records(correlation_id);
CREATE INDEX IF NOT EXISTS idx_action_actor_time
    ON action_records(actor_id, occurred_at);
CREATE INDEX IF NOT EXISTS idx_action_occurred
    ON action_records(occurred_at);
"""


def _record_from_json(payload: str) -> ActionRecord:
    """Parse one stored JSON row into an ActionRecord.

    Example:
        >>> from thot.action.models import ActionRecord
        >>> from thot.audit.hot_store import _record_from_json
        >>> r = ActionRecord(correlation_id="h" * 32).seal("")
        >>> parsed = _record_from_json(
        ...     r.model_dump_json(by_alias=True)
        ... )
        >>> parsed.correlation_id == r.correlation_id
        True
    """
    return ActionRecord.model_validate(json.loads(payload))


class SqliteHotStore:
    """SQLite-backed append-only hot store (dev, tests, compose).

    Example:
        >>> import tempfile
        >>> from pathlib import Path
        >>> from thot.audit.hot_store import SqliteHotStore
        >>> with tempfile.TemporaryDirectory() as td:
        ...     store = SqliteHotStore(Path(td) / "hot.db")
        ...     store.count()
        0
    """

    def __init__(self, path: Path) -> None:
        """Open or create the SQLite hot store at ``path``.

        Example:
            >>> import tempfile
            >>> from pathlib import Path
            >>> from thot.audit.hot_store import SqliteHotStore
            >>> with tempfile.TemporaryDirectory() as td:
            ...     p = Path(td) / "hot.db"
            ...     store = SqliteHotStore(p)
            ...     p.is_file()
            True
        """
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(_SCHEMA)
        self._conn.commit()
        self._prev_hash = self._load_head()

    def _load_head(self) -> str:
        """Return the latest record hash (empty when store is new).

        Example:
            >>> import tempfile
            >>> from pathlib import Path
            >>> from thot.audit.hot_store import SqliteHotStore
            >>> with tempfile.TemporaryDirectory() as td:
            ...     store = SqliteHotStore(Path(td) / "hot.db")
            ...     store._load_head()
            ''
        """
        row = self._conn.execute(
            "SELECT record_hash FROM action_records ORDER BY id DESC LIMIT 1"
        ).fetchone()
        return row["record_hash"] if row else ""

    def append(self, record: ActionRecord) -> ActionRecord:
        """Seal and append one ActionRecord.

        Example:
            >>> import tempfile
            >>> from pathlib import Path
            >>> from thot.action.models import ActionRecord
            >>> from thot.audit.hot_store import SqliteHotStore
            >>> with tempfile.TemporaryDirectory() as td:
            ...     store = SqliteHotStore(Path(td) / "hot.db")
            ...     r = store.append(ActionRecord(correlation_id="i" * 32))
            ...     store.close()
            ...     store = SqliteHotStore(Path(td) / "hot.db")
            ...     n = store.count()
            ...     store.close()
            ...     n
            1
        """
        sealed = record.seal(self._prev_hash)
        payload = json.dumps(
            sealed.model_dump(by_alias=True, mode="json"),
            ensure_ascii=False,
        )
        self._conn.execute(
            """
            INSERT INTO action_records (
                action_id, correlation_id, occurred_at,
                actor_id, actor_type, intent,
                record_json, prev_hash, record_hash
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                sealed.action_id,
                sealed.correlation_id,
                sealed.occurred_at,
                sealed.actor.id,
                sealed.actor.type,
                sealed.intent.declared,
                payload,
                sealed.evidence.prev_hash,
                sealed.evidence.record_hash,
            ),
        )
        self._conn.commit()
        self._prev_hash = sealed.evidence.record_hash
        return sealed

    @property
    def prev_hash(self) -> str:
        """Latest sealed record hash in this store.

        Example:
            >>> import tempfile
            >>> from pathlib import Path
            >>> from thot.action.models import ActionRecord
            >>> from thot.audit.hot_store import SqliteHotStore
            >>> with tempfile.TemporaryDirectory() as td:
            ...     store = SqliteHotStore(Path(td) / "hot.db")
            ...     _ = store.append(ActionRecord(correlation_id="j" * 32))
            ...     len(store.prev_hash) > 0
            True
        """
        return self._prev_hash

    def get_by_correlation(self, correlation_id: str) -> list[ActionRecord]:
        """Fetch records sharing one correlation id.

        Example:
            >>> import tempfile
            >>> from pathlib import Path
            >>> from thot.action.models import ActionRecord
            >>> from thot.audit.hot_store import SqliteHotStore
            >>> cid = "k" * 32
            >>> with tempfile.TemporaryDirectory() as td:
            ...     store = SqliteHotStore(Path(td) / "hot.db")
            ...     _ = store.append(ActionRecord(correlation_id=cid))
            ...     len(store.get_by_correlation(cid))
            1
        """
        rows = self._conn.execute(
            "SELECT record_json FROM action_records "
            "WHERE correlation_id = ? ORDER BY id",
            (correlation_id,),
        ).fetchall()
        return [_record_from_json(row["record_json"]) for row in rows]

    def query(
        self,
        *,
        correlation_id: str | None = None,
        actor_id: str | None = None,
        occurred_from: str | None = None,
        occurred_to: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[ActionRecord]:
        """Search records with optional filters.

        Example:
            >>> import tempfile
            >>> from pathlib import Path
            >>> from thot.action.models import ActionRecord
            >>> from thot.audit.hot_store import SqliteHotStore
            >>> with tempfile.TemporaryDirectory() as td:
            ...     store = SqliteHotStore(Path(td) / "hot.db")
            ...     _ = store.append(ActionRecord(correlation_id="l" * 32))
            ...     len(store.query(actor_id="anonymous"))
            1
        """
        clauses: list[str] = []
        params: list[Any] = []
        if correlation_id:
            clauses.append("correlation_id = ?")
            params.append(correlation_id)
        if actor_id:
            clauses.append("actor_id = ?")
            params.append(actor_id)
        if occurred_from:
            clauses.append("occurred_at >= ?")
            params.append(occurred_from)
        if occurred_to:
            clauses.append("occurred_at <= ?")
            params.append(occurred_to)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        params.extend([limit, offset])
        rows = self._conn.execute(
            f"SELECT record_json FROM action_records {where} "
            "ORDER BY id LIMIT ? OFFSET ?",
            params,
        ).fetchall()
        return [_record_from_json(row["record_json"]) for row in rows]

    def iter_all(self) -> list[ActionRecord]:
        """Return all records in insertion order.

        Example:
            >>> import tempfile
            >>> from pathlib import Path
            >>> from thot.action.models import ActionRecord
            >>> from thot.audit.hot_store import SqliteHotStore
            >>> with tempfile.TemporaryDirectory() as td:
            ...     store = SqliteHotStore(Path(td) / "hot.db")
            ...     _ = store.append(ActionRecord(correlation_id="m" * 32))
            ...     len(store.iter_all())
            1
        """
        rows = self._conn.execute(
            "SELECT record_json FROM action_records ORDER BY id"
        ).fetchall()
        return [_record_from_json(row["record_json"]) for row in rows]

    def count(self) -> int:
        """Return total record count.

        Example:
            >>> import tempfile
            >>> from pathlib import Path
            >>> from thot.audit.hot_store import SqliteHotStore
            >>> with tempfile.TemporaryDirectory() as td:
            ...     store = SqliteHotStore(Path(td) / "hot.db")
            ...     store.count()
            0
        """
        row = self._conn.execute(
            "SELECT COUNT(*) AS c FROM action_records"
        ).fetchone()
        return int(row["c"]) if row else 0

    def unarchived(self, *, limit: int = 1000) -> list[ActionRecord]:
        """List records without a WORM archive reference.

        Example:
            >>> import tempfile
            >>> from pathlib import Path
            >>> from thot.action.models import ActionRecord
            >>> from thot.audit.hot_store import SqliteHotStore
            >>> with tempfile.TemporaryDirectory() as td:
            ...     store = SqliteHotStore(Path(td) / "hot.db")
            ...     _ = store.append(ActionRecord(correlation_id="n" * 32))
            ...     len(store.unarchived())
            1
        """
        rows = self._conn.execute(
            """
            SELECT r.record_json FROM action_records r
            LEFT JOIN archive_refs a ON a.action_id = r.action_id
            WHERE a.action_id IS NULL
            ORDER BY r.id LIMIT ?
            """,
            (limit,),
        ).fetchall()
        return [_record_from_json(row["record_json"]) for row in rows]

    def mark_archived(
        self,
        action_ids: list[str],
        *,
        worm_segment: str,
        archived_at: str,
    ) -> None:
        """Record WORM segment assignment for exported action ids.

        Example:
            >>> import tempfile
            >>> from pathlib import Path
            >>> from thot.action.models import ActionRecord
            >>> from thot.audit.hot_store import SqliteHotStore
            >>> with tempfile.TemporaryDirectory() as td:
            ...     store = SqliteHotStore(Path(td) / "hot.db")
            ...     r = store.append(ActionRecord(correlation_id="o" * 32))
            ...     store.mark_archived(
            ...         [r.action_id], worm_segment="worm://x",
            ...         archived_at="2026-01-01T00:00:00Z",
            ...     )
            ...     len(store.unarchived())
            0
        """
        if not action_ids:
            return
        self._conn.executemany(
            "INSERT OR IGNORE INTO archive_refs "
            "(action_id, worm_segment, archived_at) VALUES (?, ?, ?)",
            [(aid, worm_segment, archived_at) for aid in action_ids],
        )
        self._conn.commit()

    def close(self) -> None:
        """Close the SQLite connection.

        Example:
            >>> import tempfile
            >>> from pathlib import Path
            >>> from thot.audit.hot_store import SqliteHotStore
            >>> with tempfile.TemporaryDirectory() as td:
            ...     store = SqliteHotStore(Path(td) / "hot.db")
            ...     store.close()
            ...     True
            True
        """
        self._conn.close()


class PostgresHotStore:
    """PostgreSQL append-only hot store (compose / Helm audit profile).

    Example:
        >>> from thot.audit.hot_store import PostgresHotStore, SqliteHotStore
        >>> methods = {"append", "query", "close", "count"}
        >>> methods <= set(dir(PostgresHotStore))
        True
    """

    def __init__(self, dsn: str) -> None:
        """Connect to PostgreSQL and ensure append-only schema.

        Example:
            >>> import inspect
            >>> from thot.audit.hot_store import PostgresHotStore
            >>> "dsn" in inspect.signature(PostgresHotStore.__init__).parameters
            True
        """
        try:
            import psycopg
        except ImportError as exc:
            raise RuntimeError(
                "psycopg is required for AUDIT_HOT_STORE_URL postgres://"
            ) from exc
        self._conn = psycopg.connect(dsn)
        self._conn.autocommit = True
        self._ensure_schema()
        self._prev_hash = self._load_head()

    def _ensure_schema(self) -> None:
        """Create tables and append-only triggers when missing.

        Example:
            >>> import inspect
            >>> from thot.audit.hot_store import PostgresHotStore
            >>> inspect.isfunction(PostgresHotStore._ensure_schema)
            True
        """
        with self._conn.cursor() as cur:
            cur.execute(_POSTGRES_SCHEMA)
            cur.execute("""
                CREATE OR REPLACE FUNCTION tkeir_audit_deny_mutation()
                RETURNS trigger AS $$
                BEGIN
                  RAISE EXCEPTION 'action_records is append-only';
                END;
                $$ LANGUAGE plpgsql;
                """)
            cur.execute("""
                DO $$ BEGIN
                  CREATE TRIGGER tkeir_audit_no_update
                    BEFORE UPDATE OR DELETE ON action_records
                    FOR EACH ROW EXECUTE FUNCTION tkeir_audit_deny_mutation();
                EXCEPTION WHEN duplicate_object THEN NULL;
                END $$;
                """)

    def _load_head(self) -> str:
        """Return latest record hash from PostgreSQL.

        Example:
            >>> import inspect
            >>> from thot.audit.hot_store import PostgresHotStore
            >>> inspect.isfunction(PostgresHotStore._load_head)
            True
        """
        with self._conn.cursor() as cur:
            cur.execute(
                "SELECT record_hash FROM action_records "
                "ORDER BY id DESC LIMIT 1"
            )
            row = cur.fetchone()
        return row[0] if row else ""

    def append(self, record: ActionRecord) -> ActionRecord:
        """Seal and append one ActionRecord (PostgreSQL).

        Example:
            >>> import inspect
            >>> from thot.audit.hot_store import PostgresHotStore
            >>> inspect.isfunction(PostgresHotStore.append)
            True
        """
        sealed = record.seal(self._prev_hash)
        payload = json.dumps(
            sealed.model_dump(by_alias=True, mode="json"),
            ensure_ascii=False,
        )
        with self._conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO action_records (
                    action_id, correlation_id, occurred_at,
                    actor_id, actor_type, intent,
                    record_json, prev_hash, record_hash
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    sealed.action_id,
                    sealed.correlation_id,
                    sealed.occurred_at,
                    sealed.actor.id,
                    sealed.actor.type,
                    sealed.intent.declared,
                    payload,
                    sealed.evidence.prev_hash,
                    sealed.evidence.record_hash,
                ),
            )
        self._prev_hash = sealed.evidence.record_hash
        return sealed

    @property
    def prev_hash(self) -> str:
        """Latest sealed record hash.

        Example:
            >>> from thot.audit.hot_store import PostgresHotStore
            >>> isinstance(PostgresHotStore.prev_hash, property)
            True
        """
        return self._prev_hash

    def get_by_correlation(self, correlation_id: str) -> list[ActionRecord]:
        """Fetch records by correlation id (PostgreSQL).

        Example:
            >>> import inspect
            >>> from thot.audit.hot_store import PostgresHotStore
            >>> "correlation_id" in inspect.signature(
            ...     PostgresHotStore.get_by_correlation
            ... ).parameters
            True
        """
        with self._conn.cursor() as cur:
            cur.execute(
                "SELECT record_json FROM action_records "
                "WHERE correlation_id = %s ORDER BY id",
                (correlation_id,),
            )
            rows = cur.fetchall()
        return [_record_from_json(row[0]) for row in rows]

    def query(
        self,
        *,
        correlation_id: str | None = None,
        actor_id: str | None = None,
        occurred_from: str | None = None,
        occurred_to: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[ActionRecord]:
        """Search records with optional filters (PostgreSQL).

        Example:
            >>> import inspect
            >>> from thot.audit.hot_store import PostgresHotStore
            >>> "limit" in inspect.signature(PostgresHotStore.query).parameters
            True
        """
        clauses: list[str] = []
        params: list[Any] = []
        if correlation_id:
            clauses.append("correlation_id = %s")
            params.append(correlation_id)
        if actor_id:
            clauses.append("actor_id = %s")
            params.append(actor_id)
        if occurred_from:
            clauses.append("occurred_at >= %s")
            params.append(occurred_from)
        if occurred_to:
            clauses.append("occurred_at <= %s")
            params.append(occurred_to)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        params.extend([limit, offset])
        with self._conn.cursor() as cur:
            cur.execute(
                f"SELECT record_json FROM action_records {where} "
                "ORDER BY id LIMIT %s OFFSET %s",
                params,
            )
            rows = cur.fetchall()
        return [_record_from_json(row[0]) for row in rows]

    def iter_all(self) -> list[ActionRecord]:
        """Return all records in insertion order (PostgreSQL).

        Example:
            >>> import inspect
            >>> from thot.audit.hot_store import PostgresHotStore
            >>> inspect.isfunction(PostgresHotStore.iter_all)
            True
        """
        with self._conn.cursor() as cur:
            cur.execute("SELECT record_json FROM action_records ORDER BY id")
            rows = cur.fetchall()
        return [_record_from_json(row[0]) for row in rows]

    def count(self) -> int:
        """Return total record count (PostgreSQL).

        Example:
            >>> import inspect
            >>> from thot.audit.hot_store import PostgresHotStore
            >>> inspect.isfunction(PostgresHotStore.count)
            True
        """
        with self._conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM action_records")
            row = cur.fetchone()
        return int(row[0]) if row else 0

    def unarchived(self, *, limit: int = 1000) -> list[ActionRecord]:
        """List records without WORM refs (PostgreSQL).

        Example:
            >>> import inspect
            >>> from thot.audit.hot_store import PostgresHotStore
            >>> "limit" in inspect.signature(PostgresHotStore.unarchived).parameters
            True
        """
        with self._conn.cursor() as cur:
            cur.execute(
                """
                SELECT r.record_json FROM action_records r
                LEFT JOIN archive_refs a ON a.action_id = r.action_id
                WHERE a.action_id IS NULL
                ORDER BY r.id LIMIT %s
                """,
                (limit,),
            )
            rows = cur.fetchall()
        return [_record_from_json(row[0]) for row in rows]

    def mark_archived(
        self,
        action_ids: list[str],
        *,
        worm_segment: str,
        archived_at: str,
    ) -> None:
        """Stamp WORM segment refs (PostgreSQL).

        Example:
            >>> import inspect
            >>> from thot.audit.hot_store import PostgresHotStore
            >>> "worm_segment" in inspect.signature(
            ...     PostgresHotStore.mark_archived
            ... ).parameters
            True
        """
        if not action_ids:
            return
        with self._conn.cursor() as cur:
            cur.executemany(
                "INSERT INTO archive_refs (action_id, worm_segment, archived_at) "
                "VALUES (%s, %s, %s) ON CONFLICT DO NOTHING",
                [(aid, worm_segment, archived_at) for aid in action_ids],
            )

    def close(self) -> None:
        """Close the PostgreSQL connection.

        Example:
            >>> import inspect
            >>> from thot.audit.hot_store import PostgresHotStore
            >>> inspect.isfunction(PostgresHotStore.close)
            True
        """
        self._conn.close()


def open_hot_store(url: str | None) -> HotStore | None:
    """Open a hot store from ``AUDIT_HOT_STORE_URL``.

    Args:
        url: ``sqlite://`` or ``postgres://`` URL, or None.

    Returns:
        HotStore instance, or None when ``url`` is empty.

    Example:
        >>> import tempfile
        >>> from thot.audit.hot_store import open_hot_store, SqliteHotStore
        >>> with tempfile.TemporaryDirectory() as td:
        ...     store = open_hot_store(f"sqlite:///{td}/hot.db")
        ...     isinstance(store, SqliteHotStore)
        True
    """
    if not url:
        return None
    parsed = urlparse(url)
    if parsed.scheme in {"sqlite", "file"}:
        path = Path(parsed.path)
        if parsed.netloc:
            path = Path(f"/{parsed.netloc}{parsed.path}")
        return SqliteHotStore(path)
    if parsed.scheme in {"postgres", "postgresql"}:
        return PostgresHotStore(url)
    raise ValueError(f"Unsupported hot store URL scheme: {parsed.scheme}")
