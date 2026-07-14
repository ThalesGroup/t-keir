# -*- coding: utf-8 -*-
"""Unit tests for Vespa ontology utilities."""

from thot.tools.search.ontology_utils import (
    build_hmi_ontology,
    detect_rdf_format,
    extract_deduplicated_svo_triples,
    extract_focus_passages,
    extract_relevant_triples,
    format_svo_ontology_context,
    merge_rdf_graphs,
    merge_turtle_graphs,
    serialize_graph_json_ld,
    truncate_for_prompt,
)

_SAMPLE_TURTLE = """
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
@prefix tkeir: <http://tkeir.local/ontology/> .
@prefix tkeirdoc: <http://tkeir.local/doc/> .

tkeirdoc:doc_a a tkeir:Document ;
    tkeir:hasChunk <http://tkeir.local/doc/doc_a/Chunk/chunk_1> ;
    tkeir:hasKeyword <http://tkeir.local/doc/doc_a/Keyword/streaming_service> .

<http://tkeir.local/doc/doc_a/Keyword/streaming_service> a tkeir:Keyword ;
    rdfs:label "msn video streaming service" .

<http://tkeir.local/doc/doc_a/Chunk/chunk_1> a tkeir:DocumentChunk ;
    rdfs:label "doc.pdf#chunk-1-abc" ;
    tkeir:hasMention <http://tkeir.local/doc/doc_a/Company/acme-aaa> ;
    tkeir:hasMention <http://tkeir.local/doc/doc_a/Date/jan-2001> ;
    tkeir:hasStatement <http://tkeir.local/doc/doc_a/Company/acme-aaa> .

<http://tkeir.local/doc/doc_a/Company/acme-aaa> a tkeir:Company ;
    rdfs:label "Acme" ;
    tkeir:createdBy <http://tkeir.local/doc/doc_a/Product/widget-bbb> .

<http://tkeir.local/doc/doc_a/Date/jan-2001> a tkeir:Date ;
    rdfs:label "January 2001" .

<http://tkeir.local/doc/doc_a/Product/widget-bbb> a tkeir:Product ;
    rdfs:label "Widget" .
"""


def test_detect_rdf_format():
    assert detect_rdf_format('[{"@id": "http://example.org/a"}]') == "json-ld"
    assert detect_rdf_format("@prefix ex: <http://example.org/> .") == "turtle"


def test_merge_rdf_graphs_accepts_json_ld():
    graph = merge_rdf_graphs(
        [
            '[{"@id": "http://example.org/Alice", '
            '"@type": "http://example.org/Person"}]'
        ]
    )
    assert len(graph) > 0


def test_merge_and_query_turtle_graphs():
    graph = merge_turtle_graphs(
        [
            "@prefix ex: <http://example.org/> .\n"
            "ex:Alice a ex:Person .\n"
            "ex:Alice ex:worksFor ex:Acme .\n"
        ]
    )
    lines = extract_relevant_triples(graph, "Alice works")
    assert lines
    assert any("worksFor" in line or "Person" in line for line in lines)


def test_extract_deduplicated_svo_triples_scopes_to_chunk_entities():
    graph = merge_turtle_graphs([_SAMPLE_TURTLE])
    chunk_id = "doc.pdf#chunk-1-abc"
    lines = extract_deduplicated_svo_triples(
        graph,
        "Acme",
        chunk_ids=[chunk_id],
    )
    assert lines == ["Acme | createdBy | Widget"]
    assert not extract_deduplicated_svo_triples(
        graph,
        "Acme",
        chunk_ids=["missing-chunk"],
    )


def test_format_svo_ontology_context_replaces_chunk_excerpts():
    from thot.tools.search.app import RetrievedChunk

    graph = merge_turtle_graphs([_SAMPLE_TURTLE])
    chunk = RetrievedChunk(
        chunk_id="doc.pdf#chunk-1-abc",
        text_raw="Acme launched Widget.",
        parent_doc_id="file://doc.pdf",
    )
    text = format_svo_ontology_context(
        graph,
        "Acme",
        [chunk],
        empty_message="none",
    )
    assert "Acme | createdBy | Widget" in text
    assert "Deduped SVO facts" not in text


