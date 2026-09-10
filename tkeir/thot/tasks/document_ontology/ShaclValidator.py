"""Title: Shacl Validator

Validate document RDF graphs with SHACL.

Author: Eric Blaudez

Copyright (c) 2026 Thales
Licensed under the MIT License.
"""

from __future__ import annotations

from rdflib import Graph, URIRef
from rdflib.namespace import RDF, SH

from thot.core.ThotLogger import ThotLogger
from thot.tasks.document_ontology.ShaclShapes import DOCUMENT_SHACL_SHAPES_TTL


def parse_validation_report(
    report_graph: Graph | None,
    max_results: int | None = None,
) -> list[dict]:
    """Extract SHACL validation results from a pyshacl report graph.

    Example:
        >>> parse_validation_report(None)
        []
    """
    violations: list[dict] = []
    if report_graph is None:
        return violations

    limit = (
        max_results if max_results is not None and max_results > 0 else None
    )
    for result in report_graph.subjects(RDF.type, SH.ValidationResult):
        focus_node = report_graph.value(result, SH.focusNode)
        result_path = report_graph.value(result, SH.resultPath)
        value = report_graph.value(result, SH.value)
        severity = report_graph.value(result, SH.resultSeverity)
        source_shape = report_graph.value(result, SH.sourceShape)
        message = report_graph.value(result, SH.resultMessage)
        violations.append(
            {
                "focus_node": str(focus_node) if focus_node else "",
                "result_path": str(result_path) if result_path else "",
                "value": str(value) if value is not None else "",
                "result_severity": str(severity) if severity else "",
                "source_shape": str(source_shape) if source_shape else "",
                "message": str(message) if message else "",
            }
        )
        if limit is not None and len(violations) >= limit:
            break
    return violations


def collect_min_count_violations(
    data_graph: Graph,
    shapes_ttl: str | None = None,
    max_results: int | None = None,
) -> list[dict]:
    """List focus nodes missing a ``sh:minCount`` property (capped).

    Walks induced node shapes in linear time over rdf:type triples. Used to
    skip or repair before a full pyshacl report on large documents.

    Example:
        >>> from rdflib import Graph, URIRef
        >>> from rdflib.namespace import RDF
        >>> from thot.tasks.document_ontology.OntologyBuilder import TKEIR
        >>> from thot.tasks.document_ontology.ShaclValidator import (
        ...     collect_min_count_violations,
        ... )
        >>> graph = Graph()
        >>> person = URIRef("http://ex/p")
        >>> _ = graph.add((person, RDF.type, TKEIR.Person))
        >>> shapes = (
        ...     "@prefix sh: <http://www.w3.org/ns/shacl#> ."
        ...     " @prefix tkeir: <http://tkeir.local/ontology/> ."
        ...     " tkeir:PersonShape a sh:NodeShape ;"
        ...     " sh:targetClass tkeir:Person ;"
        ...     " sh:property [ sh:path tkeir:worksFor ; sh:minCount 1 ] ."
        ... )
        >>> rows = collect_min_count_violations(graph, shapes, max_results=2)
        >>> len(rows)
        1
        >>> rows[0]["focus_node"]
        'http://ex/p'
    """
    shapes_graph = Graph()
    try:
        shapes_graph.parse(
            data=shapes_ttl or DOCUMENT_SHACL_SHAPES_TTL,
            format="turtle",
        )
    except Exception:
        return []

    instances_by_type: dict[URIRef, list[URIRef]] = {}
    for subject, _pred, obj in data_graph.triples((None, RDF.type, None)):
        if isinstance(subject, URIRef) and isinstance(obj, URIRef):
            instances_by_type.setdefault(obj, []).append(subject)

    limit = (
        max_results if max_results is not None and max_results > 0 else None
    )
    violations: list[dict] = []
    for shape in shapes_graph.subjects(RDF.type, SH.NodeShape):
        target = shapes_graph.value(shape, SH.targetClass)
        if not isinstance(target, URIRef):
            continue
        for prop_node in shapes_graph.objects(shape, SH.property):
            path = shapes_graph.value(prop_node, SH.path)
            min_count = shapes_graph.value(prop_node, SH.minCount)
            if path is None or min_count is None:
                continue
            try:
                need = int(min_count)
            except (TypeError, ValueError):
                continue
            if need < 1:
                continue
            for node in instances_by_type.get(target, ()):
                held = 0
                for _obj in data_graph.objects(node, path):
                    held += 1
                    if held >= need:
                        break
                if held >= need:
                    continue
                violations.append(
                    {
                        "focus_node": str(node),
                        "result_path": str(path),
                        "value": "",
                        "result_severity": str(SH.Violation),
                        "source_shape": str(shape),
                        "message": "minCount " + str(need),
                    }
                )
                if limit is not None and len(violations) >= limit:
                    return violations
    return violations


def validate_document_graph(
    data_graph: Graph,
    call_context=None,
    shapes_ttl: str | None = None,
    abort_on_first: bool = False,
    max_violations: int | None = None,
) -> tuple[bool, list[dict]]:
    """Validate a document graph; returns (conforms, violations).

    Example:
        >>> from thot.tasks.document_ontology.ShaclValidator import validate_document_graph
        >>> callable(validate_document_graph)
        True
    """
    shapes_graph = Graph()
    shapes_graph.parse(
        data=shapes_ttl or DOCUMENT_SHACL_SHAPES_TTL,
        format="turtle",
    )

    try:
        import pyshacl
    except ImportError as error:
        ThotLogger.warning(
            "pyshacl is not installed; skipping SHACL validation",
            context=call_context,
        )
        return False, [
            {
                "focus_node": "",
                "result_path": "",
                "value": "",
                "result_severity": "sh:Warning",
                "source_shape": "",
                "message": "SHACL validation skipped: " + str(error),
            }
        ]

    try:
        conforms, report_graph, _report_text = pyshacl.validate(
            data_graph,
            shacl_graph=shapes_graph,
            inference="none",
            abort_on_first=bool(abort_on_first),
            allow_warnings=True,
        )
    except Exception as error:
        ThotLogger.warning(
            "SHACL validation raised an exception",
            context=call_context,
        )
        return False, [
            {
                "focus_node": "",
                "result_path": "",
                "value": "",
                "result_severity": "sh:Violation",
                "source_shape": "",
                "message": "SHACL validation error: " + str(error),
            }
        ]

    return bool(conforms), parse_validation_report(
        report_graph, max_results=max_violations
    )
