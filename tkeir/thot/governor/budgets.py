"""Title: Budgets

Consumable budget tracking per actor.

Author: Eric Blaudez

Copyright (c) 2026 Thales
Licensed under the MIT License.
"""

from __future__ import annotations

import sqlite3
import threading
from pathlib import Path

from thot.governor.config import GovernorSettings
from thot.governor.models import BudgetSnapshot

_SCHEMA = """
CREATE TABLE IF NOT EXISTS budgets (
    actor_id TEXT NOT NULL,
    unit TEXT NOT NULL,
    limit_amount REAL NOT NULL,
    consumed REAL NOT NULL DEFAULT 0,
    PRIMARY KEY (actor_id, unit)
);
"""


class BudgetStore:
    """SQLite-backed budget counters.

    Example:
        >>> import tempfile
        >>> from pathlib import Path
        >>> from thot.governor.budgets import BudgetStore
        >>> from thot.governor.config import governor_settings
        >>> with tempfile.TemporaryDirectory() as td:
        ...     store = BudgetStore(Path(td) / "b.db", governor_settings())
        ...     snap = store.snapshot("u1", "docs", limit=100.0)
        ...     store.close()
        ...     snap.consumed == 0.0
        True
    """

    def __init__(self, path: Path, settings: GovernorSettings) -> None:
        """Open or create the SQLite budget database.

        Example:
            >>> import tempfile
            >>> from pathlib import Path
            >>> from thot.governor.budgets import BudgetStore
            >>> from thot.governor.config import governor_settings
            >>> with tempfile.TemporaryDirectory() as td:
            ...     p = Path(td) / "b.db"
            ...     store = BudgetStore(p, governor_settings())
            ...     p.is_file()
            True
        """
        self._settings = settings
        path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(_SCHEMA)
        self._conn.commit()
        self._lock = threading.Lock()

    def _ensure_row(self, actor_id: str, unit: str, limit: float) -> None:
        """Insert a budget row when missing (idempotent).

        Example:
            >>> import tempfile
            >>> from pathlib import Path
            >>> from thot.governor.budgets import BudgetStore
            >>> from thot.governor.config import governor_settings
            >>> with tempfile.TemporaryDirectory() as td:
            ...     store = BudgetStore(Path(td) / "b.db", governor_settings())
            ...     store._ensure_row("u1", "docs", 50.0)
            ...     snap = store.snapshot("u1", "docs", limit=50.0)
            ...     store.close()
            ...     snap.limit
            50.0
        """
        self._conn.execute(
            """
            INSERT INTO budgets (actor_id, unit, limit_amount, consumed)
            VALUES (?, ?, ?, 0)
            ON CONFLICT(actor_id, unit) DO NOTHING
            """,
            (actor_id, unit, limit),
        )
        self._conn.commit()

    def snapshot(
        self, actor_id: str, unit: str, *, limit: float
    ) -> BudgetSnapshot:
        """Return current budget snapshot without consuming.

        Example:
            >>> import tempfile
            >>> from pathlib import Path
            >>> from thot.governor.budgets import BudgetStore
            >>> from thot.governor.config import governor_settings
            >>> with tempfile.TemporaryDirectory() as td:
            ...     store = BudgetStore(Path(td) / "b.db", governor_settings())
            ...     snap = store.snapshot("u1", "docs", limit=10.0)
            ...     store.close()
            ...     snap.blocked
            False
        """
        with self._lock:
            self._ensure_row(actor_id, unit, limit)
            row = self._conn.execute(
                """
                SELECT limit_amount, consumed FROM budgets
                WHERE actor_id = ? AND unit = ?
                """,
                (actor_id, unit),
            ).fetchone()
        consumed = float(row["consumed"]) if row else 0.0
        cap = float(row["limit_amount"]) if row else limit
        ratio = consumed / cap if cap > 0 else 0.0
        throttled = ratio >= self._settings.throttle_ratio
        blocked = ratio >= 1.0
        return BudgetSnapshot(
            actor_id=actor_id,
            unit=unit,
            limit=cap,
            consumed=consumed,
            ratio=ratio,
            throttled=throttled,
            blocked=blocked,
        )

    def consume(
        self, actor_id: str, unit: str, amount: float, *, limit: float
    ) -> BudgetSnapshot:
        """Increment consumed budget and return updated snapshot.

        Example:
            >>> import tempfile
            >>> from pathlib import Path
            >>> from thot.governor.budgets import BudgetStore
            >>> from thot.governor.config import governor_settings
            >>> with tempfile.TemporaryDirectory() as td:
            ...     store = BudgetStore(Path(td) / "b.db", governor_settings())
            ...     snap = store.consume("u1", "docs", 1.0, limit=10.0)
            ...     store.close()
            ...     snap.consumed
            1.0
        """
        with self._lock:
            self._ensure_row(actor_id, unit, limit)
            self._conn.execute(
                """
                UPDATE budgets SET consumed = consumed + ?
                WHERE actor_id = ? AND unit = ?
                """,
                (amount, actor_id, unit),
            )
            self._conn.commit()
        return self.snapshot(actor_id, unit, limit=limit)

    def close(self) -> None:
        """Close the SQLite connection.

        Example:
            >>> import tempfile
            >>> from pathlib import Path
            >>> from thot.governor.budgets import BudgetStore
            >>> from thot.governor.config import governor_settings
            >>> with tempfile.TemporaryDirectory() as td:
            ...     store = BudgetStore(Path(td) / "b.db", governor_settings())
            ...     store.close()
            ...     True
            True
        """
        self._conn.close()