def test_build_hmi_ontology_exports_entities_and_keywords():
    chunk_id = "doc.pdf#chunk-1-abc"
    chunk_text = "Acme launched msn video streaming service in January 2001."
    ontology = build_hmi_ontology(
        [_SAMPLE_TURTLE],
        [chunk_id],
        chunk_texts={chunk_id: chunk_text},
    )
    assert ontology["entities"]
    acme = next(
        node for node in ontology["entities"] if node["label"] == "Acme"
    )
    assert acme["type"] == "Company"
    assert chunk_id in acme["chunk_ids"]
    assert any(
        node["label"] == "January 2001" for node in ontology["entities"]
    )
    assert not any(node["label"] == "Widget" for node in ontology["entities"])
    assert ontology["keywords"]
    keyword = ontology["keywords"][0]
    assert "msn video streaming service" in keyword["label"]
    assert chunk_id in keyword["chunk_ids"]
    assert "edges" not in ontology
    assert "nodes" not in ontology
    assert ontology["json_ld"].startswith("[")


def test_build_hmi_ontology_serializes_json_ld_from_turtle():
    ontology = build_hmi_ontology([_SAMPLE_TURTLE], [])
    assert '"@id"' in ontology["json_ld"] or '"@type"' in ontology["json_ld"]
    roundtrip = merge_rdf_graphs([ontology["json_ld"]])
    assert len(roundtrip) > 0


def test_extract_focus_passages_ranks_yang_trump_sentences():
    chunk_id = "tests/indexing/input/doc.pdf#chunk-13"
    text = (
        "By 2019, Andrew Yang became popular among supporters. "
        "National Review commentator Theodore Kopfre reported that Yang had "
        '" replaced Donald Trump as the meme candidate . " '
        "Unrelated content about music genres follows."
    )
    passages = extract_focus_passages(
        [(chunk_id, text)],
        "Who report Yang had replace Donald Trump ?",
    )
    assert "Kopfre" in passages
    assert "Yang" in passages
    assert "Donald Trump" in passages


def test_truncate_for_prompt_keeps_prefix():
    assert truncate_for_prompt("abcdefghij", max_chars=5) == "abcde…"


def test_build_hmi_ontology_filters_short_keywords():
    turtle = """
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
@prefix tkeir: <http://tkeir.local/ontology/> .
@prefix tkeirdoc: <http://tkeir.local/doc/> .

tkeirdoc:doc_a a tkeir:Document ;
    tkeir:hasChunk <http://tkeir.local/doc/doc_a/Chunk/chunk_1> ;
    tkeir:hasKeyword <http://tkeir.local/doc/doc_a/Keyword/e> ;
    tkeir:hasKeyword <http://tkeir.local/doc/doc_a/Keyword/end> .

<http://tkeir.local/doc/doc_a/Keyword/e> a tkeir:Keyword ;
    rdfs:label "e" .

<http://tkeir.local/doc/doc_a/Keyword/end> a tkeir:Keyword ;
    rdfs:label "end" .

<http://tkeir.local/doc/doc_a/Chunk/chunk_1> a tkeir:DocumentChunk ;
    rdfs:label "doc.pdf#chunk-1-abc" .
"""
    chunk_id = "doc.pdf#chunk-1-abc"
    chunk_text = "At the end of the e-book chapter."
    ontology = build_hmi_ontology(
        [turtle],
        [chunk_id],
        chunk_texts={chunk_id: chunk_text},
        min_keyword_length=3,
    )
    labels = {keyword["label"] for keyword in ontology["keywords"]}
    assert "end" in labels
    assert "e" not in labels
