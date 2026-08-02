"""Title: Approvals

Approval queue for escalated actions.

Author: Eric Blaudez

Copyright (c) 2026 Thales
Licensed under the MIT License.
"""

from __future__ import annotations

import json
import threading
from pathlib import Path

from thot.action.models import new_action_id, utc_now_rfc3339
from thot.governor.models import ApprovalItem


class ApprovalQueue:
    """JSON file queue for human approval workflows."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        if not self.path.is_file() or self.path.stat().st_size == 0:
            self._write([])
        else:
            try:
                self._read()
            except (json.JSONDecodeError, ValueError, OSError, TypeError):
                self._write([])

    def _read(self) -> list[ApprovalItem]:
        raw = json.loads(self.path.read_text(encoding="utf-8"))
        return [ApprovalItem.model_validate(item) for item in raw]

    def _write(self, items: list[ApprovalItem]) -> None:
        payload = [item.model_dump(mode="json") for item in items]
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        tmp.replace(self.path)

    def list_pending(self) -> list[ApprovalItem]:
        with self._lock:
            return [item for item in self._read() if item.status == "pending"]

    def list_all(self, *, limit: int = 100) -> list[ApprovalItem]:
        with self._lock:
            return self._read()[-limit:]

    def enqueue(
        self,
        *,
        correlation_id: str,
        actor_id: str,
        intent: str,
        reason: str,
    ) -> ApprovalItem:
        """Enqueue a pending approval item.

        Example:
            >>> import tempfile
            >>> from pathlib import Path
            >>> from thot.governor.approvals import ApprovalQueue
            >>> with tempfile.TemporaryDirectory() as td:
            ...     q = ApprovalQueue(Path(td) / "approvals.json")
            ...     item = q.enqueue(
            ...         correlation_id="g" * 32,
            ...         actor_id="user-1",
            ...         intent="ingest",
            ...         reason="escalate",
            ...     )
            ...     len(q.list_pending()) == 1 and item.status == "pending"
            True
        """
        item = ApprovalItem(
            approval_id=new_action_id(),
            correlation_id=correlation_id,
            actor_id=actor_id,
            intent=intent,
            reason=reason,
            created_at=utc_now_rfc3339(),
        )
        with self._lock:
            items = self._read()
            items.append(item)
            self._write(items)
        return item

    def get(self, approval_id: str) -> ApprovalItem | None:
        """Return one approval by id, or ``None``.

        Example:
            >>> import tempfile
            >>> from pathlib import Path
            >>> from thot.governor.approvals import ApprovalQueue
            >>> with tempfile.TemporaryDirectory() as td:
            ...     q = ApprovalQueue(Path(td) / "approvals.json")
            ...     item = q.enqueue(
            ...         correlation_id="i" * 32,
            ...         actor_id="user-1",
            ...         intent="generate",
            ...         reason="publish",
            ...     )
            ...     q.get(item.approval_id).intent
            'generate'
        """
        with self._lock:
            for item in self._read():
                if item.approval_id == approval_id:
                    return item
        return None

    def decide(
        self,
        approval_id: str,
        *,
        status: str,
    ) -> ApprovalItem | None:
        """Set approval status (``approved`` / ``denied``).

        Example:
            >>> import tempfile
            >>> from pathlib import Path
            >>> from thot.governor.approvals import ApprovalQueue
            >>> with tempfile.TemporaryDirectory() as td:
            ...     q = ApprovalQueue(Path(td) / "approvals.json")
            ...     item = q.enqueue(
            ...         correlation_id="h" * 32,
            ...         actor_id="user-1",
            ...         intent="ingest",
            ...         reason="escalate",
            ...     )
            ...     updated = q.decide(item.approval_id, status="approved")
            ...     updated is not None and updated.status == "approved"
            True
        """
        with self._lock:
            items = self._read()
            for index, item in enumerate(items):
                if item.approval_id != approval_id:
                    continue
                updated = item.model_copy(update={"status": status})
                items[index] = updated
                self._write(items)
                return updated
        return None
