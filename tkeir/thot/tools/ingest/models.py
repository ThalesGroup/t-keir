"""Title: Models

Pydantic models for ingest jobs, manifests, and API payloads.

Author: Eric Blaudez

Copyright (c) 2026 Thales
Licensed under the MIT License.
"""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, HttpUrl

MANIFEST_SCHEMA_ID = "tkeir.ingest.manifest.v1"


class IngestJobStatus(str, Enum):
    """Lifecycle states for an ingest job."""

    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    NOOP = "noop"
    FAILED = "failed"


class SourceInfo(BaseModel):
    """Provenance for ingested bytes."""

    uri: str
    filename: str | None = None
    content_type: str | None = None
    size_bytes: int | None = None


class EmbedderInfo(BaseModel):
    """Embedding model fingerprint used for idempotency."""

    model: str
    provider: str
    sha256: str


class LineageInfo(BaseModel):
    """Optional lineage links between ingest operations."""

    parent_ingest_id: str | None = None
    supersedes: str | None = None
    batch_id: str | None = None


class IngestManifest(BaseModel):
    """On-disk contract written under ``staging/{doc_id}/ingest.manifest.json``."""

    schema_id: str = Field(
        default=MANIFEST_SCHEMA_ID,
        alias="schema",
    )
    ingest_id: str
    correlation_id: str
    doc_id: str
    source: SourceInfo
    pipeline_config_sha256: str
    embedder: EmbedderInfo
    lineage: LineageInfo = Field(default_factory=LineageInfo)
    status: str = "pending"
    chunk_count: int = 0
    indexed_at: str | None = None
    created_at: str
    error: str | None = None
    # Publication provenance (Phase E) — agent-generated docs carry these.
    origin: str | None = None
    run_id: str | None = None

    model_config = {"populate_by_name": True}

    def to_storage_dict(self) -> dict[str, Any]:
        """Serialize using JSON schema field names.

        Example:
            >>> manifest = IngestManifest(
            ...     ingest_id="0" * 26,
            ...     correlation_id="a" * 32,
            ...     doc_id="b" * 64,
            ...     source=SourceInfo(uri="file:///tmp/x.pdf"),
            ...     pipeline_config_sha256="c" * 64,
            ...     embedder=EmbedderInfo(
            ...         model="bge-m3",
            ...         provider="ollama",
            ...         sha256="d" * 64,
            ...     ),
            ...     created_at="2026-01-01T00:00:00.000Z",
            ... )
            >>> manifest.to_storage_dict()["schema"]
            'tkeir.ingest.manifest.v1'
        """
        return self.model_dump(by_alias=True, exclude_none=True)


class IngestJob(BaseModel):
    """Runtime job record tracked under ``jobs/{ingest_id}.json``."""

    ingest_id: str
    correlation_id: str
    status: IngestJobStatus = IngestJobStatus.PENDING
    doc_id: str | None = None
    batch_id: str | None = None
    manifest_path: str | None = None
    error: str | None = None
    created_at: str
    updated_at: str
    noop: bool = False
    # Vespa streaming group (Keycloak principal / dev@tkeir)
    user_space: str | None = None


class OntologyUpload(BaseModel):
    """Client-uploaded ontology content (server never reads client paths)."""

    filename: str = "ontology.ttl"
    content_base64: str = Field(
        ...,
        description="Base64-encoded OWL/TTL/RDF bytes",
    )


class DocumentIngestRequest(BaseModel):
    """JSON body for ``POST /ingest/document`` when not uploading multipart."""

    url: HttpUrl | str
    filename: str | None = None
    metadata: dict[str, Any] | None = None
    # Ontology *content* only — not filesystem paths on the server.
    ontologies: list[OntologyUpload] | None = None


class BatchItem(BaseModel):
    """One document reference inside a batch manifest."""

    url: HttpUrl | str
    filename: str | None = None
    metadata: dict[str, Any] | None = None
    ontologies: list[OntologyUpload] | None = None


class BatchIngestRequest(BaseModel):
    """Body for ``POST /ingest/batch``."""

    items: list[BatchItem] = Field(min_length=1)


class IngestAcceptedResponse(BaseModel):
    """202 response when a job is queued."""

    ingest_id: str
    correlation_id: str
    status: IngestJobStatus
    doc_id: str | None = None
    noop: bool = False


class BatchAcceptedResponse(BaseModel):
    """202 response for a batch submission."""

    batch_id: str
    correlation_id: str
    jobs: list[IngestAcceptedResponse]


class JsonRecordsIngestRequest(BaseModel):
    """Options for ``POST /ingest/json-records`` (multipart or JSON path)."""

    split_records: bool = True
    index_target: str = Field(
        default="global",
        description="Vespa target: global | user | both",
    )
    offset: int = Field(default=0, ge=0)
    limit: int | None = Field(
        default=None,
        ge=1,
        description="Max records to queue (None = all)",
    )
    # Server-side dataset path relative to repo / TKEIR_WORKSPACE (admin demos).
    dataset_path: str | None = None
    filename: str | None = None


class JsonRecordsAcceptedResponse(BaseModel):
    """202 response after splitting a JSON corpus into per-record jobs."""

    batch_id: str
    correlation_id: str
    record_count: int
    queued: int
    index_target: str
    source_basename: str
    jobs: list[IngestAcceptedResponse]


class IngestStatusResponse(BaseModel):
    """``GET /ingest/status/{id}`` payload."""

    ingest_id: str
    correlation_id: str
    status: IngestJobStatus
    doc_id: str | None = None
    batch_id: str | None = None
    manifest_path: str | None = None
    error: str | None = None
    noop: bool = False
    manifest: IngestManifest | None = None
