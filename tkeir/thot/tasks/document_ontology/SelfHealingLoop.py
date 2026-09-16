"""Title: Self Healing Loop

Self-healing SHACL validation loop for document ontologies.

Author: Eric Blaudez

Copyright (c) 2026 Thales
Licensed under the MIT License.
"""

from __future__ import annotations

from dataclasses import dataclass
from time import monotonic

from rdflib import Graph

from thot.core.ThotLogger import ThotLogger
from thot.tasks.document_ontology.incoherence_stats import (
    summarize_incoherences,
)
from thot.tasks.document_ontology.OntologyRepairer import repair_graph
from thot.tasks.document_ontology.ShaclValidator import (
    collect_min_count_violations,
    validate_document_graph,
)


@dataclass
class SelfHealingSettings:
    """Caps for SHACL validate/repair so large documents stay fast.

    Example:
        >>> SelfHealingSettings().max_violations_to_repair
        48
    """

    max_repair_attempts: int = 2
    max_violations_to_repair: int = 48
    max_graph_triples: int = 12000
    max_seconds: float = 8.0


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


def _skip_summary(
    *,
    reason: str,
    graph: Graph,
    violations: list[dict] | None = None,
    cap: int = 0,
) -> dict[str, object]:
    """Compact summary when healing is skipped.

    Example:
        >>> from rdflib import Graph
        >>> _skip_summary(reason="too_large", graph=Graph())["heal_skipped"]
        'too_large'
    """
    marked = [
        {**row, "status": "UNRESOLVED"} for row in (violations or [])[:cap]
    ]
    summary = summarize_incoherences(marked, None)
    summary["heal_skipped"] = reason
    summary["graph_triple_count"] = len(graph)
    if violations is not None and cap and len(violations) > cap:
        summary["truncated"] = True
        summary["unresolved"] = max(
            int(str(summary.get("unresolved") or 0)), cap
        )
    return summary


def _auto_fixed_rows(keys: set[tuple[str, str, str]]) -> list[dict]:
    """Serialize auto-fixed violation keys.

    Example:
        >>> _auto_fixed_rows({("a", "b", "c")})[0]["status"]
        'AUTO_FIXED'
    """
    return [
        {
            "focus_node": focus_node,
            "result_path": result_path,
            "message": message,
            "status": "AUTO_FIXED",
        }
        for focus_node, result_path, message in keys
    ]


def _passed_after_repair(graph, attempts, keys):
    """Build a PASSED_AFTER_REPAIR result tuple.

    Example:
        >>> callable(_passed_after_repair)
        True
    """
    return (
        graph,
        "PASSED_AFTER_REPAIR",
        attempts,
        summarize_incoherences(_auto_fixed_rows(keys), graph),
    )


def _heal_min_count(
    graph: Graph,
    settings: SelfHealingSettings,
    shapes_ttl: str | None,
    cap: int,
    parse_cap: int | None,
    call_context,
):
    """Apply minCount repairs or skip when the gap count exceeds ``cap``.

    Example:
        >>> callable(_heal_min_count)
        True
    """
    if cap <= 0:
        return graph, 0, set(), None
    min_count_gaps = collect_min_count_violations(
        graph,
        shapes_ttl=shapes_ttl,
        max_results=parse_cap,
    )
    if len(min_count_gaps) > cap:
        ThotLogger.info(
            "Document ontology self-healing skipped: "
            + str(len(min_count_gaps))
            + "+ minCount gap(s) (cap "
            + str(cap)
            + "); pyshacl not run",
            context=call_context,
        )
        skipped = (
            graph,
            "SKIPPED_TOO_MANY_VIOLATIONS",
            0,
            _skip_summary(
                reason="too_many_violations",
                graph=graph,
                violations=min_count_gaps,
                cap=cap,
            ),
        )
        return graph, 0, set(), skipped
    if not min_count_gaps:
        return graph, 0, set(), None
    graph = repair_graph(graph, min_count_gaps, call_context=call_context)
    return graph, 1, {_violation_key(row) for row in min_count_gaps}, None


