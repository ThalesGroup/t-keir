"""Title: Sink

Observe-mode ActionRecord sinks (in-memory until audit store lands).

Author: Eric Blaudez

Copyright (c) 2026 Thales
Licensed under the MIT License.
"""

from __future__ import annotations

from collections import deque
from threading import Lock
from typing import Protocol

from thot.action.models import ActionRecord


class ActionSink(Protocol):
    """Destination for sealed ActionRecords in observe/enforce modes."""

    def append(self, record: ActionRecord) -> None:
        """Persist or buffer one ActionRecord."""

    @property
    def prev_hash(self) -> str:
        """Latest ``record_hash`` in the chain (empty if none)."""


class InMemoryActionSink:
    """Bounded append-only buffer for local observe mode and tests."""

    def __init__(self, maxlen: int = 10_000) -> None:
        """Create a sink retaining at most ``maxlen`` records."""
        self._records: deque[ActionRecord] = deque(maxlen=maxlen)
        self._lock = Lock()
        self._prev_hash = ""

    def append(self, record: ActionRecord) -> None:
        """Append a sealed record and advance the chain head.

        Args:
            record: ActionRecord to seal against the current chain head.

        Example:
            >>> from thot.action.models import ActionRecord
            >>> sink = InMemoryActionSink()
            >>> sink.append(ActionRecord(correlation_id="c" * 32))
            >>> len(sink)
            1
            >>> len(sink.prev_hash) == 64
            True
        """
        with self._lock:
            sealed = record.seal(self._prev_hash)
            self._records.append(sealed)
            self._prev_hash = sealed.evidence.record_hash

    @property
    def prev_hash(self) -> str:
        with self._lock:
            return self._prev_hash

    def clear(self) -> None:
        """Drop all buffered records (tests only)."""
        with self._lock:
            self._records.clear()
            self._prev_hash = ""

    def list_by_correlation(self, correlation_id: str) -> list[ActionRecord]:
        """Return buffered records matching ``correlation_id``.

        Example:
            >>> from thot.action.models import ActionRecord
            >>> sink = InMemoryActionSink()
            >>> cid = "d" * 32
            >>> sink.append(ActionRecord(correlation_id=cid))
            >>> [r.correlation_id for r in sink.list_by_correlation(cid)] == [cid]
            True
        """
        with self._lock:
            return [
                r for r in self._records if r.correlation_id == correlation_id
            ]

    def __len__(self) -> int:
        with self._lock:
            return len(self._records)


_MEMORY_SINK = InMemoryActionSink()
_RESOLVED_SINK: ActionSink | None = None


def default_action_sink() -> ActionSink:
    """Return the process-wide ActionRecord sink.

    When ``AUDIT_HOT_STORE_URL`` is set (or ``AUDIT_SINK_MODE=hot|dual``),
    records are mirrored to the audit hot store.
    """
    global _RESOLVED_SINK
    if _RESOLVED_SINK is not None:
        return _RESOLVED_SINK
    try:
        from thot.audit.config import audit_settings
        from thot.audit.hot_store import open_hot_store
        from thot.audit.sink_bridge import (
            CompositeActionSink,
            HotStoreActionSink,
        )

        settings = audit_settings()
        hot = open_hot_store(settings.hot_store_url)
        if hot is None or settings.sink_mode == "memory":
            _RESOLVED_SINK = _MEMORY_SINK
        elif settings.sink_mode == "hot":
            _RESOLVED_SINK = HotStoreActionSink(hot)
        else:
            _RESOLVED_SINK = CompositeActionSink(
                _MEMORY_SINK,
                HotStoreActionSink(hot),
            )
    except Exception:
        _RESOLVED_SINK = _MEMORY_SINK
    return _RESOLVED_SINK


def reset_action_sink_for_tests() -> None:
    """Reset lazy sink resolution (unit tests only)."""
    global _RESOLVED_SINK
    _RESOLVED_SINK = None
    _MEMORY_SINK.clear()
