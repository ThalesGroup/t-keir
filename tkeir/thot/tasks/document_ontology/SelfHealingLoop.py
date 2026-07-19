"""Self-healing SHACL validation loop for document ontologies."""

from __future__ import annotations

from dataclasses import dataclass

from rdflib import Graph

from thot.core.ThotLogger import ThotLogger
from thot.tasks.document_ontology.incoherence_stats import (
    summarize_incoherences,
)
from thot.tasks.document_ontology.OntologyRepairer import repair_graph
from thot.tasks.document_ontology.ShaclValidator import validate_document_graph


@dataclass
class SelfHealingSettings:
    max_repair_attempts: int = 2


def _violation_key(violation: dict) -> tuple[str, str, str]:
    """Violation key helper.

    Example:
        >>> _violation_key({'focus_node': 'a', 'result_path': 'b', 'message': 'c'})
        ('a', 'b', 'c')
    """
    return (
        violation.get("focus_node", ""),
        violation.get("result_path", ""),
        violation.get("message", ""),
    )


def run_self_healing_validation(
    graph: Graph,
    settings: SelfHealingSettings | None = None,
    shapes_ttl: str | None = None,
    call_context=None,
) -> tuple[Graph, str, int, dict[str, object]]:
    """Validate and optionally repair the graph up to max_repair_attempts.

    Returns:
        Tuple of ``(graph, status, correction_attempts, incoherence_summary)``.

    Example:
        >>> from thot.tasks.document_ontology.SelfHealingLoop import run_self_healing_validation
        >>> callable(run_self_healing_validation)
        True
    """
    settings = settings or SelfHealingSettings()
    conforms, violations = validate_document_graph(
        graph,
        call_context=call_context,
        shapes_ttl=shapes_ttl,
    )

    if conforms:
        return graph, "PASSED", 0, summarize_incoherences([], graph)

    correction_attempts = 0
    auto_fixed_keys: set[tuple[str, str, str]] = set()
    remaining = violations

    for attempt in range(1, settings.max_repair_attempts + 1):
        if not remaining:
            break

        ThotLogger.info(
            "Document ontology self-healing attempt "
            + str(attempt)
            + "/"
            + str(settings.max_repair_attempts)
            + " ("
            + str(len(remaining))
            + " violation(s))",
            context=call_context,
        )

        before_keys = {_violation_key(violation) for violation in remaining}
        graph = repair_graph(
            graph,
            remaining,
            call_context=call_context,
        )
        correction_attempts = attempt
        conforms, remaining = validate_document_graph(
            graph,
            call_context=call_context,
            shapes_ttl=shapes_ttl,
        )
        after_keys = {_violation_key(violation) for violation in remaining}
        auto_fixed_keys |= before_keys - after_keys

        if conforms:
            summary_violations = [
                {
                    "focus_node": focus_node,
                    "result_path": result_path,
                    "message": message,
                    "status": "AUTO_FIXED",
                }
                for focus_node, result_path, message in auto_fixed_keys
            ]
            return (
                graph,
                "PASSED_AFTER_REPAIR",
                correction_attempts,
                summarize_incoherences(summary_violations, graph),
            )

    summary_violations = [
        {**violation, "status": "UNRESOLVED"} for violation in remaining
    ]
    for key in auto_fixed_keys:
        focus_node, result_path, message = key
        summary_violations.append(
            {
                "focus_node": focus_node,
                "result_path": result_path,
                "message": message,
                "status": "AUTO_FIXED",
            }
        )
    return (
        graph,
        "FAILED_WITH_INCOHERENCES",
        correction_attempts,
        summarize_incoherences(summary_violations, graph),
    )
