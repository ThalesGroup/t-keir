# -*- coding: utf-8 -*-
"""Tests for RAG report assembly helpers."""

from thot.tools.search.app import RetrievedChunk
from thot.tools.search.rag_report import (
    assemble_report_markdown,
    build_fallback_detailed_report,
    extract_highlight_labels,
    parse_structured_generation,
)


def test_parse_structured_generation_splits_sections():
    raw = (
        "SHORT_ANSWER:\n"
        "Theodore Kopfre reported the trend.\n\n"
        "DETAILED_REPORT:\n"
        "## Detailed Analysis\n"
        "National Review commentator Theodore Kopfre reported Yang replaced Trump."
    )
    short, detailed = parse_structured_generation(
        raw,
        unavailable_answer="The information is not available.",
    )
    assert short == "Theodore Kopfre reported the trend."
    assert "National Review commentator" in detailed


def test_extract_highlight_labels_ranks_by_chunk_links():
    ontology = {
        "entities": [
            {"label": "Acme", "type": "Company", "chunk_ids": ["c1", "c2"]},
            {"label": "Bob", "type": "Person", "chunk_ids": ["c1"]},
        ],
        "keywords": [
            {"label": "launch", "chunk_ids": ["c1", "c2", "c3"]},
            {"label": "widget", "chunk_ids": ["c1"]},
        ],
    }
    entities, keywords = extract_highlight_labels(
        ontology, max_entities=5, max_keywords=5
    )
    assert entities[0] == "Acme"
    assert keywords[0] == "launch"


def test_assemble_report_markdown_includes_sources_and_entities():
    chunk = RetrievedChunk(
        chunk_id="doc.pdf#chunk-1",
        text_raw="Andrew Yang replaced Donald Trump as the meme candidate.",
        parent_doc_id="file://tests/input/doc.pdf",
        relevance=0.91,
    )
    report = assemble_report_markdown(
        query="Who reported Yang replaced Trump?",
        language="en",
        short_answer="Theodore Kopfre.",
        detailed_report="## Detailed Analysis\n\nKopfre reported the trend.",
        chunks=[chunk],
        ontology={
            "entities": [
                {
                    "label": "Andrew Yang",
                    "type": "Person",
                    "chunk_ids": ["doc.pdf#chunk-1"],
                }
            ],
            "keywords": [
                {"label": "meme candidate", "chunk_ids": ["doc.pdf#chunk-1"]}
            ],
        },
        vespa_hits=1,
    )
    assert "# T-KEIR RAG Report" in report
    assert "## Short Answer" in report
    assert "Theodore Kopfre." in report
    assert "## Key Entities" in report
    assert "Andrew Yang" in report
    assert "## Retrieved Sources" in report
    assert "doc.pdf#chunk-1" in report


def test_build_fallback_detailed_report_uses_passages():
    report = build_fallback_detailed_report(
        focus_passages="- [c1] Relevant sentence.",
        chunk_excerpts="---\nChunk body\n---",
    )
    assert "Focus Passages" in report
    assert "Relevant sentence." in report
