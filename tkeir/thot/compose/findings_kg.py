"""Title: Build compose KG from grounded agent findings

Convert researcher/analyst ``GroundedFindings`` into Turtle so
``thot.compose`` fills templates from real run evidence — never demo
fixtures.

Author: Eric Blaudez

Copyright (c) 2026 Thales
Licensed under the MIT License.
"""

from __future__ import annotations

import re
from typing import Any

from thot.agent.models import GroundedFinding, GroundedFindings


def _iri_safe(token: str) -> str:
    text = re.sub(r"[^a-zA-Z0-9_\-]+", "_", str(token or "").strip())
    return text.strip("_") or "item"


def _turtle_escape(text: str) -> str:
    return (
        str(text or "")
        .replace("\\", "\\\\")
        .replace('"', '\\"')
        .replace("\n", " ")
        .replace("\r", " ")
    )


def turtles_from_grounded_findings(
    findings: GroundedFindings | list[GroundedFinding] | None,
    *,
    goal: str = "",
) -> tuple[list[str], list[str]]:
    """Serialize grounded findings as Turtle for ``UserSpaceKG.load``.

    Returns:
        ``(turtles, document_ids)`` — empty turtles when there is no evidence.
    """
    if findings is None:
        return [], []
    rows: list[GroundedFinding]
    if isinstance(findings, GroundedFindings):
        rows = list(findings.findings or [])
        goal = goal or findings.goal
    else:
        rows = list(findings)

    if not rows:
        return [], []

    lines = [
        "@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .",
        "@prefix tkeir: <http://tkeir.local/ontology/> .",
        "@prefix find: <http://tkeir.local/finding/> .",
        "@prefix chunk: <http://tkeir.local/chunk/> .",
        "@prefix doc: <http://tkeir.local/doc/> .",
        "",
    ]
    document_ids: list[str] = []
    seen_chunks: set[str] = set()
    seen_docs: set[str] = set()
    keyword_labels: list[str] = []

    if goal.strip():
        lines.append(
            f'find:goal a tkeir:Finding ; rdfs:label "{_turtle_escape(goal.strip())}" .'
        )
        lines.append("")

    for index, finding in enumerate(rows):
        claim = str(finding.claim or "").strip()
        if not claim:
            continue
        fid = f"find:f{index}"
        lines.append(f"{fid} a tkeir:Finding ;")
        lines.append(f'    rdfs:label "{_turtle_escape(claim)}" .')
        for chunk_id in finding.chunk_ids or []:
            cid = str(chunk_id).strip()
            if not cid:
                continue
            chunk_iri = f"chunk:{_iri_safe(cid)}"
            if cid not in seen_chunks:
                seen_chunks.add(cid)
                lines.append(f"{chunk_iri} a tkeir:DocumentChunk ;")
                lines.append(f'    rdfs:label "{_turtle_escape(cid)}" .')
            lines.append(f"{chunk_iri} tkeir:hasStatement {fid} ;")
            lines.append(f"    tkeir:hasMention {fid} .")
        for doc_id in finding.document_ids or []:
            did = str(doc_id).strip()
            if not did:
                continue
            document_ids.append(did)
            doc_iri = f"doc:{_iri_safe(did)}"
            if did not in seen_docs:
                seen_docs.add(did)
                lines.append(f"{doc_iri} a tkeir:Document ;")
                lines.append(f'    rdfs:label "{_turtle_escape(did)}" .')
            lines.append(f"{doc_iri} tkeir:hasMention {fid} .")
            for chunk_id in finding.chunk_ids or []:
                cid = str(chunk_id).strip()
                if cid:
                    lines.append(
                        f"doc:{_iri_safe(did)} tkeir:hasChunk chunk:{_iri_safe(cid)} ."
                    )
        # Lightweight keywords from claim tokens (for keyword slots).
        for token in re.findall(r"[A-Za-z][A-Za-z\- ]{2,40}", claim):
            cleaned = " ".join(token.split())
            if len(cleaned) < 4:
                continue
            if cleaned.casefold() in {
                "the",
                "and",
                "for",
                "with",
                "from",
                "that",
                "this",
                "report",
                "generate",
            }:
                continue
            keyword_labels.append(cleaned)
        lines.append("")

    for index, label in enumerate(list(dict.fromkeys(keyword_labels))[:12]):
        kid = f"find:kw{index}"
        lines.append(f"{kid} a tkeir:Keyword ;")
        lines.append(f'    rdfs:label "{_turtle_escape(label)}" .')
        if document_ids:
            lines.append(
                f"doc:{_iri_safe(document_ids[0])} tkeir:hasKeyword {kid} ."
            )
        elif seen_chunks:
            first_chunk = next(iter(seen_chunks))
            lines.append(
                f"chunk:{_iri_safe(first_chunk)} tkeir:hasMention {kid} ."
            )

    turtle = "\n".join(lines).strip() + "\n"
    return [turtle], sorted(set(document_ids))


def findings_prose_context(
    findings: GroundedFindings | list[GroundedFinding] | None,
) -> tuple[str, list[str], list[str]]:
    """Bullet context + evidence ids for freeform compose slots."""
    if findings is None:
        return "", [], []
    rows: list[GroundedFinding]
    if isinstance(findings, GroundedFindings):
        rows = list(findings.findings or [])
    else:
        rows = list(findings)
    lines: list[str] = []
    chunks: list[str] = []
    docs: list[str] = []
    for finding in rows:
        claim = str(finding.claim or "").strip()
        if not claim:
            continue
        cite = ", ".join(finding.chunk_ids or []) or "ungrounded"
        lines.append(f"- {claim} [{cite}]")
        chunks.extend(str(c) for c in finding.chunk_ids or [] if c)
        docs.extend(str(d) for d in finding.document_ids or [] if d)
    return (
        "\n".join(lines),
        sorted(set(chunks)),
        sorted(set(docs)),
    )


def ontology_payloads_from_observations(
    observations: list[dict[str, Any]] | None,
) -> list[str]:
    """Extract JSON-LD / Turtle ontology payloads from tool observations."""
    payloads: list[str] = []
    for obs in observations or []:
        if not isinstance(obs, dict):
            continue
        candidates: list[Any] = [
            obs.get("json_ld"),
            obs.get("ontology_json_ld"),
        ]
        ontology = obs.get("ontology")
        if isinstance(ontology, dict):
            candidates.append(ontology.get("json_ld"))
        elif isinstance(ontology, str):
            candidates.append(ontology)
        result = obs.get("result")
        if isinstance(result, dict):
            candidates.append(result.get("json_ld"))
            nested = result.get("ontology")
            if isinstance(nested, dict):
                candidates.append(nested.get("json_ld"))
        for raw in candidates:
            text = str(raw or "").strip()
            if text and text not in {"[]", "{}"}:
                payloads.append(text)
    return payloads
