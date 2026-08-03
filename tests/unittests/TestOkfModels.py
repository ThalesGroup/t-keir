"""Title: Unit tests for OKF Pydantic models.

Author: Eric Blaudez

Copyright (c) 2026 Thales
Licensed under the MIT License.
"""

from __future__ import annotations

from datetime import datetime, timezone

from thot.okf.models import (
    OkfBundle,
    OkfConcept,
    OkfConceptFrontmatter,
    OkfEnrichment,
    OkfExportRequest,
    OkfExportResult,
)


def test_frontmatter_round_trip():
    fm = OkfConceptFrontmatter(
        type="Document",
        title="Alpha",
        description="First sentence.",
        tags=["a", "b"],
        timestamp=datetime(2026, 7, 23, tzinfo=timezone.utc),
        tkeir_doc_id="doc-1",
        tkeir_user_space="dev@tkeir",
        tkeir_chunk_ids=["c1"],
        tkeir_pipeline_sha="abc",
    )
    data = fm.model_dump(mode="json")
    again = OkfConceptFrontmatter.model_validate(data)
    assert again.type == "Document"
    assert again.tkeir_okf_version == "0.2"
    assert again.tkeir_chunk_ids == ["c1"]


def test_concept_and_bundle():
    fm = OkfConceptFrontmatter(
        type="Document",
        tkeir_doc_id="doc-1",
        tkeir_user_space="dev@tkeir",
    )
    concept = OkfConcept(
        frontmatter=fm, body="# Title\n", concept_id="concepts/doc-1"
    )
    assert concept.concept_id == "concepts/doc-1"
    bundle = OkfBundle(
        bundle_id="b1",
        user_space="dev@tkeir",
        concept_count=1,
        path="/tmp/b1",
    )
    result = OkfExportResult(bundle=bundle, action_record_id="act1")
    assert result.bundle.bundle_id == "b1"
    req = OkfExportRequest(user_space="dev@tkeir", query="hello", max_docs=5)
    assert req.query == "hello"


def test_okf_enrichment_contract():
    payload = {
        "schema": "okf_enrichment_v1",
        "findings": [
            {
                "concept_id": "concepts/doc-1",
                "claim": "Alpha is a project.",
                "chunk_ids": ["c1"],
                "enrichments": {
                    "description": "Alpha is a project.",
                    "tags": ["alpha"],
                    "body_sections": {"Summary": "Grounded summary."},
                },
            }
        ],
        "unfilled": [],
        "notes": "",
    }
    enrichment = OkfEnrichment.model_validate(payload)
    assert enrichment.schema_ == "okf_enrichment_v1"
    assert enrichment.findings[0].enrichments.tags == ["alpha"]
