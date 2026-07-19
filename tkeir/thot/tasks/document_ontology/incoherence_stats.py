"""Compact SHACL incoherence statistics for pipeline output."""

from __future__ import annotations

from collections import Counter

from rdflib import Graph, URIRef


def _local_name_from_uri(value: str) -> str:
    """Local name from uri helper.

    Example:
        >>> _local_name_from_uri('http://example.org/ns/hasNumericValue')
        'hasNumericValue'
    """
    text = str(value).strip()
    if not text:
        return ""
    if "#" in text:
        return text.rsplit("#", 1)[-1]
    return text.rsplit("/", 1)[-1]


def _graph_entity_nodes(graph: Graph | None) -> set[str]:
    """Graph entity nodes helper.

    Example:
        >>> from rdflib import Graph, URIRef
        >>> from rdflib.namespace import RDF
        >>> from thot.tasks.document_ontology.OntologyBuilder import TKEIR
        >>> graph = Graph()
        >>> node = URIRef('http://ex/a')
        >>> _ = graph.add((node, RDF.type, TKEIR.Person))
        >>> 'http://ex/a' in _graph_entity_nodes(graph)
        True
    """
    if graph is None:
        return set()
    nodes: set[str] = set()
    for subject, predicate, obj in graph:
        if isinstance(subject, URIRef):
            nodes.add(str(subject))
        if isinstance(obj, URIRef):
            nodes.add(str(obj))
    return nodes


def summarize_incoherences(
    violations: list[dict],
    graph: Graph | None = None,
) -> dict[str, object]:
    """Return compact incoherence statistics instead of full violation payloads.

    Example:
        >>> summarize_incoherences(
        ...     [{'focus_node': 'http://ex/a', 'result_path': 'http://tkeir#hasNumericValue', 'status': 'UNRESOLVED'}]
        ... )['total']
        1
    """
    unresolved = sum(
        1
        for violation in violations
        if violation.get("status") == "UNRESOLVED"
    )
    auto_fixed = sum(
        1
        for violation in violations
        if violation.get("status") == "AUTO_FIXED"
    )
    affected_nodes = {
        str(violation.get("focus_node", "")).strip()
        for violation in violations
        if str(violation.get("focus_node", "")).strip()
    }
    by_result_path: Counter[str] = Counter()
    by_severity: Counter[str] = Counter()
    for violation in violations:
        path = _local_name_from_uri(str(violation.get("result_path", "")))
        if path:
            by_result_path[path] += 1
        severity = _local_name_from_uri(
            str(violation.get("result_severity", ""))
        )
        if severity:
            by_severity[severity] += 1

    entity_nodes = _graph_entity_nodes(graph)
    return {
        "total": len(violations),
        "unresolved": unresolved,
        "auto_fixed": auto_fixed,
        "affected_node_count": len(affected_nodes),
        "graph_node_count": len(entity_nodes),
        "graph_triple_count": len(graph) if graph is not None else 0,
        "by_result_path": dict(sorted(by_result_path.items())),
        "by_severity": dict(sorted(by_severity.items())),
    }
