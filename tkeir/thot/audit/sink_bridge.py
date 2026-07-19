"""Bridge ActionRecords into the audit hot store."""

from __future__ import annotations

from thot.action.models import ActionRecord
from thot.action.sink import InMemoryActionSink
from thot.audit.hot_store import HotStore


class HotStoreActionSink:
    """Append sealed records to a persistent hot store."""

    def __init__(self, store: HotStore) -> None:
        self._store = store

    def append(self, record: ActionRecord) -> None:
        self._store.append(record)

    @property
    def prev_hash(self) -> str:
        return self._store.prev_hash


class CompositeActionSink:
    """Write to in-memory buffer and optional hot store."""

    def __init__(
        self,
        memory: InMemoryActionSink,
        hot: HotStoreActionSink | None,
    ) -> None:
        self._memory = memory
        self._hot = hot

    def append(self, record: ActionRecord) -> None:
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
        if self._hot is not None:
            return self._hot.prev_hash
        return self._memory.prev_hash
