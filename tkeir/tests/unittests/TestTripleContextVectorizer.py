# -*- coding: utf-8 -*-
"""Tests for SVO context TF-IDF clustering."""

from thot.tasks.document_ontology.OntologyAlignment import (
    AlignmentSettings,
    build_document_vocabulary,
)
from thot.tasks.document_ontology.triple_context_vectorizer import (
    build_context_bags,
    cluster_entities_by_triple_context,
    collect_document_svo_triples,
)


def test_collect_document_svo_triples_from_kg():
    document = {
        "kg": [
            {
                "field_type": "content",
                "subject": {"content": ["Acme"]},
                "property": {"content": ["launched"]},
                "value": {"content": ["Widget"]},
            }
        ],
    }
    triples = collect_document_svo_triples(document)
    assert triples == [("Acme", "launched", "Widget")]


def test_build_context_bags_for_subject_predicate_object_roles():
    triples = [
        ("Acme", "launched", "Widget"),
        ("Globex", "launched", "Gadget"),
    ]
    subject_bags = build_context_bags(triples, "subject")
    object_bags = build_context_bags(triples, "object")
    predicate_bags = build_context_bags(triples, "predicate")

    assert "acme" in subject_bags
    assert (
        "launched" in predicate_bags["launched"][0]
        or "widget" in subject_bags["acme"][0]
    )
    assert "globex" in subject_bags
    assert "widget" in object_bags


def test_cluster_subjects_by_predicate_object_context():
    triples = [
        ("Acme", "launched", "Widget"),
        ("Globex", "launched", "Widget"),
    ]
    subject_map = cluster_entities_by_triple_context(
        triples,
        "subject",
        similarity_threshold=0.75,
        min_cluster_size=2,
    )
    assert subject_map["acme"] == subject_map["globex"]


def test_cluster_objects_by_subject_predicate_context():
    triples = [
        ("Acme", "owns", "North Factory"),
        ("Acme", "owns", "South Factory"),
    ]
    object_map = cluster_entities_by_triple_context(
        triples,
        "object",
        similarity_threshold=0.75,
        min_cluster_size=2,
    )
    assert object_map["north factory"] == object_map["south factory"]


def test_cluster_predicates_by_subject_object_context():
    triples = [
        ("Acme", "written by", "Alice"),
        ("Widget", "written_by", "Bob"),
    ]
    predicate_map = cluster_entities_by_triple_context(
        triples,
        "predicate",
        similarity_threshold=0.85,
        min_cluster_size=2,
    )
    assert len(set(predicate_map.values())) == 1


def test_build_document_vocabulary_uses_subject_context_map():
    document = {
        "content_ner": [],
        "kg": [
            {
                "field_type": "content",
                "subject": {"content": ["Acme"]},
                "property": {"content": ["launched"]},
                "value": {"content": ["Widget"]},
            },
            {
                "field_type": "content",
                "subject": {"content": ["Globex"]},
                "property": {"content": ["launched"]},
                "value": {"content": ["Widget"]},
            },
        ],
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
    assert (
        vocabulary.subject_class_map["acme"]
        == vocabulary.subject_class_map["globex"]
    )
    assert report["context_clustering"]["triple_count"] == 2
