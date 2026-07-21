"""Tests for document ontology derivation from reference ontologies."""

from __future__ import annotations

from pathlib import Path

from rdflib import OWL, RDF, RDFS, Graph, Literal, URIRef

from thot.core.TkeirPaths import configs_dir
from thot.tasks.document_ontology.DocumentOntologyBuilder import (
    DocumentOntologyBuilder,
)
from thot.tasks.document_ontology.DocumentOntologyConfiguration import (
    DocumentOntologyConfiguration,
)
from thot.tasks.document_ontology.OntologyBuilder import TKEIR
from thot.tasks.document_ontology.OntologyDerivation import (
    DerivationSettings,
    derive_document_graph,
    load_reference_graph,
    parse_derivation_settings,
    resolve_ontology_path,
)

FIXTURE_TTL = (
    Path(__file__).resolve().parents[1]
    / "fixtures"
    / "ontologies"
    / "c2sim_sample.ttl"
)


def test_parse_derivation_settings():
    settings = parse_derivation_settings(
        {
            "enabled": True,
            "paths": ["a.ttl", "b.owl"],
            "similarity-threshold": 0.9,
        }
    )
    assert settings.enabled is True
    assert settings.paths == ("a.ttl", "b.owl")
    assert settings.similarity_threshold == 0.9


def test_load_and_match_same_as():
    ref = load_reference_graph([str(FIXTURE_TTL)])
    doc = Graph()
    entity = URIRef("http://tkeir.local/doc/unit1")
    doc.add((entity, RDF.type, TKEIR.Organization))
    doc.add((entity, RDFS.label, Literal("Task Group ALPHA")))

    enriched, report = derive_document_graph(
        doc,
        ref,
        settings=DerivationSettings(
            enabled=True,
            similarity_threshold=0.8,
            add_same_as_links=True,
            add_type_links=True,
        ),
    )
    assert report["status"] == "APPLIED"
    assert report["matches"] >= 1
    alpha = URIRef("http://www.sisostds.org/ontologies/C2SIM#Unit_ALPHA")
    assert (entity, OWL.sameAs, alpha) in enriched


def test_builder_derive_from_path(tmp_path: Path):
    config = DocumentOntologyConfiguration()
    with open(
        Path(configs_dir()) / "document-ontology.yaml",
        encoding="utf-8",
    ) as handle:
        config.load(handle)
    # Enable derivation against fixture
    config.configuration["builders"][0]["derive-from"] = {
        "enabled": True,
        "paths": [str(FIXTURE_TTL)],
        "similarity-threshold": 0.8,
        "save-report": True,
    }
    config.configuration["builders"][0]["save-derivation"] = True
    builder = DocumentOntologyBuilder(config)

    doc = {
        "source_doc_id": "doc-derive-001",
        "content_morphosyntax": [
            {"text": "Task"},
            {"text": "Group"},
            {"text": "ALPHA"},
            {"text": "secured"},
            {"text": "Objective"},
            {"text": "ALPHA"},
        ],
        "content_ner": [
            {
                "start": 0,
                "end": 3,
                "label": "organization",
                "text": "Task Group ALPHA",
            },
        ],
        "kg": [
            {
                "field_type": "content",
                "subject": {
                    "content": ["Task Group ALPHA"],
                    "positions": [0],
                },
                "property": {"content": ["secured"], "positions": [3]},
                "value": {
                    "content": ["Objective ALPHA"],
                    "positions": [4],
                },
            }
        ],
    }
    result = builder.build(doc)
    ontology = result["document_ontology"]
    assert "derivation" in ontology
    assert ontology["derivation"]["status"] in {"APPLIED", "NO_MATCHES"}
    # JSON-LD must be present for Vespa storage path
    assert ontology.get("json_ld")


def test_resolve_relative_to_search_root(tmp_path: Path):
    target = tmp_path / "nested" / "ref.ttl"
    target.parent.mkdir(parents=True)
    target.write_text(
        "@prefix ex: <http://ex/> .\nex:A a <http://www.w3.org/2002/07/owl#Class> .\n",
        encoding="utf-8",
    )
    resolved = resolve_ontology_path("nested/ref.ttl", search_roots=[tmp_path])
    assert resolved == target.resolve()
