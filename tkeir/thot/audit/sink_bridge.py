"""Title: Sink bridge

Bridge ActionRecords into the audit hot store.

Author: Eric Blaudez

Copyright (c) 2026 Thales
Licensed under the MIT License.
"""

from __future__ import annotations

from thot.action.models import ActionRecord
from thot.action.sink import InMemoryActionSink
from thot.audit.hot_store import HotStore


class HotStoreActionSink:
    """Append sealed records to a persistent hot store.

    Example:
        >>> import tempfile
        >>> from pathlib import Path
        >>> from thot.action.models import ActionRecord
        >>> from thot.audit.hot_store import SqliteHotStore
        >>> from thot.audit.sink_bridge import HotStoreActionSink
        >>> with tempfile.TemporaryDirectory() as td:
        ...     hot = SqliteHotStore(Path(td) / "hot.db")
        ...     sink = HotStoreActionSink(hot)
        ...     sink.append(ActionRecord(correlation_id="u" * 32))
        ...     hot.count() == 1
        True
    """

    def __init__(self, store: HotStore) -> None:
        """Wrap a HotStore as an ActionSink.

        Example:
            >>> import tempfile
            >>> from pathlib import Path
            >>> from thot.audit.hot_store import SqliteHotStore
            >>> from thot.audit.sink_bridge import HotStoreActionSink
            >>> with tempfile.TemporaryDirectory() as td:
            ...     hot = SqliteHotStore(Path(td) / "hot.db")
            ...     isinstance(HotStoreActionSink(hot)._store, SqliteHotStore)
            True
        """
        self._store = store

    def append(self, record: ActionRecord) -> None:
        """Seal and persist one ActionRecord.

        Example:
            >>> import tempfile
            >>> from pathlib import Path
            >>> from thot.action.models import ActionRecord
            >>> from thot.audit.hot_store import SqliteHotStore
            >>> from thot.audit.sink_bridge import HotStoreActionSink
            >>> with tempfile.TemporaryDirectory() as td:
            ...     hot = SqliteHotStore(Path(td) / "hot.db")
            ...     sink = HotStoreActionSink(hot)
            ...     sink.append(ActionRecord(correlation_id="v" * 32))
            ...     len(sink.prev_hash) > 0
            True
        """
        self._store.append(record)

    @property
    def prev_hash(self) -> str:
        """Latest record hash from the backing hot store.

        Example:
            >>> import tempfile
            >>> from pathlib import Path
            >>> from thot.audit.hot_store import SqliteHotStore
            >>> from thot.audit.sink_bridge import HotStoreActionSink
            >>> with tempfile.TemporaryDirectory() as td:
            ...     hot = SqliteHotStore(Path(td) / "hot.db")
            ...     HotStoreActionSink(hot).prev_hash
            ''
        """
        return self._store.prev_hash


class CompositeActionSink:
    """Write to in-memory buffer and optional hot store.

    Example:
        >>> from thot.action.sink import InMemoryActionSink
        >>> from thot.audit.sink_bridge import CompositeActionSink
        >>> CompositeActionSink(InMemoryActionSink(), None).prev_hash
        ''
    """

    def __init__(
        self,
        memory: InMemoryActionSink,
        hot: HotStoreActionSink | None,
    ) -> None:
        """Configure memory buffer and optional persistent hot sink.

        Example:
            >>> from thot.action.sink import InMemoryActionSink
            >>> from thot.audit.sink_bridge import CompositeActionSink
            >>> sink = CompositeActionSink(InMemoryActionSink(), None)
            >>> sink._hot is None
            True
        """
        self._memory = memory
        self._hot = hot

    def append(self, record: ActionRecord) -> None:
        """Append to memory and best-effort to hot store.

        Example:
            >>> from thot.action.models import ActionRecord
            >>> from thot.action.sink import InMemoryActionSink
            >>> from thot.audit.sink_bridge import CompositeActionSink
            >>> mem = InMemoryActionSink()
            >>> sink = CompositeActionSink(mem, None)
        >>> sink.append(ActionRecord(correlation_id="w" * 32))
        >>> len(mem)
        1
        """
        self._memory.append(record)
        if self._hot is not None:
            try:
                self._hot.append(record)
            except Exception:
                # Hot store failure must not break request path; audit API
                # surfaces write failures via metrics/alerts (Phase 9).
                pass

    @property
    def prev_hash(self) -> str:
        """Prefer hot-store hash; fall back to in-memory chain head.

        Example:
            >>> from thot.action.sink import InMemoryActionSink
            >>> from thot.audit.sink_bridge import CompositeActionSink
            >>> CompositeActionSink(InMemoryActionSink(), None).prev_hash
            ''
        """
        if self._hot is not None:
            return self._hot.prev_hash
        return self._memory.prev_hash
