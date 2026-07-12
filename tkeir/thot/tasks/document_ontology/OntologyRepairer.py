# -*- coding: utf-8 -*-
"""Repair SHACL violations in document ontology graphs (rule-based only)."""

from __future__ import annotations

from typing import Iterable

from rdflib import Graph, Literal, URIRef
from rdflib.namespace import RDF, RDFS, XSD

from thot.tasks.document_ontology.OntologyBuilder import NUMERIC_RE, TKEIR

_OWNERSHIP_PREDICATES = (
    TKEIR.ownedBy,
    TKEIR.createdBy,
    TKEIR.publishedBy,
)


def merge_repair_ttl(graph: Graph, repair_ttl: str) -> Graph:
    """Parse repaired Turtle and merge triples into the live graph.

    Example:
        >>> from rdflib import Graph, Literal, URIRef
        >>> from thot.tasks.document_ontology.OntologyBuilder import TKEIR
        >>> graph = Graph()
        >>> node = URIRef('http://example.org/a')
        >>> _ = graph.add((node, TKEIR.hasNumericValue, Literal('1')))
        >>> len(list(merge_repair_ttl(graph, '')))
        1
    """
    if not repair_ttl.strip():
        return graph
    patch = Graph()
    patch.parse(data=repair_ttl, format="turtle")
    for triple in patch:
        graph.add(triple)
    return graph


def _nodes_of_type(graph: Graph, class_uri: URIRef) -> list[URIRef]:
    """Nodes of type helper.

    Example:
        >>> from thot.tasks.document_ontology.OntologyRepairer import _nodes_of_type
        >>> callable(_nodes_of_type)
        True
    """
    return [URIRef(node) for node in graph.subjects(RDF.type, class_uri)]


def _label_for_node(graph: Graph, node: URIRef) -> str:
    """Label for node helper.

    Example:
        >>> from thot.tasks.document_ontology.OntologyRepairer import _label_for_node
        >>> callable(_label_for_node)
        True
    """
    label = graph.value(node, RDFS.label)
    return str(label) if label is not None else ""


def _has_company_relation(graph: Graph, product: URIRef) -> bool:
    """Has company relation helper.

    Example:
        >>> from thot.tasks.document_ontology.OntologyRepairer import _has_company_relation
        >>> callable(_has_company_relation)
        True
    """
    for predicate in _OWNERSHIP_PREDICATES:
        for company in graph.objects(product, predicate):
            if (company, RDF.type, TKEIR.Company) in graph:
                return True
    return False


def _company_nodes(graph: Graph) -> list[URIRef]:
    """Company nodes helper.

    Example:
        >>> from thot.tasks.document_ontology.OntologyRepairer import _company_nodes
        >>> callable(_company_nodes)
        True
    """
    return _nodes_of_type(graph, TKEIR.Company)


def _metric_nodes(graph: Graph) -> list[URIRef]:
    """Metric nodes helper.

    Example:
        >>> from thot.tasks.document_ontology.OntologyRepairer import _metric_nodes
        >>> callable(_metric_nodes)
        True
    """
    return _nodes_of_type(graph, TKEIR.Metric)


def _parse_numeric_literal(text: str) -> str | None:
    """Parse numeric literal helper.

    Example:
        >>> _parse_numeric_literal('12.5%')
        '12.5'
    """
    cleaned = text.replace(",", "").replace("%", "").strip()
    if NUMERIC_RE.match(cleaned):
        return cleaned
    return None


def _infer_numeric_value(graph: Graph, node: URIRef) -> str | None:
    """Infer numeric value helper.

    Example:
        >>> from thot.tasks.document_ontology.OntologyRepairer import _infer_numeric_value
        >>> callable(_infer_numeric_value)
        True
    """
    existing = graph.value(node, TKEIR.hasNumericValue)
    if existing is not None:
        return str(existing)
    label_value = _parse_numeric_literal(_label_for_node(graph, node))
    if label_value:
        return label_value
    for _subject, _predicate, obj in graph.triples((node, None, None)):
        if isinstance(obj, Literal):
            parsed = _parse_numeric_literal(str(obj))
            if parsed:
                return parsed
    for _subject, _predicate, obj in graph.triples((None, None, node)):
        if isinstance(obj, Literal):
            parsed = _parse_numeric_literal(str(obj))
            if parsed:
                return parsed
    return None


def apply_rule_based_repairs(
    graph: Graph, violations: Iterable[dict]
) -> Graph:
    """Apply deterministic repairs for known SHACL shape violations.

    Example:
        >>> from thot.tasks.document_ontology.OntologyRepairer import apply_rule_based_repairs
        >>> callable(apply_rule_based_repairs)
        True
    """
    messages = " ".join(
        violation.get("message", "") for violation in violations
    )

    if "Product must be owned or created by a Company" in messages:
        companies = _company_nodes(graph)
        if companies:
            company = companies[0]
            for product in _nodes_of_type(graph, TKEIR.Product):
                if not _has_company_relation(graph, product):
                    graph.add((product, TKEIR.createdBy, company))

    if "numeric object target" in messages.lower():
        for metric in _metric_nodes(graph):
            if graph.value(metric, TKEIR.hasNumericValue) is None:
                numeric = _infer_numeric_value(graph, metric)
                if numeric:
                    graph.add(
                        (
                            metric,
                            TKEIR.hasNumericValue,
                            Literal(numeric, datatype=XSD.decimal),
                        )
                    )

    return graph


def repair_graph(
    graph: Graph,
    violations: list[dict],
    call_context=None,
) -> Graph:
    """Apply rule-based SHACL repairs without LLM calls.

    Example:
        >>> from thot.tasks.document_ontology.OntologyRepairer import repair_graph
        >>> callable(repair_graph)
        True
    """
    return apply_rule_based_repairs(graph, violations)
