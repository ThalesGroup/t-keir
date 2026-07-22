"""Title: Ontology Repairer

Repair SHACL violations in document ontology graphs (rule-based only).

Author: Eric Blaudez

Copyright (c) 2026 Thales
Licensed under the MIT License.
"""

from __future__ import annotations

from collections.abc import Iterable

from rdflib import Graph, Literal, URIRef
from rdflib.namespace import RDF, RDFS, XSD

from thot.tasks.document_ontology.OntologyBuilder import NUMERIC_RE, TKEIR
from thot.tasks.document_ontology.OntologyVocabulary import METRIC_CLASS


def _local_name_from_uri(value: str) -> str:
    """Local name from uri helper.

    Example:
        >>> _local_name_from_uri('http://example.org#Person')
        'Person'
    """
    text = str(value).strip()
    if not text:
        return ""
    if "#" in text:
        return text.rsplit("#", 1)[-1]
    return text.rsplit("/", 1)[-1]


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


def _metric_nodes(graph: Graph) -> list[URIRef]:
    """Metric nodes helper.

    Example:
        >>> from thot.tasks.document_ontology.OntologyRepairer import _metric_nodes
        >>> callable(_metric_nodes)
        True
    """
    return _nodes_of_type(graph, TKEIR[METRIC_CLASS])


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


def _repair_missing_typed_link(
    graph: Graph,
    violations: Iterable[dict],
) -> None:
    """Add a missing typed object link for minCount shape violations.

    Example:
        >>> from rdflib import Graph, URIRef
        >>> from rdflib.namespace import RDF
        >>> from thot.tasks.document_ontology.OntologyBuilder import TKEIR
        >>> graph = Graph()
        >>> focus = URIRef('http://example.org/entity')
        >>> related = URIRef('http://example.org/related')
        >>> _ = graph.add((focus, RDF.type, TKEIR.Person))
        >>> _ = graph.add((related, RDF.type, TKEIR.Organization))
        >>> _ = graph.add((URIRef('http://example.org/other'), TKEIR.worksFor, related))
        >>> violations = [{'focus_node': str(focus), 'result_path': str(TKEIR.worksFor)}]
        >>> _repair_missing_typed_link(graph, violations)
        >>> (focus, TKEIR.worksFor, related) in graph
        True
    """
    for violation in violations:
        focus_text = str(violation.get("focus_node", "")).strip()
        result_path = _local_name_from_uri(
            str(violation.get("result_path", ""))
        )
        if not focus_text or not result_path:
            continue
        if result_path in {"hasNumericValue"}:
            continue
        focus_node = URIRef(focus_text)
        if graph.value(focus_node, RDF.type) is None:
            continue
        predicate = TKEIR[result_path]
        if any(graph.objects(focus_node, predicate)):
            continue
        for _subject, path, obj in graph:
            if path != predicate or not isinstance(obj, URIRef):
                continue
            if graph.value(obj, RDF.type) is None:
                continue
            graph.add((focus_node, predicate, obj))
            break


def _repair_numeric_values(
    graph: Graph,
    violations: Iterable[dict],
) -> None:
    """Repair numeric values helper.

    Example:
        >>> from rdflib import Graph, Literal, URIRef
        >>> from rdflib.namespace import RDF, RDFS
        >>> from thot.tasks.document_ontology.OntologyBuilder import TKEIR
        >>> graph = Graph()
        >>> metric = URIRef('http://example.org/metric')
        >>> _ = graph.add((metric, RDF.type, TKEIR.Metric))
        >>> _ = graph.add((metric, RDFS.label, Literal('12.5%')))
        >>> violations = [{'focus_node': str(metric), 'result_path': str(TKEIR.hasNumericValue)}]
        >>> _repair_numeric_values(graph, violations)
        >>> str(graph.value(metric, TKEIR.hasNumericValue))
        '12.5'
    """
    for violation in violations:
        result_path = _local_name_from_uri(
            str(violation.get("result_path", ""))
        )
        if result_path != "hasNumericValue":
            continue
        focus_text = str(violation.get("focus_node", "")).strip()
        if not focus_text:
            continue
        focus_node = URIRef(focus_text)
        if graph.value(focus_node, TKEIR.hasNumericValue) is not None:
            continue
        numeric = _infer_numeric_value(graph, focus_node)
        if numeric:
            graph.add(
                (
                    focus_node,
                    TKEIR.hasNumericValue,
                    Literal(numeric, datatype=XSD.decimal),
                )
            )


def apply_rule_based_repairs(
    graph: Graph, violations: Iterable[dict]
) -> Graph:
    """Apply deterministic repairs for known SHACL shape violations.

    Example:
        >>> from thot.tasks.document_ontology.OntologyRepairer import apply_rule_based_repairs
        >>> callable(apply_rule_based_repairs)
        True
    """
    violation_list = list(violations)
    _repair_numeric_values(graph, violation_list)
    _repair_missing_typed_link(graph, violation_list)
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
