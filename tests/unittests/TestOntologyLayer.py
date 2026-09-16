"""Unit tests for canonical ontology identity, JSON concepts, service, expansion."""

from __future__ import annotations

from thot.ontology.expansion import (
    ExpansionSpec,
    expand_concept_ids,
    overlap_score,
)
from thot.ontology.identity import (
    PRED_HAS_VALUE,
    is_stable_id,
    json_attribute_id,
    json_value_id,
    legacy_json_value_id,
    predicate_id,
    preserve_or_mint,
    relation_key,
)
from thot.ontology.json_concepts import extract_json_concepts
from thot.ontology.model import (
    Ontology,
    OntologyConcept,
    Provenance,
    ProvenanceKind,
)
from thot.ontology.service import OntologyService
from thot.ontology.vespa import (
    build_passage_yql,
    chunk_ontology_vespa_fields,
    grouping_hits_to_ontology,
    relation_contains_clauses,
)


def test_labels_are_not_identifiers():
    assert (
        preserve_or_mint("Kubernetes on the cloud")
        == "doc:kubernetes.on.the.cloud"
    )
    assert preserve_or_mint("C4ISR") == "C4ISR"
    assert is_stable_id("technology:kubernetes")
    assert not is_stable_id("How is Kubernetes deployed?")


def test_json_ids_are_centralized():
    assert (
        json_attribute_id("customer.country")
        == "json:attribute:customer.country"
    )
    assert json_value_id("customer.country", "France") == (
        "json:value:customer.country=france"
    )
    assert legacy_json_value_id("domain", "osint") == "DOMAIN:osint"
    assert predicate_id("has_value") == PRED_HAS_VALUE


def test_nested_json_paths_and_arrays():
    extracted = extract_json_concepts(
        {
            "title": "ignored narrative",
            "customer": {"country": "France", "segment": "enterprise"},
            "tags": ["alpha", "beta"],
            "status": "active",
        }
    )
    ids = extracted.chunk_ids()
    assert "json:attribute:customer.country" in ids
    assert any(i.startswith("json:value:customer.country=") for i in ids)
    assert any("COUNTRY:France" in i or "france" in i.lower() for i in ids)
    assert extracted.ontology.relations
    assert extracted.ontology.relations[0].predicate_id == PRED_HAS_VALUE
    assert all("title" not in i.lower() or i.startswith("json:") for i in ids)
    # narrative body is not a concept
    joined = " ".join(ids)
    assert "ignored narrative" not in joined


def test_expert_ontology_not_overwritten():
    expert = Ontology()
    expert.add_concept(
        OntologyConcept(
            "C1",
            preferred_label="Kubernetes",
            provenance=Provenance(kind=ProvenanceKind.EXPERT_DEFINED),
        )
    )
    extra = Ontology()
    extra.add_concept(OntologyConcept("C1", preferred_label="Other"))
    extra.add_concept(OntologyConcept("C2", preferred_label="Pod"))
    merged = expert.extend(extra)
    assert merged.get("C1").preferred_label == "Kubernetes"
    assert merged.get("C1").provenance.kind is ProvenanceKind.EXPERT_DEFINED
    assert merged.get("C2") is not None


def test_map_and_extract_relations():
    svc = OntologyService.from_business_payload(
        {
            "concepts": [
                {
                    "concept_id": "technology:kubernetes",
                    "preferred_label": "Kubernetes",
                }
            ]
        }
    )
    ids, mapped = svc.map_concepts(["Kubernetes", "cluster"])
    assert ids[0] == "technology:kubernetes"
    assert mapped == 1
    rels = svc.extract_svo_relations(
        {
            "kg": [
                {
                    "subject": {"content": ["Kubernetes"]},
                    "property": {"content": ["implements"]},
                    "value": {"content": ["orchestration"]},
                }
            ]
        },
        {"text_raw": "Kubernetes implements orchestration"},
    )
    assert rels
    assert rels[0].subject_id == "technology:kubernetes"
    assert rels[0].predicate_id == "pred:implements"


def test_enrichment_without_expert_ontology():
    out = OntologyService().enrich_chunk(
        {"text_raw": "plain text chunk"},
        {"source_doc_id": "d1"},
    )
    assert isinstance(out.concept_ids, list)
    assert out.metrics["failures"] == 0


def test_json_enrichment_and_vespa_fields():
    out = OntologyService().enrich_chunk(
        {"text_raw": "customer record"},
        {"record": {"customer": {"country": "France"}}},
    )
    assert any(i.startswith("json:attribute:") for i in out.concept_ids)
    fields = chunk_ontology_vespa_fields(out.concept_ids, out.relations)
    assert fields["ontology_concepts"] == fields["ontology_concept_ids"]
    assert fields["ontology_rel_keys"]
    assert fields["ontology_relations"][0]["subject_id"].startswith(
        "json:attribute:"
    )


def test_expansion_parents_children_related():
    ont = Ontology()
    ont.add_concept(
        OntologyConcept(
            "k8s",
            preferred_label="Kubernetes",
            narrower_ids=["pod"],
            broader_ids=["cncf"],
            related_ids=["container"],
        )
    )
    ont.add_concept(OntologyConcept("pod", preferred_label="Pod"))
    ont.add_concept(OntologyConcept("cncf", preferred_label="CNCF"))
    ont.add_concept(OntologyConcept("container", preferred_label="Container"))
    children = expand_concept_ids(
        ["k8s"], ont, ExpansionSpec(include_children=True)
    )
    assert "pod" in children.concept_ids
    parents = expand_concept_ids(
        ["k8s"], ont, ExpansionSpec(include_parents=True)
    )
    assert "cncf" in parents.concept_ids
    related = expand_concept_ids(
        ["k8s"], ont, ExpansionSpec(include_related=True)
    )
    assert "container" in related.concept_ids


