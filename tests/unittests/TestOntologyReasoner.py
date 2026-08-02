"""Title: Ontology reasoner unit tests

Author: Eric Blaudez

Copyright (c) 2026 Thales
Licensed under the MIT License.
"""

import pytest

from thot.tools.search.ontology_reasoner import (
    normalize_reasoner_name,
    query_merged_ontology,
)
from thot.tools.search.ontology_utils import build_hmi_ontology

_SAMPLE = """
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
@prefix owl: <http://www.w3.org/2002/07/owl#> .
@prefix xsd: <http://www.w3.org/2001/XMLSchema#> .
@prefix ex: <http://example.org/> .

ex:Organization a owl:Class ;
    rdfs:label "Organization" .
ex:Company a owl:Class ;
    rdfs:subClassOf ex:Organization ;
    rdfs:label "Company" .
ex:Person a owl:Class ;
    rdfs:label "Person" .
ex:age a owl:DatatypeProperty ;
    rdfs:range xsd:integer ;
    rdfs:label "age" .
ex:Acme a ex:Company ;
    rdfs:label "Acme" .
ex:Alice a ex:Person ;
    rdfs:label "Alice" ;
    ex:age 25 .
ex:Bob a ex:Person ;
    rdfs:label "Bob" ;
    ex:age 18 .
"""


def test_build_hmi_ontology_merge_metadata():
    out = build_hmi_ontology([_SAMPLE], [], document_ids=["doc-a", "doc-a"])
    assert out["triple_count"] > 0
    assert out["source_count"] == 1
    assert out["document_ids"] == ["doc-a"]
    assert out["json_ld"].startswith("[") or "@" in out["json_ld"]


def test_query_subclasses_python_backend():
    out = query_merged_ontology(
        _SAMPLE,
        operation="subclasses",
        class_iri="http://example.org/Organization",
    )
    assert out["backend"] == "python"
    assert out["reasoner"] == "python"
    assert out["count"] >= 1
    iris = {row["iri"] for row in out["results"]}
    assert "http://example.org/Company" in iris


def test_query_instances_python():
    out = query_merged_ontology(
        _SAMPLE,
        operation="instances",
        class_iri="http://example.org/Company",
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
        reasoner="python",
    )
    assert out["json_ld"]
    assert "http://example.org/Company" in out["json_ld"]
    assert out["reasoner"] == "python"


def test_normalize_reasoner_name():
    assert normalize_reasoner_name(None) == "python"
    assert normalize_reasoner_name("python") == "python"
    with pytest.raises(ValueError, match="unsupported reasoner"):
        normalize_reasoner_name("hermit")


def test_results_as_json_ld():
    from thot.tools.search.ontology_reasoner import results_as_json_ld

    payload = results_as_json_ld(
        "instances",
        results=[{"iri": "http://example.org/Acme", "label": "Acme"}],
        class_iri="http://example.org/Company",
        reasoner="python",
        backend="python",
    )
    assert "Acme" in payload
    assert "Company" in payload


def test_coherence_check():
    out = query_merged_ontology(_SAMPLE, operation="consistency")
    assert out["backend"] == "python"
    assert "consistent" in out


def test_expression_person_age():
    out = query_merged_ontology(
        _SAMPLE,
        operation="expression",
        expression="Person and age > 20",
    )
    assert out["backend"] == "python"
    assert out["count"] >= 1
    iris = " ".join(str(row) for row in out["results"])
    assert "Alice" in iris


def test_extra_json_ld_merge():
    extra = """
    @prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
    @prefix owl: <http://www.w3.org/2002/07/owl#> .
    @prefix bo: <http://business.example/> .
    bo:Vessel a owl:Class ; rdfs:label "Vessel" .
    """
    out = query_merged_ontology(
        _SAMPLE,
        operation="expression",
        expression="Vessel",
        extra_json_ld=extra,
    )
    assert out["operation"] == "expression"
    assert out["count"] == 0
    assert "Compiled expression" in (out.get("note") or "")


def test_proposals_depend_on_chunk_terms_and_ontology():
    from thot.tools.search.business_ontology import (
        business_ontology_to_json_ld,
        load_dataset_business_ontology_payload,
    )
    from thot.tools.search.ontology_utils import merge_rdf_graphs
    from thot.tools.search.python_reasoner import (
        important_terms_from_chunk_hits,
        propose_navigator_queries,
    )

    payload = load_dataset_business_ontology_payload("osint")
    assert payload
    graph = merge_rdf_graphs([business_ontology_to_json_ld(payload)])
    assert len(graph) > 100

    entities = [
        {"label": "Suez", "type": "LOC", "chunk_ids": ["c1", "c2", "c3"]},
        {"label": "vessel", "type": "ORG", "chunk_ids": ["c1", "c2"]},
    ]
    keywords = [
        {"label": "STS", "chunk_ids": ["c1", "c3"]},
        {"label": "loitering", "chunk_ids": ["c2"]},
    ]
    terms = important_terms_from_chunk_hits(
        entities=entities,
        keywords=keywords,
        focus_terms=["Suez"],
        limit=5,
    )
    assert terms[0].lower() == "suez"

    proposals = propose_navigator_queries(
        graph,
        focus_terms=["Suez"],
        chunk_entities=entities,
        chunk_keywords=keywords,
    )
    kinds = {row["kind"] for row in proposals}
    assert "sparql" in kinds
    sparql_titles = "\n".join(
        row["title"] for row in proposals if row["kind"] == "sparql"
    ).lower()
    assert "suez" in sparql_titles
    assert "personnel movement" not in sparql_titles
    joined = "\n".join(
        row["query"] for row in proposals if row["kind"] == "sparql"
    ).lower()
    assert "suez" in joined
    assert "person and age" not in joined
