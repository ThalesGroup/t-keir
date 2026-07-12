# -*- coding: utf-8 -*-
"""Self-healing SHACL validation loop for document ontologies."""

from __future__ import annotations

from dataclasses import dataclass

from rdflib import Graph

from thot.core.ThotLogger import ThotLogger
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


def _public_violation(violation: dict, status: str) -> dict:
    """Public violation helper.

    Example:
        >>> _public_violation({'focus_node': 'n', 'message': 'm'}, 'AUTO_FIXED')
        {'focus_node': 'n', 'message': 'm', 'status': 'AUTO_FIXED'}
    """
    return {
        "focus_node": violation.get("focus_node", ""),
        "message": violation.get("message", ""),
        "status": status,
    }


def run_self_healing_validation(
    graph: Graph,
    settings: SelfHealingSettings | None = None,
    call_context=None,
) -> tuple[Graph, str, int, list[dict]]:
    """Validate and optionally repair the graph up to max_repair_attempts.

    Example:
        >>> from thot.tasks.document_ontology.SelfHealingLoop import run_self_healing_validation
        >>> callable(run_self_healing_validation)
        True
    """
    settings = settings or SelfHealingSettings()
    conforms, violations = validate_document_graph(
        graph, call_context=call_context
    )

    if conforms:
        return graph, "PASSED", 0, []

    correction_attempts = 0
    auto_fixed: list[dict] = []
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
        before_violations = list(remaining)
        graph = repair_graph(
            graph,
            remaining,
            call_context=call_context,
        )
        correction_attempts = attempt
        conforms, remaining = validate_document_graph(
            graph, call_context=call_context
        )
        after_keys = {_violation_key(violation) for violation in remaining}

        for violation in before_violations:
            key = _violation_key(violation)
            if key in before_keys and key not in after_keys:
                fixed = _public_violation(violation, "AUTO_FIXED")
                if fixed not in auto_fixed:
                    auto_fixed.append(fixed)

        if conforms:
            unresolved = [
                _public_violation(violation, "UNRESOLVED")
                for violation in remaining
            ]
            return (
                graph,
                "PASSED_AFTER_REPAIR",
                correction_attempts,
                unresolved + auto_fixed,
            )

    unresolved = [
        _public_violation(violation, "UNRESOLVED") for violation in remaining
    ]
    return (
        graph,
        "FAILED_WITH_INCOHERENCES",
        correction_attempts,
        unresolved + auto_fixed,
    )