def test_overlap_and_yql():
    score = overlap_score(
        hit_concept_ids=["a", "b"],
        hit_relation_keys=[relation_key("a", PRED_HAS_VALUE, "b")],
        query_concept_ids=["a"],
        query_relation_keys=[relation_key("a", PRED_HAS_VALUE, "b")],
        concept_weight=1.0,
        relation_weight=1.0,
    )
    assert score == 2.0
    yql = build_passage_yql(
        "global",
        hits=10,
        concept_ids=["technology:kubernetes"],
        include_nearest_neighbor=False,
    )
    assert "ontology_concepts contains" in yql
    assert "ontology_concept_ids contains" in yql
    exact = relation_contains_clauses(
        [
            {
                "subject_id": "a",
                "predicate_id": PRED_HAS_VALUE,
                "object_id": "b",
            }
        ],
        mode="exact",
    )
    assert "ontology_rel_keys contains" in exact[0]


def test_grouping_export_shape():
    ont = grouping_hits_to_ontology(
        concept_counts={"C1": 2},
        relation_keys=["C1|pred:has_value|V1"],
    )
    payload = ont.to_export_dict()
    assert payload["concepts"][0]["id"] == "C1"
    assert payload["relations"][0]["object"] == "V1"


def test_shacl_interface():
    from thot.ontology.shacl import ontology_to_shacl_ttl, validate_ontology

    ont = Ontology(
        concepts={"C1": OntologyConcept("C1", preferred_label="K8s")}
    )
    ttl = ontology_to_shacl_ttl(ont)
    assert "sh:" in ttl
    result = validate_ontology(ont)
    assert "conforms" in result


def test_json_records_keeps_legacy_and_canonical_ids():
    from thot.tools.ingest.json_records import extract_record_concepts

    ids = extract_record_concepts({"domain": "osint", "title": "skip me"})
    assert "DOMAIN:osint" in ids
    assert any(i.startswith("json:attribute:") for i in ids)
    assert all("skip me" not in i for i in ids)


def test_index_passage_fields_include_concept_alias():
    from thot.tools.ingest.index_passages import _passage_fields

    fields = _passage_fields(
        chunk={"chunk_id": "c1", "text_raw": "Kubernetes"},
        document={"source_doc_id": "doc1"},
        dense=[0.1, 0.2],
        sparse={"3": 0.5},
        ontology_concepts=["technology:kubernetes"],
        embedding_dim=2,
        ontology_relations=[
            {
                "subject_id": "technology:kubernetes",
                "predicate_id": "pred:implements",
                "object_id": "technology:container-orchestration",
                "confidence": 0.94,
            }
        ],
    )
    assert fields["ontology_concepts"] == ["technology:kubernetes"]
    assert fields["ontology_concept_ids"] == ["technology:kubernetes"]
    assert fields["ontology_rel_keys"]
    assert fields["freshness_ttl_seconds"] == 0
    assert fields["source_type"] == "ingest"
    assert fields["chunk_id"] == "c1"
    from thot.tools.ingest.document_index import corpus_doc_docid

    assert fields["parent_doc_id"] == corpus_doc_docid("doc1")


def test_text_only_yql_still_uses_nearest_neighbor():
    yql = build_passage_yql("global", hits=10, include_nearest_neighbor=True)
    assert "nearestNeighbor(dense_vector, q_dense)" in yql
    assert "ontology_concepts contains" not in yql


def test_ontology_triple_fields_and_yql():
    from thot.ontology.model import OntologyRelation
    from thot.ontology.vespa import (
        build_corpus_doc_yql,
        ontology_triple_docid,
        triple_to_vespa_fields,
    )

    rel = OntologyRelation("a", "pred:has_value", "b")
    fields = triple_to_vespa_fields(rel, first_source_ref="doc1")
    assert fields["triple_key"] == "a|pred:has_value|b"
    assert len(ontology_triple_docid("a", "pred:has_value", "b")) == 40
    yql = build_corpus_doc_yql(
        hits=5, concept_ids=["C1"], include_nearest_neighbor=False
    )
    assert "from corpus_doc" in yql
    assert "ontology_concept_ids contains" in yql


def test_catalog_sync_skips_existing_triples():
    import asyncio

    from thot.ontology.catalog_sync import sync_corpus_ontology
    from thot.ontology.model import Ontology, OntologyConcept, OntologyRelation
    from thot.ontology.vespa import (
        ontology_concept_docid,
        ontology_triple_docid,
    )

    class _Fake:
        def __init__(self) -> None:
            self.store: dict[tuple[str, str], dict] = {}

        async def get_index_document(self, document_type, document_key):
            return self.store.get((document_type, document_key))

        async def upsert_ontology_concept(self, fields, document_key):
            self.store[("ontology_concept", document_key)] = fields

        async def upsert_ontology_triple(self, fields, document_key):
            self.store[("ontology_triple", document_key)] = fields

    fake = _Fake()
    cid = ontology_concept_docid("C1")
    tid = ontology_triple_docid("C1", "pred:related", "C2")
    fake.store[("ontology_concept", cid)] = {"concept_id": "C1"}
    fake.store[("ontology_triple", tid)] = {"triple_key": "C1|pred:related|C2"}
    ont = Ontology()
    ont.add_concept(OntologyConcept("C1"))
    ont.add_concept(OntologyConcept("C2"))
    ont.add_relation(OntologyRelation("C1", "pred:related", "C2"))
    result = asyncio.run(sync_corpus_ontology(fake, ont))
    assert result.concepts_inserted == 1
    assert result.concepts_skipped == 1
    assert result.triples_inserted == 0
    assert result.triples_skipped == 1
