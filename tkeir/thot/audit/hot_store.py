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
    """Query and append interface for the audit hot tier."""

    def append(self, record: ActionRecord) -> ActionRecord:
        """Persist one sealed record; return stored copy."""

    @property
    def prev_hash(self) -> str:
        """Latest ``record_hash`` in the chain."""

    def get_by_correlation(self, correlation_id: str) -> list[ActionRecord]:
        """Return records for a correlation id ordered by id."""

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
        """Paginated search."""

    def iter_all(self) -> list[ActionRecord]:
        """Return all records in chain order (verification)."""

    def count(self) -> int:
        """Total stored records."""

    def unarchived(self, *, limit: int = 1000) -> list[ActionRecord]:
        """Records not yet assigned a WORM segment."""

    def mark_archived(
        self,
        action_ids: list[str],
        *,
        worm_segment: str,
        archived_at: str,
    ) -> None:
        """Stamp WORM segment refs on exported records."""

    def close(self) -> None:
        """Release connections."""


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
    return ActionRecord.model_validate(json.loads(payload))


class SqliteHotStore:
    """SQLite-backed append-only hot store (dev, tests, compose)."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(_SCHEMA)
        self._conn.commit()
        self._prev_hash = self._load_head()

    def _load_head(self) -> str:
        row = self._conn.execute(
            "SELECT record_hash FROM action_records ORDER BY id DESC LIMIT 1"
        ).fetchone()
        return row["record_hash"] if row else ""

    def append(self, record: ActionRecord) -> ActionRecord:
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
        return self._prev_hash

    def get_by_correlation(self, correlation_id: str) -> list[ActionRecord]:
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
        rows = self._conn.execute(
            "SELECT record_json FROM action_records ORDER BY id"
        ).fetchall()
        return [_record_from_json(row["record_json"]) for row in rows]

    def count(self) -> int:
        row = self._conn.execute(
            "SELECT COUNT(*) AS c FROM action_records"
        ).fetchone()
        return int(row["c"]) if row else 0

    def unarchived(self, *, limit: int = 1000) -> list[ActionRecord]:
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
        if not action_ids:
            return
        self._conn.executemany(
            "INSERT OR IGNORE INTO archive_refs "
            "(action_id, worm_segment, archived_at) VALUES (?, ?, ?)",
            [(aid, worm_segment, archived_at) for aid in action_ids],
        )
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()


class PostgresHotStore:
    """PostgreSQL append-only hot store (compose / Helm audit profile)."""

    def __init__(self, dsn: str) -> None:
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
        with self._conn.cursor() as cur:
            cur.execute(
                "SELECT record_hash FROM action_records "
                "ORDER BY id DESC LIMIT 1"
            )
            row = cur.fetchone()
        return row[0] if row else ""

    def append(self, record: ActionRecord) -> ActionRecord:
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
        return self._prev_hash

    def get_by_correlation(self, correlation_id: str) -> list[ActionRecord]:
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
        with self._conn.cursor() as cur:
            cur.execute("SELECT record_json FROM action_records ORDER BY id")
            rows = cur.fetchall()
        return [_record_from_json(row[0]) for row in rows]

    def count(self) -> int:
        with self._conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM action_records")
            row = cur.fetchone()
        return int(row[0]) if row else 0

    def unarchived(self, *, limit: int = 1000) -> list[ActionRecord]:
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
        if not action_ids:
            return
        with self._conn.cursor() as cur:
            cur.executemany(
                "INSERT INTO archive_refs (action_id, worm_segment, archived_at) "
                "VALUES (%s, %s, %s) ON CONFLICT DO NOTHING",
                [(aid, worm_segment, archived_at) for aid in action_ids],
            )

    def close(self) -> None:
        self._conn.close()


def open_hot_store(url: str | None) -> HotStore | None:
    """Open a hot store from ``AUDIT_HOT_STORE_URL``."""
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
