"""Title: Privacy

GDPR pseudonymization and crypto-shredding helpers.

Author: Eric Blaudez

Copyright (c) 2026 Thales
Licensed under the MIT License.
"""

from __future__ import annotations

import hashlib
import os
import sqlite3
from pathlib import Path

from thot.action.models import sha256_hex


class SubjectKeyStore:
    """Envelope keys kept outside the WORM tier."""

    def __init__(self, path: Path, *, salt: bytes | None = None) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._salt = salt or os.urandom(16)
        self._conn = sqlite3.connect(str(path), check_same_thread=False)
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS subject_keys (
                subject_id TEXT PRIMARY KEY,
                envelope_key BLOB NOT NULL,
                created_at TEXT NOT NULL
            )
            """)
        self._conn.commit()

    def pseudonym(self, subject_id: str) -> str:
        """Return a stable pseudonym for ``subject_id``.

        Args:
            subject_id: Raw subject identifier (never store in WORM).

        Returns:
            Hex digest derived from envelope key + salt.

        Example:
            >>> import tempfile
            >>> from pathlib import Path
            >>> from thot.audit.privacy import SubjectKeyStore
            >>> with tempfile.TemporaryDirectory() as td:
            ...     keys = SubjectKeyStore(Path(td) / "keys.db", salt=b"salt")
            ...     a = keys.pseudonym("alice")
            ...     b = keys.pseudonym("alice")
            ...     keys.close()
            ...     a == b and len(a) == 64
            True
        """
        row = self._conn.execute(
            "SELECT envelope_key FROM subject_keys WHERE subject_id = ?",
            (subject_id,),
        ).fetchone()
        if row:
            key = row[0]
        else:
            key = os.urandom(32)
            self._conn.execute(
                "INSERT INTO subject_keys (subject_id, envelope_key, created_at) "
                "VALUES (?, ?, datetime('now'))",
                (subject_id, key),
            )
            self._conn.commit()
        digest = hashlib.pbkdf2_hmac(
            "sha256",
            subject_id.encode("utf-8"),
            self._salt + key,
            100_000,
        )
        return sha256_hex(digest)

    def forget(self, subject_id: str) -> bool:
        """Crypto-shred envelope key for ``subject_id``.

        Args:
            subject_id: Subject whose envelope key should be deleted.

        Returns:
            True if a key row was deleted.

        Example:
            >>> import tempfile
            >>> from pathlib import Path
            >>> from thot.audit.privacy import SubjectKeyStore
            >>> with tempfile.TemporaryDirectory() as td:
            ...     keys = SubjectKeyStore(Path(td) / "keys.db", salt=b"salt")
            ...     _ = keys.pseudonym("bob")
            ...     ok = keys.forget("bob")
            ...     keys.close()
            ...     ok
            True
        """
        cur = self._conn.execute(
            "DELETE FROM subject_keys WHERE subject_id = ?",
            (subject_id,),
        )
        self._conn.commit()
        return cur.rowcount > 0

    def close(self) -> None:
        self._conn.close()
