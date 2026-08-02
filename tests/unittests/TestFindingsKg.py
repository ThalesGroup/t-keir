"""Title: Findings → compose KG unit tests

Author: Eric Blaudez

Copyright (c) 2026 Thales
Licensed under the MIT License.
"""

from thot.agent.models import GroundedFinding, GroundedFindings
from thot.compose.findings_kg import (
    findings_prose_context,
    turtles_from_grounded_findings,
)
from thot.compose.kg import UserSpaceKG


def test_turtles_from_findings_ground_real_chunks() -> None:
    findings = GroundedFindings(
        goal="Generate report about Gulfs",
        findings=[
            GroundedFinding(
                claim="The Persian Gulf is a critical maritime corridor.",
                chunk_ids=["osint-gulf-1"],
                document_ids=["doc-gulf"],
                confidence=0.9,
            ),
            GroundedFinding(
                claim="Suez approaches show STS transfers.",
                chunk_ids=["osint-suez-2"],
                document_ids=["doc-suez"],
                confidence=0.8,
            ),
        ],
    )
    turtles, docs = turtles_from_grounded_findings(findings)
    assert turtles
    joined = "\n".join(turtles)
    assert "Persian Gulf" in joined
    assert "osint-gulf-1" in joined
    assert "doc.pdf" not in joined
    assert "Acme" not in joined
    assert "doc-gulf" in docs

    kg = UserSpaceKG("test-findings", use_process_cache=False)
    kg.load(turtles, document_ids=docs)
    prose, chunks, _ = findings_prose_context(findings)
    assert "Persian Gulf" in prose
    assert "osint-gulf-1" in chunks
