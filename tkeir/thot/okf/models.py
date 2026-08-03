"""Title: OKF v0.2 Pydantic models (Google SPEC + T-KEIR extensions).

Conforms to the Open Knowledge Format frontmatter families in
``docs/okf/SPEC.md`` (vendored from GoogleCloudPlatform/knowledge-catalog).
T-KEIR adds optional ``tkeir_*`` producer keys that conformant consumers ignore.

Author: Eric Blaudez

Copyright (c) 2026 Thales
Licensed under the MIT License.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field


def _utc_now() -> datetime:
    """Return a timezone-aware UTC timestamp.

    Returns:
        Current UTC datetime.

    Example:
        >>> from thot.okf.models import _utc_now
        >>> _utc_now().tzinfo is not None
        True
    """
    return datetime.now(timezone.utc)


class OkfActorEvent(BaseModel):
    """One ``generated`` / ``verified`` event (SPEC §5.2 / §7).

    Example:
        >>> from thot.okf.models import OkfActorEvent
        >>> OkfActorEvent(by="process:tkeir-okf-export").by
        'process:tkeir-okf-export'
    """

    by: str
    at: datetime | None = None


class OkfSourceEntry(BaseModel):
    """One ``sources`` entry (SPEC §5.1). ``resource`` is required per entry.

    Example:
        >>> from thot.okf.models import OkfSourceEntry
        >>> OkfSourceEntry(resource="vespa://dev@tkeir/doc-1", id="doc-1").id
        'doc-1'
    """

    resource: str
    id: str | None = None
    title: str | None = None
    author: str | None = None
    usage_count: int | None = None
    last_modified: str | None = None


class OkfConceptFrontmatter(BaseModel):
    """YAML frontmatter for one OKF concept file (SPEC §4.1 + T-KEIR keys).

    Example:
        >>> from thot.okf.models import OkfConceptFrontmatter
        >>> fm = OkfConceptFrontmatter(
        ...     type="Document",
        ...     tkeir_doc_id="doc-1",
        ...     tkeir_user_space="dev@tkeir",
        ... )
        >>> fm.tkeir_okf_version
        '0.2'
    """

    type: str
    title: str | None = None
    description: str | None = None
    resource: str | None = None
    tags: list[str] = Field(default_factory=list)
    timestamp: datetime | None = None
    # SPEC §5 provenance / trust / lifecycle (all optional)
    sources: list[OkfSourceEntry] = Field(default_factory=list)
    generated: OkfActorEvent | None = None
    verified: list[OkfActorEvent] | OkfActorEvent | None = None
    status: str | None = None
    stale_after: str | None = None
    # T-KEIR producer extensions
    tkeir_doc_id: str
    tkeir_user_space: str
    tkeir_chunk_ids: list[str] = Field(default_factory=list)
    tkeir_pipeline_sha: str | None = None
    tkeir_okf_version: str = "0.2"


class OkfConcept(BaseModel):
    """One concept: frontmatter + Markdown body + bundle-relative id.

    Example:
        >>> from thot.okf.models import OkfConcept, OkfConceptFrontmatter
        >>> c = OkfConcept(
        ...     frontmatter=OkfConceptFrontmatter(
        ...         type="Chunk",
        ...         tkeir_doc_id="d",
        ...         tkeir_user_space="dev@tkeir",
        ...     ),
        ...     body="# Hi\\n",
        ...     concept_id="chunks/c1",
        ... )
        >>> c.concept_id
        'chunks/c1'
    """

    frontmatter: OkfConceptFrontmatter
    body: str
    concept_id: str


class OkfBundle(BaseModel):
    """Metadata for a written OKF bundle directory.

    Example:
        >>> from thot.okf.models import OkfBundle
        >>> OkfBundle(
        ...     bundle_id="b1",
        ...     user_space="dev@tkeir",
        ...     concept_count=1,
        ...     path="/tmp/b1",
        ... ).concept_count
        1
    """

    bundle_id: str
    user_space: str
    query: str | None = None
    concept_count: int
    created_at: datetime = Field(default_factory=_utc_now)
    path: str


class OkfExportRequest(BaseModel):
    """Inbound export request (CLI / HTTP / orchestrator builtin).

    Example:
        >>> from thot.okf.models import OkfExportRequest
        >>> OkfExportRequest(user_space="dev@tkeir").max_docs
        200
    """

    user_space: str
    query: str | None = None
    max_docs: int = 200
    output_dir: str | None = None
    doc_ids: list[str] | None = None


class OkfHttpExportBody(BaseModel):
    """HTTP body for ``POST /okf/export`` — never carries access-control space.

    Example:
        >>> from thot.okf.models import OkfHttpExportBody
        >>> OkfHttpExportBody(query="Atlas").query
        'Atlas'
    """

    query: str | None = None
    max_docs: int = 200
    output_dir: str | None = None


class OkfPublishWikiBody(BaseModel):
    """HTTP body for ``POST /okf/bundles/{id}/publish-wiki``.

    Example:
        >>> from thot.okf.models import OkfPublishWikiBody
        >>> OkfPublishWikiBody(path="wiki/x.md").path
        'wiki/x.md'
    """

    path: str | None = None
    """Optional workspace-relative path (default ``wiki/<slug>.md``)."""

    markdown: str | None = None
    """Optional edited wiki markdown; when set, saved to the bundle before publish."""


class OkfWikiUpdateBody(BaseModel):
    """HTTP body for ``PUT /okf/bundles/{id}/wiki``.

    Example:
        >>> from thot.okf.models import OkfWikiUpdateBody
        >>> OkfWikiUpdateBody(markdown="---\\ntype: Wiki\\n---\\n").markdown.startswith("---")
        True
    """

    markdown: str
    """Full ``wiki.md`` contents (YAML frontmatter + Markdown body)."""


class OkfExportResult(BaseModel):
    """Result of a full or scoped export.

    Example:
        >>> from thot.okf.models import OkfBundle, OkfExportResult
        >>> OkfExportResult(
        ...     bundle=OkfBundle(
        ...         bundle_id="b",
        ...         user_space="dev@tkeir",
        ...         concept_count=0,
        ...         path="/tmp",
        ...     ),
        ...     action_record_id="a1",
        ... ).action_record_id
        'a1'
    """

    bundle: OkfBundle
    unfilled_docs: list[str] = Field(default_factory=list)
    action_record_id: str


class OkfEnrichmentBody(BaseModel):
    """Optional body sections produced by ``okf_curator``.

    Example:
        >>> from thot.okf.models import OkfEnrichmentBody
        >>> OkfEnrichmentBody(Summary="x").Summary
        'x'
    """

    Summary: str | None = None
    Key_Entities: str | None = Field(default=None, alias="Key Entities")
    Relations: str | None = None

    model_config = {"populate_by_name": True, "extra": "allow"}


class OkfEnrichmentPayload(BaseModel):
    """Enrichment fields applied to an existing concept file.

    Example:
        >>> from thot.okf.models import OkfEnrichmentPayload
        >>> OkfEnrichmentPayload(tags=["a"]).tags
        ['a']
    """

    description: str | None = None
    tags: list[str] = Field(default_factory=list)
    body_sections: dict[str, str] = Field(default_factory=dict)


class OkfEnrichmentFinding(BaseModel):
    """One grounded enrichment finding (``okf_enrichment_v1``).

    Example:
        >>> from thot.okf.models import OkfEnrichmentFinding
        >>> OkfEnrichmentFinding(concept_id="concepts/d").concept_id
        'concepts/d'
    """

    concept_id: str
    enrichments: OkfEnrichmentPayload = Field(
        default_factory=OkfEnrichmentPayload
    )
    chunk_ids: list[str] = Field(default_factory=list)
    document_ids: list[str] = Field(default_factory=list)
    confidence: float = 0.0
    claim: str = ""


class OkfEnrichment(BaseModel):
    """Curator output contract.

    Example:
        >>> from thot.okf.models import OkfEnrichment
        >>> OkfEnrichment().schema_
        'okf_enrichment_v1'
    """

    schema_: str = Field(default="okf_enrichment_v1", alias="schema")
    findings: list[OkfEnrichmentFinding] = Field(default_factory=list)
    unfilled: list[str] = Field(default_factory=list)
    notes: str = ""

    model_config = {"populate_by_name": True}


class OkfBundleMeta(BaseModel):
    """On-disk metadata sidecar (``.tkeir-meta.json``).

    Example:
        >>> from thot.okf.models import OkfBundle, OkfBundleMeta
        >>> OkfBundleMeta(
        ...     bundle=OkfBundle(
        ...         bundle_id="b",
        ...         user_space="dev@tkeir",
        ...         concept_count=0,
        ...         path="/tmp",
        ...     )
        ... ).extra
        {}
    """

    bundle: OkfBundle
    extra: dict[str, Any] = Field(default_factory=dict)
