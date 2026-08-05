"""Title: Persistent SimHash / URL dedupe index for the web collector.

Author: Eric Blaudez

Copyright (c) 2026 Thales
Licensed under the MIT License.
"""

from __future__ import annotations

import json
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from thot.action.models import utc_now_rfc3339
from thot.tools.collector.simhash import is_near_duplicate, simhash64


@dataclass(frozen=True)
class DedupeHit:
    """Result of a dedupe probe.

    Example:
        >>> DedupeHit(is_duplicate=False).is_duplicate
        False
    """

    is_duplicate: bool
    reason: str = ""
    matched_url: str | None = None
    matched_simhash: int | None = None
    simhash: int | None = None


class CollectorDedupeIndex:
    """Process-wide + on-disk index of collected URLs and SimHashes.

    Shared by ``/collect`` and ``/collect/batch`` so duplicates are suppressed
    across all collector traffic for this workspace.

    Example:
        >>> import tempfile
        >>> from pathlib import Path
        >>> from thot.tools.collector.dedupe import CollectorDedupeIndex
        >>> with tempfile.TemporaryDirectory() as td:
        ...     idx = CollectorDedupeIndex(Path(td))
        ...     first = idx.probe_and_register("https://a", "Unique content AAA 111")
        ...     second = idx.probe_and_register("https://a", "Unique content AAA 111")
        ...     first.is_duplicate, second.is_duplicate, second.reason
        (False, True, 'url')
    """

    def __init__(
        self,
        root: Path,
        *,
        max_hamming: int = 3,
        ngram: int = 3,
    ) -> None:
        """Load existing index from ``root/simhashes.jsonl`` when present.

        Example:
            >>> import tempfile
            >>> from pathlib import Path
            >>> from thot.tools.collector.dedupe import CollectorDedupeIndex
            >>> with tempfile.TemporaryDirectory() as td:
            ...     CollectorDedupeIndex(Path(td)).size
            0
        """
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.path = self.root / "simhashes.jsonl"
        self.max_hamming = max(0, int(max_hamming))
        self.ngram = max(1, int(ngram))
        self._lock = threading.Lock()
        self._urls: dict[str, int] = {}
        self._hashes: list[tuple[int, str]] = []
        self._load()

    @property
    def size(self) -> int:
        """Number of registered fingerprints.

        Example:
            >>> import tempfile
            >>> from pathlib import Path
            >>> from thot.tools.collector.dedupe import CollectorDedupeIndex
            >>> with tempfile.TemporaryDirectory() as td:
            ...     CollectorDedupeIndex(Path(td)).size
            0
        """
        with self._lock:
            return len(self._hashes)

    def _load(self) -> None:
        """Load fingerprints from the JSONL store if present.

        Example:
            >>> import tempfile
            >>> from pathlib import Path
            >>> from thot.tools.collector.dedupe import CollectorDedupeIndex
            >>> with tempfile.TemporaryDirectory() as td:
            ...     CollectorDedupeIndex(Path(td)).size
            0
        """
        if not self.path.is_file():
            return
        for line in self.path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            url = str(row.get("url") or "").strip()
            try:
                fingerprint = int(row.get("simhash"))
            except (TypeError, ValueError):
                continue
            if not url:
                continue
            self._urls[url] = fingerprint
            self._hashes.append((fingerprint, url))

    def _append(self, record: dict[str, Any]) -> None:
        """Append one JSON record to the on-disk index.

        Example:
            >>> import tempfile
            >>> from pathlib import Path
            >>> from thot.tools.collector.dedupe import CollectorDedupeIndex
            >>> with tempfile.TemporaryDirectory() as td:
            ...     idx = CollectorDedupeIndex(Path(td))
            ...     idx._append({"url": "https://x", "simhash": 1})
            ...     idx.path.is_file()
            True
        """
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")

    def known_url(self, url: str) -> bool:
        """Return True when ``url`` was already collected.

        Example:
            >>> import tempfile
            >>> from pathlib import Path
            >>> from thot.tools.collector.dedupe import CollectorDedupeIndex
            >>> with tempfile.TemporaryDirectory() as td:
            ...     idx = CollectorDedupeIndex(Path(td))
            ...     _ = idx.probe_and_register("https://known", "body " * 30)
            ...     idx.known_url("https://known"), idx.known_url("https://other")
            (True, False)
        """
        with self._lock:
            return (
                bool((url or "").strip()) and (url or "").strip() in self._urls
            )

    def probe(self, url: str, markdown: str) -> DedupeHit:
        """Check URL / SimHash without registering.

        Example:
            >>> import tempfile
            >>> from pathlib import Path
            >>> from thot.tools.collector.dedupe import CollectorDedupeIndex
            >>> with tempfile.TemporaryDirectory() as td:
            ...     idx = CollectorDedupeIndex(Path(td))
            ...     idx.probe("https://x", "hello").is_duplicate
            False
        """
        normalized_url = (url or "").strip()
        fingerprint = simhash64(markdown, ngram=self.ngram)
        with self._lock:
            if normalized_url and normalized_url in self._urls:
                return DedupeHit(
                    is_duplicate=True,
                    reason="url",
                    matched_url=normalized_url,
                    matched_simhash=self._urls[normalized_url],
                    simhash=fingerprint,
                )
            known = [item[0] for item in self._hashes]
            near, matched = is_near_duplicate(
                fingerprint, known, max_distance=self.max_hamming
            )
            if near:
                matched_url = next(
                    (u for h, u in self._hashes if h == matched), None
                )
                return DedupeHit(
                    is_duplicate=True,
                    reason="simhash",
                    matched_url=matched_url,
                    matched_simhash=matched,
                    simhash=fingerprint,
                )
        return DedupeHit(is_duplicate=False, simhash=fingerprint)

    def register(
        self,
        url: str,
        markdown: str,
        *,
        simhash: int | None = None,
        meta: dict[str, Any] | None = None,
    ) -> int:
        """Persist a new document fingerprint (caller must have probed first).

        Example:
            >>> import tempfile
            >>> from pathlib import Path
            >>> from thot.tools.collector.dedupe import CollectorDedupeIndex
            >>> with tempfile.TemporaryDirectory() as td:
            ...     idx = CollectorDedupeIndex(Path(td))
            ...     h = idx.register("https://y", "brand new page text 42")
            ...     isinstance(h, int)
            True
        """
        normalized_url = (url or "").strip()
        fingerprint = (
            int(simhash)
            if simhash is not None
            else simhash64(markdown, ngram=self.ngram)
        )
        record = {
            "url": normalized_url,
            "simhash": fingerprint,
            "simhash_hex": f"{fingerprint:016x}",
            "at": utc_now_rfc3339(),
            **(meta or {}),
        }
        with self._lock:
            if normalized_url:
                self._urls[normalized_url] = fingerprint
            self._hashes.append((fingerprint, normalized_url))
            self._append(record)
        return fingerprint

    def probe_and_register(self, url: str, markdown: str) -> DedupeHit:
        """Atomic probe; register when not duplicate.

        Example:
            >>> import tempfile
            >>> from pathlib import Path
            >>> from thot.tools.collector.dedupe import CollectorDedupeIndex
            >>> with tempfile.TemporaryDirectory() as td:
            ...     idx = CollectorDedupeIndex(Path(td))
            ...     a = idx.probe_and_register("https://z", "Same body " * 20)
            ...     b = idx.probe_and_register("https://z2", "Same body " * 20)
            ...     a.is_duplicate, b.is_duplicate, b.reason
            (False, True, 'simhash')
        """
        with self._lock:
            normalized_url = (url or "").strip()
            fingerprint = simhash64(markdown, ngram=self.ngram)
            if normalized_url and normalized_url in self._urls:
                return DedupeHit(
                    is_duplicate=True,
                    reason="url",
                    matched_url=normalized_url,
                    matched_simhash=self._urls[normalized_url],
                    simhash=fingerprint,
                )
            known = [item[0] for item in self._hashes]
            near, matched = is_near_duplicate(
                fingerprint, known, max_distance=self.max_hamming
            )
            if near:
                matched_url = next(
                    (u for h, u in self._hashes if h == matched), None
                )
                return DedupeHit(
                    is_duplicate=True,
                    reason="simhash",
                    matched_url=matched_url,
                    matched_simhash=matched,
                    simhash=fingerprint,
                )
            if normalized_url:
                self._urls[normalized_url] = fingerprint
            self._hashes.append((fingerprint, normalized_url))
            self._append(
                {
                    "url": normalized_url,
                    "simhash": fingerprint,
                    "simhash_hex": f"{fingerprint:016x}",
                    "at": utc_now_rfc3339(),
                }
            )
            return DedupeHit(is_duplicate=False, simhash=fingerprint)


def dedupe_index_for_workspace(
    workspace: Path,
    *,
    max_hamming: int = 3,
) -> CollectorDedupeIndex:
    """Build the default index under ``workspace/collector/dedupe``.

    Example:
        >>> import tempfile
        >>> from pathlib import Path
        >>> from thot.tools.collector.dedupe import dedupe_index_for_workspace
        >>> with tempfile.TemporaryDirectory() as td:
        ...     dedupe_index_for_workspace(Path(td)).path.name
        'simhashes.jsonl'
    """
    return CollectorDedupeIndex(
        Path(workspace) / "collector" / "dedupe",
        max_hamming=max_hamming,
    )
