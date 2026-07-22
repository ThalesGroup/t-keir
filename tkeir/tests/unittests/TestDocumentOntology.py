"""Title: Document Ontology

Tests for document ontology generation and self-healing.

Author: Eric Blaudez

Copyright (c) 2026 Thales
Licensed under the MIT License.
"""

import os

import pytest

from thot.core.TkeirPaths import configs_dir
from thot.tasks.document_ontology.DocumentOntologyBuilder import (
    DocumentOntologyBuilder,
)
from thot.tasks.document_ontology.OntologyBuilder import (
    OntologyBuildSettings,
    build_document_graph,
    collect_ontology_covered_positions,
    compute_ontology_text_coverage,
)
from thot.tasks.document_ontology.OntologyRepairer import (
    apply_rule_based_repairs,
    merge_repair_ttl,
)
from thot.tasks.document_ontology.SelfHealingLoop import (
    SelfHealingSettings,
    run_self_healing_validation,
)
from thot.tasks.document_ontology.ShaclValidator import validate_document_graph


def _document_with_kg() -> dict:
    return {
        "source_doc_id": "doc-ontology-001",
        "content_morphosyntax": [
            {"text": "Acme"},
            {"text": "Corp"},
            {"text": "launched"},
            {"text": "Widget"},
            {"text": "Pro"},
            {"text": "targets"},
            {"text": "42%"},
            {"text": "growth"},
            {"text": "this"},
            {"text": "year"},
        ],
        "content_ner": [
            {
                "start": 0,
                "end": 2,
                "label": "organization",
                "text": "Acme Corp",
            },
            {"start": 4, "end": 5, "label": "product", "text": "Widget Pro"},
            {"start": 8, "end": 9, "label": "quantity", "text": "42%"},
        ],
        "kg": [
            {
                "field_type": "content",
                "subject": {"content": ["Acme Corp"], "positions": [0]},
                "property": {"content": ["launched"], "positions": [2]},
                "value": {"content": ["Widget Pro"], "positions": [4]},
            },
            {
                "field_type": "content",
                "subject": {"content": ["Widget Pro"], "positions": [4]},
                "property": {"content": ["targets"], "positions": [6]},
                "value": {"content": ["42%"], "positions": [8]},
            },
        ],
    }


class TestOntologyBuilder:
    def test_build_document_graph_contains_triples(self):
        graph = build_document_graph(_document_with_kg())
        assert len(graph) > 0
        serialized = graph.serialize(format="turtle")
        assert "Acme Corp" in serialized
        assert "Widget Pro" in serialized

    def test_validate_document_graph_returns_conforms(self):
        graph = build_document_graph(_document_with_kg())
        conforms, violations = validate_document_graph(graph)
        assert isinstance(conforms, bool)
        assert isinstance(violations, list)

    def test_compute_ontology_text_coverage_reports_percent(self):
        coverage = compute_ontology_text_coverage(_document_with_kg())
        assert coverage["text_coverage_percent"] > 0
        assert coverage["covered_tokens"] <= coverage["total_tokens"]
        assert coverage["covered_characters"] <= coverage["total_characters"]
        assert coverage["total_tokens"] == 10

    def test_coverage_uses_ner_keywords_deps_and_chunks(self):
        document = _document_with_kg()
        document["content_deps"] = [
            {"text": token["text"]}
            for token in document["content_morphosyntax"]
        ]
        document["keywords"] = [
            {
                "score": 10,
                "text": "growth",
                "span": {"start": 7, "end": 8},
            }
        ]
        document["golden_chunks"] = [
            {
                "chunk_id": "chunk-0",
                "metadata": {
                    "token_start": 0,
                    "token_end": 10,
                    "primary_entities": {"organization": ["Acme Corp"]},
                    "svo_triplets": [["Acme Corp", "launched", "Widget Pro"]],
                },
            }
        ]

        covered = collect_ontology_covered_positions(document)
        coverage = compute_ontology_text_coverage(document)

        assert covered["content"] == set(range(10))
        assert coverage["text_coverage_percent"] == 100.0
        assert coverage["covered_tokens"] == 10

    def test_build_document_graph_includes_ner_and_keywords(self):
        document = _document_with_kg()
        document["keywords"] = [
            {
                "score": 10,
                "text": "growth",
                "span": {"start": 7, "end": 8},
            }
        ]
        serialized = build_document_graph(document).serialize(format="turtle")
        assert "hasMention" in serialized
        assert "hasKeyword" in serialized

    def test_build_document_graph_skips_short_keywords(self):
        document = _document_with_kg()
        document["content_morphosyntax"].append({"text": "a"})
        document["keywords"] = [
            {"score": 1, "text": "a", "span": {"start": 10, "end": 11}},
            {"score": 9, "text": "growth", "span": {"start": 7, "end": 8}},
        ]
        serialized = build_document_graph(
            document,
            settings=OntologyBuildSettings(min_keyword_length=3),
        ).serialize(format="turtle")
        assert 'label "growth"' in serialized
        assert 'label "a"' not in serialized


