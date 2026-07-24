"""Title: Unit tests for OKF enrichment applicator.

Author: Eric Blaudez

Copyright (c) 2026 Thales
Licensed under the MIT License.
"""

from __future__ import annotations

from pathlib import Path

from thot.agent.models import GroundedFinding, GroundedFindings
from thot.okf.applicator import (
    OkfEnrichmentApplicator,
    enrichments_from_grounded,
    parse_concept_file,
)
from thot.okf.exporter import render_frontmatter
from thot.okf.models import (
    OkfConceptFrontmatter,
    OkfEnrichment,
    OkfEnrichmentFinding,
    OkfEnrichmentPayload,
)


def _write_concept(root: Path) -> Path:
    path = root / "concepts" / "doc-1.md"
    path.parent.mkdir(parents=True)
    fm = OkfConceptFrontmatter(
        type="Document",
        title="Doc",
        description="Old.",
        tags=["old"],
        tkeir_doc_id="doc-1",
        tkeir_user_space="dev@tkeir",
        tkeir_chunk_ids=["c1"],
        tkeir_pipeline_sha="deadbeef",
    )
    body = "# Doc\n\n## Entities\n\n_none_\n"
    path.write_text(render_frontmatter(fm) + "\n" + body, encoding="utf-8")
    return path


def test_applicator_updates_description_and_preserves_tkeir(tmp_path: Path):
    path = _write_concept(tmp_path)
    enrichment = OkfEnrichment(
        findings=[
            OkfEnrichmentFinding(
                concept_id="concepts/doc-1",
                claim="New description.",
                chunk_ids=["c1"],
                enrichments=OkfEnrichmentPayload(
                    description="New description.",
                    tags=["new"],
                    body_sections={"Summary": "Curated summary."},
                ),
            )
        ]
    )
    summary = OkfEnrichmentApplicator(tmp_path).apply(enrichment)
    assert summary["applied"] == 1
    text = path.read_text(encoding="utf-8")
    fm, body = parse_concept_file(text)
    assert fm["description"] == "New description."
    assert fm["tkeir_pipeline_sha"] == "deadbeef"
    assert fm["tkeir_doc_id"] == "doc-1"
    assert "new" in fm["tags"]
    assert "Curated summary." in body
    assert "## Curator enrichments" in body


def test_enrichments_from_notes_json():
    notes = (
        '{"schema":"okf_enrichment_v1","findings":['
        '{"concept_id":"concepts/doc-1","chunk_ids":["c1"],'
        '"enrichments":{"description":"From notes","tags":[],'
        '"body_sections":{}}}],"unfilled":[]}'
    )
    result = GroundedFindings(
        findings=[
            GroundedFinding(
                claim="From notes", chunk_ids=["c1"], document_ids=["okf:concepts/doc-1"]
            )
        ],
        notes=notes,
    )
    enrichment = enrichments_from_grounded(result)
    assert enrichment.findings[0].concept_id == "concepts/doc-1"
    assert enrichment.findings[0].enrichments.description == "From notes"
