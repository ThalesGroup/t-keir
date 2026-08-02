"""Title: Ontology Utils

Unit tests for Vespa ontology utilities.

Author: Eric Blaudez

Copyright (c) 2026 Thales
Licensed under the MIT License.
"""

from thot.tools.search.ontology_utils import (
    build_hmi_ontology,
    detect_rdf_format,
    extract_deduplicated_svo_triples,
    extract_focus_passages,
    extract_relevant_triples,
    format_svo_ontology_context,
    merge_rdf_graphs,
    merge_turtle_graphs,
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
    assert acme["weight"] > 0
    assert acme["mention_count"] >= 1
    assert acme["text_hits"] >= 1
    assert any(
        node["label"] == "January 2001" for node in ontology["entities"]
    )
    # kg object via hasStatement → createdBy Widget is reinforced as an entity.
    widget = next(
        node for node in ontology["entities"] if node["label"] == "Widget"
    )
    assert widget["type"] == "Product"
    assert chunk_id in widget["chunk_ids"]
    assert ontology["keywords"]
    keyword = ontology["keywords"][0]
    assert "msn video streaming service" in keyword["label"]
    assert chunk_id in keyword["chunk_ids"]
    assert keyword["weight"] > 0
    assert isinstance(ontology.get("relations"), list)
    assert "edges" not in ontology
    assert "nodes" not in ontology
    assert ontology["json_ld"].startswith("[")
    assert "importanceScore" not in ontology["json_ld"]
    assert "linkWeight" not in ontology["json_ld"]


def test_build_hmi_ontology_reinforces_doc_ner_onto_chunks():
    """Document-level hasMention (content_ner) attaches to retrieved chunks."""
    turtle = """
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
@prefix tkeir: <http://tkeir.local/ontology/> .
@prefix tkeirdoc: <http://tkeir.local/doc/> .

tkeirdoc:doc_b a tkeir:Document ;
    tkeir:hasChunk <http://tkeir.local/doc/doc_b/Chunk/c1> ;
    tkeir:hasMention <http://tkeir.local/doc/doc_b/Location/greece> .

<http://tkeir.local/doc/doc_b/Location/greece> a tkeir:Location ;
    rdfs:label "Greece" .

<http://tkeir.local/doc/doc_b/Chunk/c1> a tkeir:DocumentChunk ;
    rdfs:label "doc-b#chunk-1" .
"""
    chunk_id = "doc-b#chunk-1"
    ontology = build_hmi_ontology(
        [turtle],
        [chunk_id],
        chunk_texts={chunk_id: "Patrol near Greece and the Aegean."},
    )
    greece = next(
        node for node in ontology["entities"] if node["label"] == "Greece"
    )
    assert greece["type"] == "Location"
    assert chunk_id in greece["chunk_ids"]


def test_enrich_hmi_from_analyzed_tkeir_fields():
    """Search-time: read kg / content_ner / keywords from analyzed dump."""
    from thot.tools.search.ontology_utils import (
        enrich_hmi_ontology_from_analyzed_documents,
    )

    chunk_id = "c1"
    parent = "doc:maritime"
    hmi = {
        "entities": [],
        "keywords": [],
        "relations": [],
        "json_ld": "[]",
    }
    analyzed = {
        parent: {
            "source_doc_id": parent,
            "content_ner": [
                {"text": "Greece", "label": "location"},
            ],
            "kg": [
                {
                    "subject": {"content": ["MARITIME", "ALERT"]},
                    "property": {"content": ["held"]},
                    "value": {"content": ["station"]},
                    "field_type": "content",
                }
            ],
            "keywords": [{"text": "AIS dark", "score": 5}],
        }
    }
    text = "MARITIME ALERT held station near Greece with AIS dark activity."
    out = enrich_hmi_ontology_from_analyzed_documents(
        hmi,
        analyzed_documents=analyzed,
        chunk_parent_ids={chunk_id: parent},
        chunk_texts={chunk_id: text},
    )
    labels = {row["label"] for row in out["entities"]}
    assert "Greece" in labels
    assert "MARITIME ALERT" in labels
    assert "station" in labels
    assert any(row["label"] == "AIS dark" for row in out["keywords"])
    assert any(
        row["source"] == "MARITIME ALERT"
        and row["predicate"] == "held"
        and row["target"] == "station"
        for row in out["relations"]
    )
    # Structural scaffolding must not displace kg verbs.
    assert not any(
        str(row.get("predicate") or "").casefold() == "haskeyword"
        for row in out["relations"]
    )


def test_build_hmi_ontology_serializes_json_ld_from_turtle():
    ontology = build_hmi_ontology([_SAMPLE_TURTLE], [])
    assert '"@id"' in ontology["json_ld"] or '"@type"' in ontology["json_ld"]
    roundtrip = merge_rdf_graphs([ontology["json_ld"]])
    assert len(roundtrip) > 0


def test_extract_focus_passages_prefers_tight_query_cluster():
    text = (
        "Unrelated vaporwave essay about albums and music scenes. "
        "George Harrison liked Abbey Road from the Beatles. "
        "More vaporwave artists continued releasing albums."
    )
    passages = extract_focus_passages(
        [("c1", text)],
        "Abbey Road George Harrison",
        context_sentences=0,
        max_passages=1,
    )
    assert "George Harrison" in passages
    assert "vaporwave" not in passages.lower()


def test_extract_focus_passages_includes_neighboring_context():
    chunk_id = "doc.pdf#chunk-2"
    text = (
        "Earlier unrelated background about critics and live albums. "
        'George Harrison liked "Something in the Way She Moves" so much that '
        "he used the beginning as the first line of his 1969 song Something "
        "from the Beatles album Abbey Road. "
        "Taylor stated that he never thought George intended to copy the song."
    )
    passages = extract_focus_passages(
        [(chunk_id, text)],
        "Who interpret the album Abbey Road",
        context_sentences=1,
        max_passages=1,
    )
    assert "George Harrison" in passages
    assert "Abbey Road" in passages
    assert "Taylor stated" in passages


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


def test_build_hmi_ontology_exports_entities_without_retrieved_chunks():
    """Basket brief fuses analyzed RDF with zero Vespa hits — still export chips."""
    ontology = build_hmi_ontology(
        [_SAMPLE_TURTLE],
        [],
        document_ids=["doc.pdf"],
    )
    assert ontology["triple_count"] > 0
    assert ontology[
        "entities"
    ], "expected NER entities from all DocumentChunks"
    assert any(node["label"] == "Acme" for node in ontology["entities"])
    assert ontology["keywords"], "expected keywords without chunk_text filter"
    assert any(
        "msn video streaming service" in node["label"]
        for node in ontology["keywords"]
    )
