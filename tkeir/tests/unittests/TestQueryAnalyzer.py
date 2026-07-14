# -*- coding: utf-8 -*-
"""Tests for QueryAnalyzerTask and Vespa payload generation."""

from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import AsyncMock

from thot.tools.search.query_analyzer import (
    NerEntity,
    QueryAnalysis,
    QueryAnalyzerTask,
    SvoTriple,
    analyze_query_document,
    build_hybrid_yql,
    build_search_terms,
    build_vespa_search_payload,
    extract_keyword_terms,
    extract_ner_entities,
    extract_svo_triples,
)
from thot.tools.search.rag_config import RagSearchConfig
from thot.tools.search.vespa_client import (
    build_field_contains_or_clause,
    build_multi_field_contains_or_clause,
)

MICROSOFT_PIPELINE_OUTPUT = {
    "content_morphosyntax": [
        {"text": "What", "lemma": "what", "pos": "PRON"},
        {"text": "did", "lemma": "do", "pos": "AUX"},
        {"text": "Microsoft", "lemma": "Microsoft", "pos": "PROPN"},
        {"text": "acquire", "lemma": "acquire", "pos": "VERB"},
        {"text": "in", "lemma": "in", "pos": "ADP"},
        {"text": "2026", "lemma": "2026", "pos": "NUM"},
        {"text": "?", "lemma": "?", "pos": "PUNCT"},
    ],
    "content_ner": [
        {"text": "Microsoft", "label": "organization", "start": 2, "end": 3},
        {"text": "2026", "label": "date", "start": 5, "end": 6},
    ],
    "kg": [
        {
            "subject": {"content": "Microsoft"},
            "property": {"content": "acquire"},
            "value": {"content": ""},
        }
    ],
    "keywords": [
        {"text": "microsoft acquisition", "score": 12},
        {"text": "2026", "score": 4},
    ],
}


class _FakeRunner:
    def run(self, document: dict[str, Any], **kwargs: Any) -> dict[str, Any]:
        return dict(MICROSOFT_PIPELINE_OUTPUT)


def test_extract_ner_entities_deduplicates():
    entities = extract_ner_entities(
        [
            {"text": "Microsoft", "label": "organization"},
            {"text": "Microsoft", "label": "organization"},
        ]
    )
    assert len(entities) == 1
    assert entities[0].text == "Microsoft"


def test_extract_svo_triples_skips_relations():
    triples = extract_svo_triples(
        [
            {
                "subject": {"content": "Microsoft"},
                "property": {"content": "rel:instanceof"},
                "value": {"content": "organization"},
            },
            {
                "subject": {"content": "Microsoft"},
                "property": {"content": "acquire"},
                "value": {"content": "GitHub"},
            },
        ]
    )
    assert len(triples) == 1
    assert triples[0].verb == "acquire"


def test_build_search_terms_prioritizes_entities_and_svo():
    analysis = QueryAnalysis(
        raw_query="What did Microsoft acquire in 2026?",
        language="en",
        ner_entities=[
            NerEntity("Microsoft", "organization"),
            NerEntity("2026", "date"),
        ],
        svo_triples=[SvoTriple("Microsoft", "acquire", "")],
        keywords=["microsoft acquisition"],
        lemmas=["acquire", "2026"],
    )
    terms = build_search_terms(analysis, RagSearchConfig())
    assert terms[0] == "Microsoft"
    assert "acquire" in terms
    assert "2026" in terms


def test_build_hybrid_yql_targets_multiple_bm25_fields():
    analysis = QueryAnalysis(
        raw_query="What did Microsoft acquire in 2026?",
        language="en",
        search_terms=["Microsoft", "acquire", "2026"],
    )
    config = RagSearchConfig(
        use_chunk_embedding=True,
        use_question_embedding=True,
        use_text_raw=True,
        use_parent_content=True,
        use_parent_title=True,
    )
    yql = build_hybrid_yql(analysis, config, hits=10)
    assert "nearestNeighbor(chunk_embedding, q_chunk_emb)" in yql
    assert "nearestNeighbor(questions_embeddings, q_question_emb)" in yql
    assert "text_raw contains" in yql
    assert "parent_content contains" in yql
    assert "parent_title contains" in yql
    assert "Microsoft" in yql


def test_build_field_contains_or_clause_matches_existing_pattern():
    clause = build_field_contains_or_clause("text_raw", "Michael Chang")
    assert clause is not None
    assert 'text_raw contains "Michael Chang"' in clause
    assert 'text_raw contains "Michael"' in clause
    assert " OR " in clause


def test_build_multi_field_contains_or_clause():
    clause = build_multi_field_contains_or_clause(
        ["Microsoft", "acquire"],
        fields=("text_raw", "parent_title"),
    )
    assert clause is not None
    assert "text_raw contains" in clause
    assert "parent_title contains" in clause


