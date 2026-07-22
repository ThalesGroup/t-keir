"""Title: Worm store

Filesystem WORM segment store (dev / non-prod GOVERNANCE mode).

Author: Eric Blaudez

Copyright (c) 2026 Thales
Licensed under the MIT License.
"""

from __future__ import annotations

import gzip
import json
import logging
import os
from pathlib import Path

from thot.action.models import ActionRecord, sha256_hex, utc_now_rfc3339

LOGGER = logging.getLogger(__name__)


class WormSegmentStore:
    """Write-once JSONL.gz segments with SHA-256 sidecars."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)

    def segment_path(self, segment_id: str) -> Path:
        return self.root / f"{segment_id}.jsonl.gz"

    def sha_path(self, segment_id: str) -> Path:
        return self.root / f"{segment_id}.sha256"

    def write_segment(
        self,
        segment_id: str,
        records: list[ActionRecord],
    ) -> str:
        """Write records to a new segment; return relative segment URI.

        Args:
            segment_id: Unique segment name (file stem).
            records: Non-empty list of ActionRecords.

        Returns:
            ``worm://<segment_id>`` URI.

        Raises:
            ValueError: If ``records`` is empty.
            FileExistsError: If the segment already exists.

        Example:
            >>> import tempfile
            >>> from pathlib import Path
            >>> from thot.action.models import ActionRecord
            >>> from thot.audit.worm_store import WormSegmentStore
            >>> with tempfile.TemporaryDirectory() as td:
            ...     store = WormSegmentStore(Path(td))
            ...     uri = store.write_segment(
            ...         "demo", [ActionRecord(correlation_id="f" * 32).seal("")]
            ...     )
            ...     uri == "worm://demo" and len(store.read_segment("demo")) == 1
            True
        """
        if not records:
            raise ValueError("Cannot write empty WORM segment")
        if self.segment_path(segment_id).exists():
            raise FileExistsError(f"WORM segment already exists: {segment_id}")

        lines = [
            json.dumps(
                record.model_dump(by_alias=True, mode="json"),
                ensure_ascii=False,
            )
            for record in records
        ]
        body = ("\n".join(lines) + "\n").encode("utf-8")
        compressed = gzip.compress(body)
        seg_path = self.segment_path(segment_id)
        tmp = seg_path.with_suffix(".tmp")
        tmp.write_bytes(compressed)
        os.replace(tmp, seg_path)
        digest = sha256_hex(compressed)
        sidecar = f"{digest}  {seg_path.name}\n"
        self.sha_path(segment_id).write_text(sidecar)
        # Optional MinIO / S3 object-lock mirror (when AUDIT_WORM_S3_ENDPOINT set)
        from thot.audit.s3_put import mirror_worm_segment

        try:
            mirror_worm_segment(
                segment_id=segment_id,
                compressed=compressed,
                sha_sidecar=sidecar.encode("utf-8"),
            )
        except Exception as exc:  # noqa: BLE001
            LOGGER.error("WORM S3 mirror failed for %s: %s", segment_id, exc)
        return f"worm://{segment_id}"

    def read_segment(self, segment_id: str) -> list[ActionRecord]:
        """Load and verify one segment."""
        seg_path = self.segment_path(segment_id)
        if not seg_path.is_file():
            raise FileNotFoundError(segment_id)
        compressed = seg_path.read_bytes()
        expected = self.sha_path(segment_id).read_text().split()[0]
        actual = sha256_hex(compressed)
        if actual != expected:
            raise ValueError(
                f"WORM segment hash mismatch for {segment_id}: "
                f"{actual} != {expected}"
            )
        raw = gzip.decompress(compressed).decode("utf-8")
        records: list[ActionRecord] = []
        for line in raw.splitlines():
            if line.strip():
                records.append(ActionRecord.model_validate(json.loads(line)))
        return records

    def list_segments(self) -> list[str]:
        return sorted(
            path.name.removesuffix(".jsonl.gz")
            for path in self.root.glob("*.jsonl.gz")
        )

    def write_anchor(self, *, record_hash: str, segment_id: str) -> Path:
        """Persist a daily chain-head anchor."""
        anchors = self.root / "anchors"
        anchors.mkdir(parents=True, exist_ok=True)
        day = utc_now_rfc3339()[:10]
        path = anchors / f"{day}.json"
        payload = {
            "record_hash": record_hash,
            "segment_id": segment_id,
            "anchored_at": utc_now_rfc3339(),
        }
        path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        return path
