"""Title: SHACL adapter for the canonical ontology model.

Converts :class:`thot.ontology.model.Ontology` to RDF and reuses the
existing document-ontology SHACL inductor / validator. Vespa storage is
not imported here.

Author: Eric Blaudez

Copyright (c) 2026 Thales
Licensed under the MIT License.
"""

from __future__ import annotations

from typing import Any

from thot.ontology.model import Ontology, ProvenanceKind


def ontology_to_rdf_graph(ontology: Ontology):
    """Build an rdflib Graph from the canonical ontology.

    Example:
        >>> from thot.ontology.model import Ontology, OntologyConcept
        >>> from thot.ontology.shacl import ontology_to_rdf_graph
        >>> g = ontology_to_rdf_graph(Ontology(concepts={
        ...     'C1': OntologyConcept('C1', preferred_label='K8s'),
        ... }))
        >>> len(g) > 0
        True
    """
    from rdflib import Graph, Literal, Namespace, URIRef
    from rdflib.namespace import RDF, RDFS, SKOS

    from thot.tasks.document_ontology.OntologyBuilder import TKEIR
    from thot.tasks.document_ontology.OntologyVocabulary import (
        sanitize_rdf_class_name,
    )

    graph = Graph()
    graph.bind("tkeir", TKEIR)
    graph.bind("skos", SKOS)
    SH = Namespace("http://www.w3.org/ns/shacl#")
    graph.bind("sh", SH)

    def _uri(concept_id: str) -> URIRef:
        safe = sanitize_rdf_class_name(concept_id, fallback="Concept")
        return TKEIR[safe]

    for concept in ontology.concepts.values():
        node = _uri(concept.concept_id)
        graph.add((node, RDF.type, TKEIR.Concept))
        if concept.concept_type:
            graph.add((node, TKEIR.conceptType, Literal(concept.concept_type)))
        label = concept.preferred_label or concept.concept_id
        graph.add((node, RDFS.label, Literal(label)))
        graph.add((node, SKOS.prefLabel, Literal(label)))
        for alias in concept.aliases:
            graph.add((node, SKOS.altLabel, Literal(alias)))
        if concept.definition:
            graph.add((node, SKOS.definition, Literal(concept.definition)))
        graph.add(
            (
                node,
                TKEIR.provenance,
                Literal(concept.provenance.kind.value),
            )
        )
        if concept.provenance.kind is ProvenanceKind.EXPERT_DEFINED:
            graph.add((node, TKEIR.expertDefined, Literal(True)))
        for parent in concept.broader_ids or concept.parent_ids:
            graph.add((node, SKOS.broader, _uri(parent)))
        for child in concept.narrower_ids:
            graph.add((node, SKOS.narrower, _uri(child)))
        for other in concept.related_ids:
            graph.add((node, SKOS.related, _uri(other)))
        for prop in concept.properties:
            pred = TKEIR[sanitize_rdf_class_name(prop.name, fallback="prop")]
            graph.add((node, pred, Literal(prop.value_type)))

    for relation in ontology.relations:
        graph.add(
            (
                _uri(relation.subject_id),
                TKEIR[
                    sanitize_rdf_class_name(
                        relation.predicate_id, fallback="related"
                    )
                ],
                _uri(relation.object_id),
            )
        )
    return graph


def ontology_to_shacl_ttl(ontology: Ontology) -> str:
    """Induce SHACL Turtle from the canonical ontology.

    Example:
        >>> from thot.ontology.model import Ontology, OntologyConcept
        >>> from thot.ontology.shacl import ontology_to_shacl_ttl
        >>> ttl = ontology_to_shacl_ttl(Ontology(concepts={
        ...     'C1': OntologyConcept('C1', preferred_label='K8s'),
        ... }))
        >>> 'sh:NodeShape' in ttl or 'sh:' in ttl
        True
    """
    from thot.tasks.document_ontology.ShaclInductor import (
        induce_document_shacl_shapes,
    )

    graph = ontology_to_rdf_graph(ontology)
    return induce_document_shacl_shapes(graph, alignment_report=None)


def validate_ontology(ontology: Ontology) -> dict[str, Any]:
    """Run pyshacl on the ontology graph using induced shapes.

    Example:
        >>> from thot.ontology.model import Ontology, OntologyConcept
        >>> from thot.ontology.shacl import validate_ontology
        >>> result = validate_ontology(Ontology(concepts={
        ...     'C1': OntologyConcept('C1', preferred_label='K8s'),
        ... }))
        >>> 'conforms' in result
        True
    """
    from thot.tasks.document_ontology.ShaclValidator import (
        validate_document_graph,
    )

    graph = ontology_to_rdf_graph(ontology)
    shapes_ttl = ontology_to_shacl_ttl(ontology)
    conforms, violations = validate_document_graph(
        graph, shapes_ttl=shapes_ttl
    )
    return {"conforms": bool(conforms), "violations": list(violations or [])}
