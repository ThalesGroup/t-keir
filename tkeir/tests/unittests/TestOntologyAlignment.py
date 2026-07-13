# -*- coding: utf-8 -*-
"""Tests for ontology class/property alignment and SHACL induction."""

from __future__ import annotations

from rdflib import Graph, Literal, URIRef
from rdflib.namespace import RDF, RDFS

from thot.tasks.document_ontology.OntologyAlignment import (
    AlignmentSettings,
    align_document_graph,
    build_document_vocabulary,
    extract_class_labels,
    extract_predicate_labels,
)
from thot.tasks.document_ontology.OntologyBuilder import TKEIR
from thot.tasks.document_ontology.ShaclInductor import (
    induce_document_shacl_shapes,
)


def _graph_with_synonyms() -> Graph:
    graph = Graph()
    writer = URIRef("http://tkeir.local/doc/demo/Writer/alice-1")
    writers = URIRef("http://tkeir.local/doc/demo/Writers/bob-1")
    product = URIRef("http://tkeir.local/doc/demo/Product/book-1")
    company = URIRef("http://tkeir.local/doc/demo/Company/acme-1")

    graph.add((writer, RDF.type, TKEIR.Writer))
    graph.add((writer, RDFS.label, Literal("Alice")))
    graph.add((writers, RDF.type, TKEIR.Writers))
    graph.add((writers, RDFS.label, Literal("Bob")))
    graph.add((product, RDF.type, TKEIR.Product))
    graph.add((company, RDF.type, TKEIR.Company))
    graph.add((product, TKEIR.writtenBy, writer))
    graph.add((product, TKEIR.createdBy, company))
    return graph


def test_build_document_vocabulary_uses_heuristic_labeling_when_disabled():
    document = {
        "content_ner": [{"label": "organization", "text": "Acme"}],
        "kg": [
            {
                "property": {"content": ["launched"]},
            }
        ],
    }
    vocabulary, report = build_document_vocabulary(
        document,
        settings=AlignmentSettings(enabled=False),
    )
    assert report["status"] == "HEURISTIC"
    assert vocabulary.class_for_ner_label("organization") == "Organization"
    assert vocabulary.predicate_for_verb("launched") == "launched"


def test_build_document_vocabulary_clusters_classes_from_dynamic_labels():
    document = {
        "content_ner": [{"label": "org", "text": "Acme"}],
        "golden_chunks": [
            {
                "metadata": {
                    "primary_entities": {"organization": ["Acme Corp"]},
                }
            }
        ],
        "kg": [],
    }
    vocabulary, report = build_document_vocabulary(
        document,
        settings=AlignmentSettings(
            enabled=True,
            similarity_threshold=0.75,
            min_cluster_size=2,
        ),
    )
    assert report["status"] == "APPLIED"
    assert report["class_clusters"]


def test_build_document_vocabulary_clusters_with_tfidf_lemmas():
    document = {
        "content_ner": [
            {"label": "writer", "text": "Alice"},
            {"label": "writers", "text": "Bob"},
        ],
        "kg": [
            {"property": {"content": ["written by"]}},
            {"property": {"content": ["written_by"]}},
        ],
    }
    vocabulary, report = build_document_vocabulary(
        document,
        settings=AlignmentSettings(
            enabled=True,
            similarity_threshold=0.85,
            min_cluster_size=2,
        ),
    )
    assert report["status"] == "APPLIED"
    assert vocabulary.class_for_ner_label("writer") == vocabulary.class_for_ner_label(
        "writers"
    )
    assert vocabulary.predicate_for_verb("written by") == vocabulary.predicate_for_verb(
        "written_by"
    )


def test_extract_class_and_predicate_labels():
    graph = _graph_with_synonyms()
    assert extract_class_labels(graph) == [
        "Company",
        "Product",
        "Writer",
        "Writers",
    ]
    assert "writtenBy" in extract_predicate_labels(graph)
    assert "createdBy" in extract_predicate_labels(graph)


def test_align_document_graph_merges_synonyms():
    graph = _graph_with_synonyms()
    aligned, report = align_document_graph(
        graph,
        settings=AlignmentSettings(
            enabled=True,
            similarity_threshold=0.85,
            min_cluster_size=2,
        ),
    )

    assert report["status"] == "APPLIED"
    canonical_class = report["class_map"]["Writer"]
    assert report["class_map"]["Writers"] == canonical_class
    assert (None, TKEIR.Writers, None) not in aligned
    assert len(list(aligned.subjects(RDF.type, TKEIR[canonical_class]))) == 2


def test_induce_document_shacl_shapes_uses_canonical_paths():
    graph = _graph_with_synonyms()
    aligned, report = align_document_graph(
        graph,
        settings=AlignmentSettings(enabled=True, similarity_threshold=0.85),
    )
    shapes_ttl = induce_document_shacl_shapes(aligned, report)
    canonical_property = report["property_map"]["writtenBy"]
    assert f"tkeir:{canonical_property}" in shapes_ttl
    assert "Induced" in shapes_ttl
