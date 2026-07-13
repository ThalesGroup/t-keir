# -*- coding: utf-8 -*-
"""Tests for ontology vocabulary naming helpers."""

from rdflib import Graph, Literal, URIRef
from rdflib.namespace import RDF, RDFS

from thot.tasks.document_ontology.OntologyBuilder import TKEIR
from thot.tasks.document_ontology.OntologyVocabulary import (
    sanitize_rdf_local_name,
    title_case_label,
)
from thot.tasks.document_ontology.ShaclInductor import (
    induce_document_shacl_shapes,
)
from thot.tasks.document_ontology.ShaclValidator import validate_document_graph


def test_sanitize_rdf_local_name_strips_invalid_characters():
    assert title_case_label("mandarin.[7") == "Mandarin7"
    assert sanitize_rdf_local_name("can-speak!", pascal=False) == "canSpeak"


def test_induced_shacl_shapes_parse_with_sanitized_class_names():
    graph = Graph()
    coach = URIRef("http://tkeir.local/doc/demo/Chang/coach-1")
    language = URIRef("http://tkeir.local/doc/demo/Mandarin.[7/lang-1")
    graph.add((coach, RDF.type, TKEIR["Chang"]))
    graph.add((coach, RDFS.label, Literal("Coach")))
    graph.add((language, RDF.type, TKEIR["Mandarin.[7"]))
    graph.add((coach, TKEIR["canSpeak"], language))

    shapes_ttl = induce_document_shacl_shapes(
        graph,
        {
            "node_classes": ["Chang", "Mandarin.[7"],
            "class_map": {},
            "property_map": {},
        },
    )
    shapes_graph = Graph()
    shapes_graph.parse(data=shapes_ttl, format="turtle")
    conforms, _violations = validate_document_graph(
        graph, shapes_ttl=shapes_ttl
    )
    assert "Mandarin.[7" not in shapes_ttl
    assert "Mandarin7" in shapes_ttl
