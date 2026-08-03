"""Title: Archiver

Export closed hot-store segments to WORM storage.

Author: Eric Blaudez

Copyright (c) 2026 Thales
Licensed under the MIT License.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from thot.action.models import ActionRecord, new_action_id, utc_now_rfc3339
from thot.audit.hot_store import HotStore, SqliteHotStore
from thot.audit.worm_store import WormSegmentStore


def archive_unarchived(
    hot: HotStore,
    worm: WormSegmentStore,
    *,
    batch_size: int = 500,
) -> str | None:
    """Move unarchived records into a WORM segment.

    Returns:
        Segment id when records were archived, else ``None``.

    Example:
        >>> with tempfile.TemporaryDirectory() as td:
        ...     root = Path(td)
        ...     hot = SqliteHotStore(root / "hot.db")
        ...     worm = WormSegmentStore(root / "worm")
        ...     _ = hot.append(ActionRecord(correlation_id="p" * 32))
        ...     seg = archive_unarchived(hot, worm)
        ...     hot.close()
        ...     seg is not None and len(worm.list_segments()) == 1
        True
    """
    records = hot.unarchived(limit=batch_size)
    if not records:
        return None
    segment_id = new_action_id()
    worm_uri = worm.write_segment(segment_id, records)
    now = utc_now_rfc3339()
    hot.mark_archived(
        [record.action_id for record in records],
        worm_segment=worm_uri,
        archived_at=now,
    )
    if records:
        worm.write_anchor(
            record_hash=records[-1].evidence.record_hash,
            segment_id=segment_id,
        )
    return segment_id
