"""Title: OKF v0.1 Pydantic models (T-KEIR producer extensions).

Example:
    >>> from thot.okf.models import OkfConceptFrontmatter
    >>> fm = OkfConceptFrontmatter(
    ...     type="Document",
    ...     tkeir_doc_id="doc-1",
    ...     tkeir_user_space="dev@tkeir",
    ... )
    >>> fm.tkeir_okf_version
    '0.1'

Author: Eric Blaudez

Copyright (c) 2026 Thales
Licensed under the MIT License.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class OkfConceptFrontmatter(BaseModel):
    """YAML frontmatter for one OKF concept file."""

    type: str
    title: str | None = None
    description: str | None = None
    resource: str | None = None
    tags: list[str] = Field(default_factory=list)
    timestamp: datetime | None = None
    tkeir_doc_id: str
    tkeir_user_space: str
    tkeir_chunk_ids: list[str] = Field(default_factory=list)
    tkeir_pipeline_sha: str | None = None
    tkeir_okf_version: str = "0.1"


class OkfConcept(BaseModel):
    """One concept: frontmatter + Markdown body + bundle-relative id."""

    frontmatter: OkfConceptFrontmatter
    body: str
    concept_id: str


class OkfBundle(BaseModel):
    """Metadata for a written OKF bundle directory."""

    bundle_id: str
    user_space: str
    query: str | None = None
    concept_count: int
    created_at: datetime = Field(default_factory=_utc_now)
    path: str


class OkfExportRequest(BaseModel):
    """Inbound export request (CLI / HTTP / orchestrator builtin)."""

    user_space: str
    query: str | None = None
    max_docs: int = 200
    output_dir: str | None = None
    doc_ids: list[str] | None = None


class OkfHttpExportBody(BaseModel):
    """HTTP body for ``POST /okf/export`` — never carries access-control space."""

    query: str | None = None
    max_docs: int = 200
    output_dir: str | None = None


class OkfPublishWikiBody(BaseModel):
    """HTTP body for ``POST /okf/bundles/{id}/publish-wiki``."""

    path: str | None = None
    """Optional workspace-relative path (default ``wiki/<slug>.md``)."""

    markdown: str | None = None
    """Optional edited wiki markdown; when set, saved to the bundle before publish."""


class OkfWikiUpdateBody(BaseModel):
    """HTTP body for ``PUT /okf/bundles/{id}/wiki``."""

    markdown: str
    """Full ``wiki.md`` contents (YAML frontmatter + Markdown body)."""


class OkfExportResult(BaseModel):
    """Result of a full or scoped export."""

    bundle: OkfBundle
    unfilled_docs: list[str] = Field(default_factory=list)
    action_record_id: str


class OkfEnrichmentBody(BaseModel):
    """Optional body sections produced by ``okf_curator``."""

    Summary: str | None = None
    Key_Entities: str | None = Field(default=None, alias="Key Entities")
    Relations: str | None = None

    model_config = {"populate_by_name": True, "extra": "allow"}


class OkfEnrichmentPayload(BaseModel):
    """Enrichment fields applied to an existing concept file."""

    description: str | None = None
    tags: list[str] = Field(default_factory=list)
    body_sections: dict[str, str] = Field(default_factory=dict)


class OkfEnrichmentFinding(BaseModel):
    """One grounded enrichment finding (``okf_enrichment_v1``)."""

    concept_id: str
    enrichments: OkfEnrichmentPayload = Field(
        default_factory=OkfEnrichmentPayload
    )
    chunk_ids: list[str] = Field(default_factory=list)
    document_ids: list[str] = Field(default_factory=list)
    confidence: float = 0.0
    claim: str = ""


class OkfEnrichment(BaseModel):
    """Curator output contract."""

    schema_: str = Field(default="okf_enrichment_v1", alias="schema")
    findings: list[OkfEnrichmentFinding] = Field(default_factory=list)
    unfilled: list[str] = Field(default_factory=list)
    notes: str = ""

    model_config = {"populate_by_name": True}


class OkfBundleMeta(BaseModel):
    """On-disk metadata sidecar (``.tkeir-meta.json``)."""

    bundle: OkfBundle
    extra: dict[str, Any] = Field(default_factory=dict)
