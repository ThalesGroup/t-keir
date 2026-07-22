"""Title: Ontology reasoner unit tests

Author: Eric Blaudez

Copyright (c) 2026 Thales
Licensed under the MIT License.
"""

from thot.tools.search.ontology_reasoner import (
    owlapy_available,
    query_merged_ontology,
)
from thot.tools.search.ontology_utils import build_hmi_ontology

_SAMPLE = """
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
@prefix owl: <http://www.w3.org/2002/07/owl#> .
@prefix ex: <http://example.org/> .

ex:Organization a owl:Class ;
    rdfs:label "Organization" .
ex:Company a owl:Class ;
    rdfs:subClassOf ex:Organization ;
    rdfs:label "Company" .
ex:Acme a ex:Company ;
    rdfs:label "Acme" .
"""


def test_owlapy_available_is_bool():
    assert isinstance(owlapy_available(), bool)


def test_build_hmi_ontology_merge_metadata():
    out = build_hmi_ontology([_SAMPLE], [], document_ids=["doc-a", "doc-a"])
    assert out["triple_count"] > 0
    assert out["source_count"] == 1
    assert out["document_ids"] == ["doc-a"]
    assert out["json_ld"].startswith("[") or "@" in out["json_ld"]


def test_query_subclasses_rdflib_fallback():
    out = query_merged_ontology(
        _SAMPLE,
        operation="subclasses",
        class_iri="http://example.org/Organization",
        prefer_owlapy=False,
    )
    assert out["backend"] == "rdflib"
    assert out["count"] >= 1
    iris = {row["iri"] for row in out["results"]}
    assert "http://example.org/Company" in iris


def test_query_instances_rdflib():
    out = query_merged_ontology(
        _SAMPLE,
        operation="instances",
        class_iri="http://example.org/Company",
        prefer_owlapy=False,
    )
    assert out["count"] >= 1
    assert any(row["iri"].endswith("Acme") for row in out["results"])


def test_query_sparql():
    out = query_merged_ontology(
        _SAMPLE,
        operation="sparql",
        sparql=(
            "PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#> "
            "SELECT ?label WHERE { ?s rdfs:label ?label }"
        ),
        prefer_owlapy=False,
    )
    assert out["count"] >= 1
    labels = {row.get("label", "") for row in out["results"]}
    assert "Acme" in labels or any("Acme" in v for v in labels)


def test_empty_ontology():
    out = query_merged_ontology(
        "[]", operation="sparql", sparql="SELECT ?s WHERE { ?s ?p ?o }"
    )
    assert out["count"] == 0
    assert out["backend"] == "none"
    assert out.get("json_ld")


def test_query_subclasses_returns_json_ld():
    out = query_merged_ontology(
        _SAMPLE,
        operation="subclasses",
        class_iri="http://example.org/Organization",
        prefer_owlapy=False,
        reasoner="rdflib",
    )
    assert out["json_ld"]
    assert "http://example.org/Company" in out["json_ld"]
    assert out["reasoner"] == "rdflib"


def test_normalize_and_results_as_json_ld():
    from thot.tools.search.ontology_reasoner import (
        normalize_reasoner_name,
        results_as_json_ld,
    )

    assert normalize_reasoner_name("pellet") == "Pellet"
    payload = results_as_json_ld(
        "instances",
        results=[{"iri": "http://example.org/Acme", "label": "Acme"}],
        class_iri="http://example.org/Company",
        reasoner="rdflib",
        backend="rdflib",
    )
    assert "Acme" in payload
    assert "Company" in payload
