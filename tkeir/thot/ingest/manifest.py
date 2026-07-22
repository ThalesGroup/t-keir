"""Title: Manifest

Manifest builders and idempotency key helpers.

Author: Eric Blaudez

Copyright (c) 2026 Thales
Licensed under the MIT License.
"""

from __future__ import annotations

from pathlib import Path

from thot.action.models import sha256_hex
from thot.ingest.models import (
    EmbedderInfo,
    IngestManifest,
    LineageInfo,
    SourceInfo,
)


def pipeline_config_sha256(config_path: Path) -> str:
    """Hash the pipeline configuration file bytes.

    Example:
        >>> import tempfile
        >>> from pathlib import Path
        >>> from thot.ingest.manifest import pipeline_config_sha256
        >>> with tempfile.NamedTemporaryFile("wb", delete=False) as handle:
        ...     _ = handle.write(b"pipeline")
        ...     path = Path(handle.name)
        >>> digest = pipeline_config_sha256(path)
        >>> len(digest) == 64
        True
        >>> path.unlink()
    """
    return sha256_hex(config_path.read_bytes())


def embedder_fingerprint(*, provider: str, model: str) -> str:
    """Stable digest for the configured embedding model.

    Example:
        >>> from thot.ingest.manifest import embedder_fingerprint
        >>> len(embedder_fingerprint(provider="ollama", model="bge-m3")) == 64
        True
    """
    return sha256_hex(f"{provider}:{model}")


def idempotency_key(
    doc_id: str,
    pipeline_config_sha256: str,
    embedder_sha256: str,
) -> str:
    """Compute the idempotency key for a document ingest.

    Example:
        >>> from thot.ingest.manifest import idempotency_key
        >>> key = idempotency_key("a" * 64, "b" * 64, "c" * 64)
        >>> len(key) == 64
        True
    """
    return sha256_hex(f"{doc_id}|{pipeline_config_sha256}|{embedder_sha256}")


def build_manifest(
    *,
    ingest_id: str,
    correlation_id: str,
    doc_id: str,
    source: SourceInfo,
    pipeline_sha: str,
    embedder: EmbedderInfo,
    created_at: str,
    lineage: LineageInfo | None = None,
) -> IngestManifest:
    """Create a new manifest in ``pending`` state.

    Example:
        >>> from thot.ingest.manifest import build_manifest
        >>> from thot.ingest.models import EmbedderInfo, SourceInfo
        >>> manifest = build_manifest(
        ...     ingest_id="0" * 26,
        ...     correlation_id="1" * 32,
        ...     doc_id="2" * 64,
        ...     source=SourceInfo(uri="file:///tmp/x.pdf"),
        ...     pipeline_sha="3" * 64,
        ...     embedder=EmbedderInfo(
        ...         model="bge-m3",
        ...         provider="ollama",
        ...         sha256="4" * 64,
        ...     ),
        ...     created_at="2026-01-01T00:00:00.000Z",
        ... )
        >>> manifest.status
        'pending'
    """
    return IngestManifest(
        ingest_id=ingest_id,
        correlation_id=correlation_id,
        doc_id=doc_id,
        source=source,
        pipeline_config_sha256=pipeline_sha,
        embedder=embedder,
        lineage=lineage or LineageInfo(),
        status="pending",
        created_at=created_at,
    )