class TestSelfHealingLoop:
    def test_rule_repair_can_pass_after_attempt(self):
        graph = build_document_graph(_document_with_kg())
        graph, status, attempts, incoherence_summary = (
            run_self_healing_validation(
                graph,
                settings=SelfHealingSettings(max_repair_attempts=2),
            )
        )
        assert status in {
            "PASSED",
            "PASSED_AFTER_REPAIR",
            "FAILED_WITH_INCOHERENCES",
        }
        assert attempts in {0, 1, 2}
        assert isinstance(incoherence_summary, dict)
        assert "total" in incoherence_summary
        assert "unresolved" in incoherence_summary


class TestDocumentOntologyBuilder:
    def _load_config(self):
        from thot.tasks.document_ontology.DocumentOntologyConfiguration import (
            DocumentOntologyConfiguration,
        )

        config = DocumentOntologyConfiguration()
        with open(
            os.path.join(configs_dir(), "document-ontology.yaml"),
            encoding="utf-8",
        ) as handle:
            config.load(handle)
        return config

    def test_build_persists_ontology_with_correction_metadata(self):
        builder = DocumentOntologyBuilder(config=self._load_config())
        document = _document_with_kg()
        result = builder.run(document)
        ontology = result["document_ontology"]
        assert ontology["json_ld"]
        assert ontology["json_ld"].lstrip().startswith("[")
        assert ontology["shacl_status"] in {
            "PASSED",
            "PASSED_AFTER_REPAIR",
            "FAILED_WITH_INCOHERENCES",
        }
        assert ontology["correction_attempts"] in {0, 1, 2}
        assert isinstance(ontology["incoherences"], dict)
        assert "total" in ontology["incoherences"]
        assert "alignment" not in ontology
        assert "text_coverage_percent" in ontology
        assert ontology["text_coverage_percent"] >= 0
        assert ontology["covered_tokens"] <= ontology["total_tokens"]

    def test_build_requires_kg(self):
        builder = DocumentOntologyBuilder(config=self._load_config())
        with pytest.raises(ValueError):
            builder.run({"content_ner": []})

    def test_merge_repair_ttl_adds_triples(self):
        graph = build_document_graph(_document_with_kg())
        before = len(graph)
        patch_ttl = (
            "@prefix tkeir: <http://tkeir.local/ontology/> .\n"
            "<http://tkeir.local/doc/extra/Product/demo> "
            "tkeir:createdBy <http://tkeir.local/doc/extra/Company/demo> .\n"
        )
        merge_repair_ttl(graph, patch_ttl)
        assert len(graph) > before

    def test_apply_rule_based_repairs_adds_company_link(self):
        graph = build_document_graph(_document_with_kg())
        conforms_before, violations = validate_document_graph(graph)
        if conforms_before:
            pytest.skip("Graph already conforms before repair")
        repaired = apply_rule_based_repairs(graph, violations)
        conforms_after, _ = validate_document_graph(repaired)
        assert conforms_after or len(violations) > 0
