# -*- coding: utf-8 -*-
"""Validate document RDF graphs with SHACL."""

from __future__ import annotations

from rdflib import Graph
from rdflib.namespace import RDF, SH

from thot.core.ThotLogger import ThotLogger
from thot.tasks.document_ontology.ShaclShapes import DOCUMENT_SHACL_SHAPES_TTL


def parse_validation_report(report_graph: Graph | None) -> list[dict]:
    """Extract SHACL validation results from a pyshacl report graph.

    Example:
        >>> parse_validation_report(None)
        []
    """
    violations: list[dict] = []
    if report_graph is None:
        return violations

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
    return violations


def validate_document_graph(
    data_graph: Graph,
    call_context=None,
    shapes_ttl: str | None = None,
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
            abort_on_first=False,
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

    return bool(conforms), parse_validation_report(report_graph)