def test_build_vespa_payload_includes_tensors_and_ranking():
    analysis = QueryAnalysis(
        raw_query="Microsoft acquire",
        language="en",
        search_terms=["Microsoft", "acquire"],
    )
    payload = build_vespa_search_payload(
        analysis,
        RagSearchConfig(),
        q_chunk_emb=[0.1] * 384,
        q_question_emb=[0.2] * 384,
        hits=15,
        timeout_seconds=45.0,
        embedding_dim=384,
    )
    assert payload["hits"] == 15
    assert payload["ranking.profile"] == "hybrid_2_level"
    assert len(payload["input.query(q_chunk_emb)"]) == 384
    assert len(payload["input.query(q_question_emb)"]) == 384
    assert "ranking.weights" not in payload


def test_analyze_query_document_from_pipeline_output():
    analysis = analyze_query_document(
        MICROSOFT_PIPELINE_OUTPUT,
        "What did Microsoft acquire in 2026?",
        language="en",
        config=RagSearchConfig(),
    )
    assert analysis.ner_entities[0].text == "Microsoft"
    assert analysis.svo_triples[0].subject == "Microsoft"
    assert "Microsoft" in analysis.search_terms
    assert "acquire" in analysis.search_terms
    assert "2026" in analysis.search_terms


def test_query_analyzer_task_processes_complex_query():
    llm = AsyncMock()
    llm.embed = AsyncMock(
        side_effect=lambda text: [float(len(text) % 7)] * 384
    )
    task = QueryAnalyzerTask(
        _FakeRunner(),
        llm,
        RagSearchConfig(
            enabled=True,
            use_parent_content=True,
            use_parent_title=True,
        ),
        embedding_dim=384,
        timeout_seconds=30.0,
    )
    result = asyncio.run(
        task.process(
            "What did Microsoft acquire in 2026?",
            language="en",
            hits=12,
        )
    )
    payload = result["payload"]
    analysis = result["analysis"]

    assert "Microsoft" in analysis["search_terms"]
    assert analysis["ner_entities"][0]["text"] == "Microsoft"
    assert analysis["svo_triples"][0]["subject"] == "Microsoft"
    assert payload["hits"] == 12
    assert "Microsoft" in payload["yql"]
    assert llm.embed.await_count >= 1


def test_query_analyzer_task_sync_wrapper():
    llm = AsyncMock()
    llm.embed = AsyncMock(return_value=[0.0] * 384)
    task = QueryAnalyzerTask(_FakeRunner(), llm, RagSearchConfig())
    result = asyncio.run(
        task.process("What did Microsoft acquire in 2026?", language="en")
    )
    assert result["analysis"]["lexical_query"]


def test_format_query_analysis_for_prompt_includes_entities():
    from thot.tools.search.query_analyzer import (
        format_query_analysis_for_prompt,
    )

    text = format_query_analysis_for_prompt(
        raw_query="What did Microsoft acquire?",
        lexical_query="Microsoft acquire",
        analysis={
            "search_terms": ["Microsoft", "acquire"],
            "ner_entities": [{"text": "Microsoft", "label": "organization"}],
            "svo_triples": [
                {"subject": "Microsoft", "verb": "acquire", "object": ""}
            ],
        },
    )
    assert text.startswith("PRIMARY")
    assert "Microsoft | acquire |" in text
    assert "Microsoft (organization)" in text


def test_build_focus_query_text_includes_entities():
    from thot.tools.search.query_analyzer import build_focus_query_text

    focus = build_focus_query_text(
        raw_query="Who interpret the album Abbey Road",
        analysis={
            "ner_entities": [{"text": "Abbey Road", "label": "work"}],
            "search_terms": ["Abbey Road", "interpret"],
        },
    )
    assert "Abbey Road" in focus
    assert "interpret" in focus


def test_build_svo_match_query_prioritizes_triples():
    from thot.tools.search.query_analyzer import build_svo_match_query

    match = build_svo_match_query(
        raw_query="What did Microsoft acquire?",
        lexical_query="Microsoft acquire",
        analysis={
            "svo_triples": [
                {"subject": "Microsoft", "verb": "acquire", "object": "GitHub"}
            ],
            "search_terms": ["Microsoft", "acquire"],
        },
    )
    assert "Microsoft" in match
    assert "acquire" in match
    assert "GitHub" in match


def test_format_vespa_query_json():
    from thot.tools.search.query_analyzer import format_vespa_query_json

    rendered = format_vespa_query_json(
        {
            "yql": "select * from chunk where true",
            "input.query(q_chunk_emb)": [0.1] * 384,
        }
    )
    assert '"yql"' in rendered
    assert '"omitted": true' in rendered
    assert "0.1" not in rendered
