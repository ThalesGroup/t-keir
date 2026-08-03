"""Title: Verify

Hash-chain verification for hot and WORM tiers.

Author: Eric Blaudez

Copyright (c) 2026 Thales
Licensed under the MIT License.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from thot.action.models import ActionRecord
from thot.audit.hot_store import HotStore
from thot.audit.worm_store import WormSegmentStore


@dataclass
class VerifyReport:
    """Outcome of ``verify_chain``.

    Example:
        >>> from thot.audit.verify import VerifyReport
        >>> VerifyReport(ok=True, records_checked=2).ok
        True
    """

    ok: bool
    records_checked: int = 0
    errors: list[str] = field(default_factory=list)
    worm_segments_checked: int = 0


def verify_hot_chain(records: list[ActionRecord]) -> VerifyReport:
    """Re-hash the hot store chain.

    Args:
        records: Ordered ActionRecords (oldest first).

    Returns:
        VerifyReport with ``ok`` True when prev/record hashes match.

    Example:
        >>> from thot.action.models import ActionRecord
        >>> a = ActionRecord(correlation_id="e" * 32).seal("")
        >>> b = ActionRecord(correlation_id="e" * 32).seal(a.evidence.record_hash)
        >>> report = verify_hot_chain([a, b])
        >>> report.ok and report.records_checked == 2
        True
    """
    report = VerifyReport(ok=True)
    previous_hash = ""
    for record in records:
        report.records_checked += 1
        if record.evidence.prev_hash != previous_hash:
            report.ok = False
            report.errors.append(
                f"prev_hash mismatch at action_id={record.action_id}"
            )
        recomputed = record.compute_record_hash(record.evidence.prev_hash)
        if recomputed != record.evidence.record_hash:
            report.ok = False
            report.errors.append(
                f"record_hash mismatch at action_id={record.action_id}"
            )
        previous_hash = record.evidence.record_hash
    return report


def verify_store(
    hot: HotStore,
    worm: WormSegmentStore | None = None,
) -> VerifyReport:
    """Verify hot chain and optional WORM segment integrity.

    Example:
        >>> import tempfile
        >>> from pathlib import Path
        >>> from thot.action.models import ActionRecord
        >>> from thot.audit.hot_store import SqliteHotStore
        >>> from thot.audit.verify import verify_store
        >>> from thot.audit.worm_store import WormSegmentStore
        >>> with tempfile.TemporaryDirectory() as td:
        ...     root = Path(td)
        ...     hot = SqliteHotStore(root / "hot.db")
        ...     _ = hot.append(ActionRecord(correlation_id="q" * 32))
        ...     report = verify_store(hot, WormSegmentStore(root / "worm"))
        ...     hot.close()
        ...     report.ok and report.records_checked == 1
        True
    """
    records = hot.iter_all()
    report = verify_hot_chain(records)
    if worm is None:
        return report
    for segment_id in worm.list_segments():
        try:
            worm.read_segment(segment_id)
            report.worm_segments_checked += 1
        except (OSError, ValueError) as exc:
            report.ok = False
            report.errors.append(f"WORM segment {segment_id}: {exc}")
    return report
