"""Title: Rag Report

Tests for RAG report assembly helpers.

Author: Eric Blaudez

Copyright (c) 2026 Thales
Licensed under the MIT License.
"""

from thot.tools.search.app import RetrievedChunk
from thot.tools.search.rag_report import (
    apply_chunk_evidence_fallback,
    assemble_report_markdown,
    build_chunk_evidence_answer,
    build_fallback_detailed_report,
    extract_highlight_labels,
    format_input_prompt,
    is_unavailable_short_answer,
    parse_structured_generation,
    query_highlight_terms,
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


def test_format_input_prompt_combines_system_and_user():
    prompt = format_input_prompt("Be concise.", "Who is Alice?")
    assert "[SYSTEM]" in prompt
    assert "Be concise." in prompt
    assert "[USER]" in prompt
    assert "Who is Alice?" in prompt


def test_assemble_report_markdown_excludes_input_prompt():
    report = assemble_report_markdown(
        query="Who is Alice?",
        language="en",
        short_answer="Alice works at Acme.",
        detailed_report="## Detailed Analysis\nAlice is mentioned.",
        chunks=[],
        ontology={"entities": [], "keywords": []},
        vespa_hits=0,
        input_prompt="[SYSTEM]\nBe concise.\n\n[USER]\nWho is Alice?",
    )
    assert "## LLM Input Prompt" not in report
    assert "[SYSTEM]" not in report
    assert "Be concise." not in report
    assert "## Question" in report
    assert "Who is Alice?" in report


def test_assemble_report_markdown_excludes_vespa_query():
    report = assemble_report_markdown(
        query="Abbey Road",
        language="en",
        short_answer="A Beatles album.",
        detailed_report="## Detailed Analysis\nAlbum details.",
        chunks=[],
        ontology={"entities": [], "keywords": []},
        vespa_hits=3,
        vespa_query='{"yql": "select * from chunk where true", "hits": 3}',
    )
    assert "## Vespa Search Query" not in report
    assert "select * from chunk where true" not in report
    assert "## Question" in report
    assert "Abbey Road" in report


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


def test_build_chunk_evidence_answer_lists_matching_documents():
    chunk = RetrievedChunk(
        chunk_id="file://tests/doc.pdf#chunk-4",
        text_raw="Awards · Charles Sutton Medal · AFL",
        parent_doc_id="file://tests/input/00948237f4a650deb4c4f101aef11882.pdf",
        relevance=3.19,
    )
    short, detailed = build_chunk_evidence_answer("Charles Sutton", [chunk])
    assert short is not None
    assert detailed is not None
    assert "00948237f4a650deb4c4f101aef11882.pdf" in short
    assert "Charles Sutton" in detailed or "Charles Sutton Medal" in detailed


def test_apply_chunk_evidence_fallback_replaces_negative_llm_answer():
    chunk = RetrievedChunk(
        chunk_id="doc.pdf#chunk-1",
        text_raw="Charles Sutton Medal",
        parent_doc_id="file://tests/doc.pdf",
    )
    short, detailed, used = apply_chunk_evidence_fallback(
        query_text="In which document appears Charles Sutton",
        short_answer=(
            "None of the provided document chunks mention Charles Sutton."
        ),
        detailed_report="Impossible to determine.",
        chunks=[chunk],
        unavailable_answer="The information is not available.",
    )
    assert used is True
    assert "doc.pdf" in short
    assert "Charles Sutton Medal" in detailed


def test_query_highlight_terms_from_user_query():
    chunk = RetrievedChunk(
        chunk_id="c1",
        text_raw="Active entities: Charles Sutton, AFLW.",
        parent_doc_id="doc",
    )
    terms = query_highlight_terms(
        "In which document appears Charles Sutton", [chunk]
    )
    assert "Charles Sutton" in terms
    assert "Charles" in terms


def test_passage_based_short_answer_prefers_predicate_sentence():
    from thot.tools.search.rag_report import _passage_based_short_answer

    chunk = RetrievedChunk(
        chunk_id="doc.pdf#chunk-2",
        text_raw=(
            "Active entities: David R. Adler, James Taylor. "
            "Topic: critic Jon Landau regards song. "
            'George Harrison liked " Something in the Way She Moves " so much '
            "that he used the beginning."
        ),
        parent_doc_id="file://tests/008363af8cc8b4678c3d72f70d76f21c.pdf",
    )
    answer = _passage_based_short_answer(
        'Who liked "Something in the Way She Moves"',
        [chunk],
    )
    assert answer == "George Harrison"


def test_passage_based_short_answer_extracts_name_when_predicate_missing():
    from thot.tools.search.rag_report import _passage_based_short_answer

    chunk = RetrievedChunk(
        chunk_id="doc.pdf#chunk-2",
        text_raw=(
            'George Harrison liked "Something in the Way She Moves" so much that '
            "he used the beginning as the first line of his 1969 song Something "
            "from the Beatles album Abbey Road."
        ),
        parent_doc_id="file://tests/008363af8cc8b4678c3d72f70d76f21c.pdf",
    )
    answer = _passage_based_short_answer(
        "Who interpret the album Abbey Road",
        [chunk],
    )
    assert answer == "George Harrison"

    metadata_chunk = (
        "Active entities: David R. Adler, James Taylor. "
        "Topic: critic Jon Landau regards song A live version was included. "
        "Inspiration for Something George Harrison liked "
        '"Something in the Way She Moves" so much that he used the beginning '
        "as the first line of his 1969 song Something from the Beatles "
        "album Abbey Road."
    )
    metadata = RetrievedChunk(
        chunk_id="doc.pdf#chunk-3",
        text_raw=metadata_chunk,
        parent_doc_id="file://tests/008363af8cc8b4678c3d72f70d76f21c.pdf",
    )
    assert (
        _passage_based_short_answer(
            "Who interpret the album Abbey Road", [metadata]
        )
        == "George Harrison"
    )


def test_extract_focus_passages_prefers_abbey_road_sentence():
    from thot.tools.search.ontology_utils import extract_focus_passages
    from thot.tools.search.vespa_client import clean_chunk_text_for_prompt

    text = (
        "Active entities: Taylor. Topic: critic regards song live version. "
        "Inspiration for Something George Harrison liked Abbey Road album."
    )
    focus = extract_focus_passages(
        [("c1", clean_chunk_text_for_prompt(text))],
        "Who interpret the album Abbey Road",
        max_passages=2,
    )
    assert "George Harrison" in focus
    assert "Topic:" not in focus


def test_parse_structured_generation_accepts_markdown_markers():
    raw = (
        "**SHORT ANSWER:**\n"
        'Claudio Miranda made "The Curious Case of Benjamin Button."\n\n'
        "**DETAILED REPORT:**\n"
        "## Filmography\n"
        "- **The Curious Case of Benjamin Button (2008)**"
    )
    short, detailed = parse_structured_generation(
        raw,
        unavailable_answer="The information is not available.",
    )
    assert (
        short == 'Claudio Miranda made "The Curious Case of Benjamin Button."'
    )
    assert "## Filmography" in detailed
    assert "**SHORT ANSWER:**" not in short


def test_build_chunk_evidence_answer_uses_passage_for_who_questions():
    chunk = RetrievedChunk(
        chunk_id="doc.pdf#chunk-2",
        text_raw=(
            'George Harrison liked " Something in the Way She Moves " so much '
            "that he used the beginning."
        ),
        parent_doc_id="file://tests/008363af8cc8b4678c3d72f70d76f21c.pdf",
        relevance=0.9,
    )
    short, detailed = build_chunk_evidence_answer(
        'Who liked "Something in the Way She Moves"',
        [chunk],
    )
    assert short is not None
    assert detailed is not None
    assert "George Harrison" in short
    assert "George Harrison" in detailed


def test_answer_supported_by_matching_chunks_keeps_llm_name_answer():
    from thot.tools.search.rag_report import (
        answer_supported_by_matching_chunks,
    )

    chunk = RetrievedChunk(
        chunk_id="c1",
        text_raw='George Harrison liked "Something in the Way She Moves".',
        parent_doc_id="file://doc.pdf",
    )
    assert answer_supported_by_matching_chunks(
        "George Harrison",
        [chunk],
        'Who liked "Something in the Way She Moves"',
    )


def test_answer_supported_rejects_who_name_with_hallucinated_details():
    from thot.tools.search.rag_report import (
        answer_supported_by_matching_chunks,
    )

    chunk = RetrievedChunk(
        chunk_id="doc.pdf#chunk-2",
        text_raw=(
            'George Harrison liked "Something in the Way She Moves" so much that '
            "he used the beginning as the first line of his 1969 song Something "
            "from the Beatles album Abbey Road."
        ),
        parent_doc_id="file://tests/008363af8cc8b4678c3d72f70d76f21c.pdf",
    )
    hallucinated = (
        'George Harrison interpreted "Something in the Way She Moves" '
        "from his solo album."
    )
    assert not answer_supported_by_matching_chunks(
        hallucinated,
        [chunk],
        "Who interpret the album Abbey Road",
    )


def test_curious_case_llm_answer_is_not_replaced_by_fallback():
    import json
    from pathlib import Path

    from thot.tools.search.app import RetrievedChunk

    obj = json.loads(
        Path(
            "tests/indexing/output/00708688ff6b5e723c0268ef52344c7f.pdf.pipeline.json"
        ).read_text()
    )
    raws: list[str] = []

    def collect(o: object) -> None:
        if isinstance(o, dict):
            text = o.get("text_raw")
            if isinstance(text, str) and len(text) > 100:
                raws.append(text)
            for value in o.values():
                collect(value)
        elif isinstance(o, list):
            for value in o:
                collect(value)

    collect(obj)
    chunks = [
        RetrievedChunk(
            chunk_id=f"c{i}",
            text_raw=text,
            parent_doc_id="file://claudio.pdf",
            relevance=10 - i,
        )
        for i, text in enumerate(raws[:6])
    ]
    query = 'Who make "The Curious Cas" ?'
    llm_short = 'Claudio Miranda made "The Curious Case of Benjamin Button."'
    llm_detailed = (
        "## Filmography\n"
        "- **The Curious Case of Benjamin Button (2008)**\n"
        "  - Directed by David Fincher\n"
        "  - Cinematographer: Claudio Miranda, ASC\n"
    )
    short, detailed, used = apply_chunk_evidence_fallback(
        query_text=query,
        short_answer=llm_short,
        detailed_report=llm_detailed,
        chunks=chunks,
        unavailable_answer="The information is not available.",
    )
    assert used is False
    assert short == llm_short
    assert "Filmography" in detailed


def test_apply_chunk_evidence_corrects_abbey_road_who_hallucination():
    chunk = RetrievedChunk(
        chunk_id="doc.pdf#chunk-2",
        text_raw=(
            'George Harrison liked "Something in the Way She Moves" so much that '
            "he used the beginning as the first line of his 1969 song Something "
            "from the Beatles album Abbey Road."
        ),
        parent_doc_id="file://tests/008363af8cc8b4678c3d72f70d76f21c.pdf",
        relevance=0.9,
    )
    hallucinated = (
        'George Harrison interpreted "Something in the Way She Moves" '
        "from his solo album."
    )
    short, _, used = apply_chunk_evidence_fallback(
        query_text="Who interpret the album Abbey Road",
        short_answer=hallucinated,
        detailed_report="Wrong analysis.",
        chunks=[chunk],
        unavailable_answer="The information is not available.",
    )
    assert used is True
    assert short.startswith("George Harrison")


def test_apply_chunk_evidence_fallback_skips_supported_llm_answer():
    chunk = RetrievedChunk(
        chunk_id="c1",
        text_raw='George Harrison liked "Something in the Way She Moves".',
        parent_doc_id="file://doc.pdf",
    )
    short, detailed, used = apply_chunk_evidence_fallback(
        query_text='Who liked "Something in the Way She Moves"',
        short_answer="George Harrison",
        detailed_report="He liked the song.",
        chunks=[chunk],
        unavailable_answer="The information is not available.",
    )
    assert used is False
    assert short == "George Harrison"
    assert is_unavailable_short_answer(
        "The information is not available.",
        "The information is not available.",
    )
    assert not is_unavailable_short_answer(
        "Found in doc.pdf",
        "The information is not available.",
    )