def _heal_repair_loop(
    graph: Graph,
    remaining: list,
    settings: SelfHealingSettings,
    shapes_ttl: str | None,
    cap: int,
    parse_cap: int | None,
    deadline: float,
    correction_attempts: int,
    auto_fixed_keys: set[tuple[str, str, str]],
    call_context,
):
    """Run remaining SHACL repair attempts.

    Example:
        >>> callable(_heal_repair_loop)
        True
    """
    for attempt in range(
        correction_attempts + 1, settings.max_repair_attempts + 1
    ):
        if not remaining:
            break
        if monotonic() > deadline:
            ThotLogger.info(
                "Document ontology self-healing stopped: time budget "
                + str(settings.max_seconds)
                + "s",
                context=call_context,
            )
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
        graph = repair_graph(graph, remaining[:cap], call_context=call_context)
        correction_attempts = attempt
        conforms, remaining = validate_document_graph(
            graph,
            call_context=call_context,
            shapes_ttl=shapes_ttl,
            max_violations=parse_cap,
        )
        auto_fixed_keys |= before_keys - {
            _violation_key(violation) for violation in remaining
        }
        if conforms:
            return _passed_after_repair(
                graph, correction_attempts, auto_fixed_keys
            )
        if len(remaining) > cap:
            ThotLogger.info(
                "Document ontology self-healing stopped: still "
                + str(len(remaining))
                + " violation(s) after repair",
                context=call_context,
            )
            break
    summary_violations = [
        {**violation, "status": "UNRESOLVED"} for violation in remaining[:cap]
    ]
    summary_violations.extend(_auto_fixed_rows(auto_fixed_keys))
    return (
        graph,
        "FAILED_WITH_INCOHERENCES",
        correction_attempts,
        summarize_incoherences(summary_violations, graph),
    )


def run_self_healing_validation(
    graph: Graph,
    settings: SelfHealingSettings | None = None,
    shapes_ttl: str | None = None,
    call_context=None,
) -> tuple[Graph, str, int, dict[str, object]]:
    """Validate and optionally repair the graph up to max_repair_attempts.

    Large graphs and high violation counts skip the repair loop so ingest
    does not stall. Returns
    ``(graph, status, correction_attempts, incoherence_summary)``.

    Example:
        >>> from rdflib import Graph, URIRef
        >>> from thot.tasks.document_ontology.SelfHealingLoop import (
        ...     SelfHealingSettings,
        ...     run_self_healing_validation,
        ... )
        >>> g = Graph()
        >>> _ = g.add((URIRef("http://ex/a"), URIRef("http://ex/p"), URIRef("http://ex/b")))
        >>> _graph, status, attempts, _summary = run_self_healing_validation(
        ...     g,
        ...     settings=SelfHealingSettings(max_graph_triples=0),
        ... )
        >>> status
        'SKIPPED_TOO_LARGE'
        >>> attempts
        0
    """
    settings = settings or SelfHealingSettings()
    triple_count = len(graph)
    if triple_count > settings.max_graph_triples:
        ThotLogger.info(
            "Document ontology SHACL skipped: graph has "
            + str(triple_count)
            + " triples (cap "
            + str(settings.max_graph_triples)
            + ")",
            context=call_context,
        )
        return (
            graph,
            "SKIPPED_TOO_LARGE",
            0,
            _skip_summary(reason="too_large", graph=graph),
        )

    cap = max(0, int(settings.max_violations_to_repair))
    deadline = monotonic() + max(0.1, float(settings.max_seconds))
    parse_cap = cap + 1 if cap else None
    graph, correction_attempts, auto_fixed_keys, skipped = _heal_min_count(
        graph, settings, shapes_ttl, cap, parse_cap, call_context
    )
    if skipped is not None:
        return skipped

    conforms, remaining = validate_document_graph(
        graph,
        call_context=call_context,
        shapes_ttl=shapes_ttl,
        abort_on_first=False,
        max_violations=parse_cap,
    )
    if conforms and correction_attempts:
        return _passed_after_repair(
            graph, correction_attempts, auto_fixed_keys
        )
    if conforms:
        return graph, "PASSED", 0, summarize_incoherences([], graph)
    if cap == 0 or len(remaining) > cap:
        ThotLogger.info(
            "Document ontology self-healing skipped: "
            + str(len(remaining))
            + " violation(s) (cap "
            + str(cap)
            + ")",
            context=call_context,
        )
        return (
            graph,
            "SKIPPED_TOO_MANY_VIOLATIONS",
            correction_attempts,
            _skip_summary(
                reason="too_many_violations",
                graph=graph,
                violations=remaining,
                cap=cap,
            ),
        )
    return _heal_repair_loop(
        graph,
        remaining,
        settings,
        shapes_ttl,
        cap,
        parse_cap,
        deadline,
        correction_attempts,
        auto_fixed_keys,
        call_context,
    )
