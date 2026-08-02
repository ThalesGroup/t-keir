"""Title: Ontology reasoner queries over merged RAG graphs

Query a merged document ontology (JSON-LD from Vespa parents) with SPARQL
and the single ``python`` reasoner (coherence / hierarchy + class expressions).

Author: Eric Blaudez

Copyright (c) 2026 Thales
Licensed under the MIT License.
"""

from __future__ import annotations

from typing import Any
from typing import Literal as TypingLiteral

from rdflib import OWL, RDF, RDFS, Graph, Literal, URIRef

from thot.tools.search.ontology_utils import (
    detect_rdf_format,
    merge_rdf_graphs,
    serialize_graph_json_ld,
)

OntologyOperation = TypingLiteral[
    "consistency",
    "subclasses",
    "superclasses",
    "instances",
    "types",
    "sparql",
    "expression",
    "infer",
]

SUPPORTED_OPERATIONS: tuple[str, ...] = (
    "consistency",
    "subclasses",
    "superclasses",
    "instances",
    "types",
    "sparql",
    "expression",
    "infer",
)

DEFAULT_REASONER = "python"
SUPPORTED_REASONERS: tuple[str, ...] = ("python",)

TKEIR_REASON = "http://tkeir.local/reasoner/"
RDFS_NS = "http://www.w3.org/2000/01/rdf-schema#"
RDF_NS = "http://www.w3.org/1999/02/22-rdf-syntax-ns#"
OWL_NS = "http://www.w3.org/2002/07/owl#"


def _iri_ref(iri: str) -> URIRef:
    return URIRef(str(iri).strip())


def _init_result_set_graph(
    operation: str,
    *,
    hit_count: int,
    backend: str = "",
    reasoner: str = "",
) -> tuple[Graph, URIRef]:
    """Build an empty result-set graph with metadata triples."""
    graph = Graph()
    graph.bind("rdfs", RDFS)
    graph.bind("owl", OWL)
    graph.bind("tkeir", URIRef("http://tkeir.local/ontology/"))
    result_set = URIRef(f"{TKEIR_REASON}ResultSet")
    graph.add((result_set, RDF.type, URIRef(f"{TKEIR_REASON}QueryResult")))
    graph.add((result_set, RDFS.label, Literal(f"reasoner:{operation}")))
    if backend:
        graph.add(
            (
                result_set,
                URIRef(f"{TKEIR_REASON}backend"),
                Literal(backend),
            )
        )
    if reasoner:
        graph.add(
            (
                result_set,
                URIRef(f"{TKEIR_REASON}engine"),
                Literal(reasoner),
            )
        )
    graph.add(
        (
            result_set,
            URIRef(f"{TKEIR_REASON}operation"),
            Literal(operation),
        )
    )
    graph.add(
        (
            result_set,
            URIRef(f"{TKEIR_REASON}hitCount"),
            Literal(hit_count),
        )
    )
    return graph, result_set


def _add_focus_nodes(
    graph: Graph,
    result_set: URIRef,
    *,
    class_iri: str | None,
    individual_iri: str | None,
) -> tuple[URIRef | None, URIRef | None]:
    """Attach focus class / individual nodes to the result set."""
    focus_class = _iri_ref(class_iri) if class_iri else None
    focus_ind = _iri_ref(individual_iri) if individual_iri else None
    if focus_class is not None:
        graph.add((focus_class, RDF.type, OWL.Class))
        graph.add(
            (focus_class, RDFS.label, Literal(_local_name(str(focus_class))))
        )
        graph.add((result_set, URIRef(f"{TKEIR_REASON}focus"), focus_class))
    if focus_ind is not None:
        graph.add((focus_ind, RDF.type, OWL.NamedIndividual))
        graph.add(
            (focus_ind, RDFS.label, Literal(_local_name(str(focus_ind))))
        )
        graph.add((result_set, URIRef(f"{TKEIR_REASON}focus"), focus_ind))
    return focus_class, focus_ind


def _add_iri_hit(
    graph: Graph,
    result_set: URIRef,
    *,
    operation: str,
    iri: str,
    label: str,
    focus_class: URIRef | None,
    focus_ind: URIRef | None,
) -> None:
    """Add a typed IRI hit linked to the result set."""
    node = _iri_ref(iri)
    if operation in {"subclasses", "superclasses"}:
        graph.add((node, RDF.type, OWL.Class))
        if focus_class is not None:
            if operation == "subclasses":
                graph.add((node, RDFS.subClassOf, focus_class))
            else:
                graph.add((focus_class, RDFS.subClassOf, node))
    elif operation == "instances" and focus_class is not None:
        graph.add((node, RDF.type, focus_class))
        graph.add((node, RDF.type, OWL.NamedIndividual))
    elif operation == "types" and focus_ind is not None:
        graph.add((node, RDF.type, OWL.Class))
        graph.add((focus_ind, RDF.type, node))
    else:
        graph.add((node, RDF.type, OWL.Thing))
    if label:
        graph.add((node, RDFS.label, Literal(label)))
    graph.add((result_set, URIRef(f"{TKEIR_REASON}hit"), node))


def _add_spo_binding(
    graph: Graph,
    result_set: URIRef,
    *,
    index: int,
    subject: str,
    predicate: str,
    obj: str,
) -> None:
    """Add a compact SPO triple from SPARQL / generic bindings."""
    s_node = (
        _iri_ref(subject)
        if subject.startswith("http")
        else URIRef(f"{TKEIR_REASON}blank/{index}/s")
    )
    if subject.startswith("http"):
        pass
    else:
        graph.add((s_node, RDFS.label, Literal(subject)))
    p_node = (
        _iri_ref(predicate)
        if predicate.startswith("http")
        else URIRef(f"{TKEIR_REASON}pred/{_local_name(predicate)}")
    )
    if obj.startswith("http"):
        o_node: Any = _iri_ref(obj)
    else:
        o_node = Literal(obj)
    graph.add((s_node, p_node, o_node))
    graph.add((result_set, URIRef(f"{TKEIR_REASON}hit"), s_node))


def _add_binding_row_fallback(
    graph: Graph,
    result_set: URIRef,
    *,
    index: int,
    row: dict[str, str],
) -> None:
    """Fallback: one blank Binding node per tabular row."""
    blank = URIRef(f"{TKEIR_REASON}row/{index}")
    graph.add((blank, RDF.type, URIRef(f"{TKEIR_REASON}Binding")))
    for key, value in row.items():
        if value:
            graph.add(
                (
                    blank,
                    URIRef(f"{TKEIR_REASON}binding/{key}"),
                    Literal(value),
                )
            )
    graph.add((result_set, URIRef(f"{TKEIR_REASON}hit"), blank))


def results_as_json_ld(
    operation: str,
    *,
    results: list[dict[str, str]],
    class_iri: str | None = None,
    individual_iri: str | None = None,
    consistent: bool | None = None,
    backend: str = "",
    reasoner: str = "",
) -> str:
    """Serialize reasoner hits as a compact JSON-LD graph for HMI display.

    Args:
        operation: Reasoner operation name.
        results: Tabular hits (``iri``/``label`` or SPARQL bindings).
        class_iri: Focus class for hierarchy / instance ops.
        individual_iri: Focus individual for ``types``.
        consistent: Consistency flag when ``operation=consistency``.
        backend: Engine identifier recorded on the result set node.
        reasoner: Reasoner name recorded on the result set node.

    Returns:
        JSON-LD string (array of nodes).

    Example:
        >>> payload = results_as_json_ld(
        ...     "subclasses",
        ...     results=[{"iri": "http://ex/B", "label": "B"}],
        ...     class_iri="http://ex/A",
        ... )
        >>> '"@id": "http://ex/B"' in payload or '"@id":"http://ex/B"' in payload
        True
    """
    graph, result_set = _init_result_set_graph(
        operation,
        hit_count=len(results),
        backend=backend,
        reasoner=reasoner,
    )

    if operation == "consistency":
        flag = True if consistent is None else bool(consistent)
        graph.add(
            (
                result_set,
                URIRef(f"{TKEIR_REASON}consistent"),
                Literal(flag),
            )
        )
        return serialize_graph_json_ld(graph)

    focus_class, focus_ind = _add_focus_nodes(
        graph,
        result_set,
        class_iri=class_iri,
        individual_iri=individual_iri,
    )

    for index, row in enumerate(results):
        iri = (row.get("iri") or "").strip()
        label = (row.get("label") or "").strip()
        if iri:
            _add_iri_hit(
                graph,
                result_set,
                operation=operation,
                iri=iri,
                label=label,
                focus_class=focus_class,
                focus_ind=focus_ind,
            )
            continue

        # SPARQL / generic bindings → compact triples when s/p/o present.
        subject = (row.get("s") or row.get("subject") or "").strip()
        predicate = (row.get("p") or row.get("predicate") or "").strip()
        obj = (row.get("o") or row.get("object") or "").strip()
        if subject and predicate and obj:
            _add_spo_binding(
                graph,
                result_set,
                index=index,
                subject=subject,
                predicate=predicate,
                obj=obj,
            )
            continue

        _add_binding_row_fallback(graph, result_set, index=index, row=row)

    return serialize_graph_json_ld(graph)


def normalize_reasoner_name(reasoner: str | None) -> str:
    """Return ``python`` or raise if another reasoner name is requested.

    Example:
        >>> normalize_reasoner_name(None)
        'python'
        >>> normalize_reasoner_name("python")
        'python'
    """
    raw = (reasoner or DEFAULT_REASONER).strip().lower()
    if not raw:
        return DEFAULT_REASONER
    if raw == DEFAULT_REASONER:
        return DEFAULT_REASONER
    raise ValueError(
        f"unsupported reasoner {reasoner!r}; "
        f"only {DEFAULT_REASONER!r} is available"
    )


def _load_graph(payload: str) -> Graph:
    """Parse a single JSON-LD / Turtle payload into an rdflib graph."""
    text = (payload or "").strip()
    if not text or text == "[]":
        return Graph()
    return merge_rdf_graphs([text])


def _local_name(uri: str) -> str:
    text = str(uri)
    if "#" in text:
        return text.rsplit("#", 1)[-1]
    return text.rsplit("/", 1)[-1]


def _rdfs_related_classes(
    graph: Graph,
    class_iri: str,
    *,
    direction: TypingLiteral["sub", "super"],
    direct: bool,
    limit: int,
) -> list[dict[str, str]]:
    """Walk ``rdfs:subClassOf`` without a DL reasoner."""
    target = URIRef(class_iri)
    found: list[URIRef] = []
    if direction == "sub":
        # X subClassOf target → X is subclass
        for subject in graph.subjects(RDFS.subClassOf, target):
            if isinstance(subject, URIRef):
                found.append(subject)
    else:
        for obj in graph.objects(target, RDFS.subClassOf):
            if isinstance(obj, URIRef):
                found.append(obj)

    if not direct:
        # One-level expansion is enough for the lightweight fallback.
        frontier = list(found)
        seen = set(found)
        while frontier:
            current = frontier.pop()
            if direction == "sub":
                nxt = [
                    s
                    for s in graph.subjects(RDFS.subClassOf, current)
                    if isinstance(s, URIRef)
                ]
            else:
                nxt = [
                    o
                    for o in graph.objects(current, RDFS.subClassOf)
                    if isinstance(o, URIRef)
                ]
            for node in nxt:
                if node not in seen:
                    seen.add(node)
                    found.append(node)
                    frontier.append(node)

    results: list[dict[str, str]] = []
    for node in found[:limit]:
        results.append({"iri": str(node), "label": _local_name(str(node))})
    return results


def _sparql_select(
    graph: Graph,
    query: str,
    *,
    limit: int,
) -> list[dict[str, str]]:
    """Run a SPARQL SELECT and return row dicts (string values)."""
    capped = query.strip().rstrip(";")
    if "LIMIT" not in capped.upper():
        capped = f"{capped}\nLIMIT {max(1, limit)}"
    rows: list[dict[str, str]] = []
    for raw in graph.query(capped):
        labels = getattr(raw, "labels", None)
        if labels is None:
            continue
        binding: Any = raw
        row: dict[str, str] = {}
        for key in labels:
            value = binding[key]
            row[str(key)] = "" if value is None else str(value)
        rows.append(row)
        if len(rows) >= limit:
            break
    return rows


def _instances_python(
    graph: Graph, class_iri: str, *, limit: int
) -> list[dict[str, str]]:
    cls = URIRef(class_iri)
    out: list[dict[str, str]] = []
    for subject in graph.subjects(RDF.type, cls):
        if not isinstance(subject, URIRef):
            continue
        out.append({"iri": str(subject), "label": _local_name(str(subject))})
        if len(out) >= limit:
            break
    return out


def _types_python(
    graph: Graph, individual_iri: str, *, limit: int
) -> list[dict[str, str]]:
    ind = URIRef(individual_iri)
    out: list[dict[str, str]] = []
    for obj in graph.objects(ind, RDF.type):
        if not isinstance(obj, URIRef):
            continue
        out.append({"iri": str(obj), "label": _local_name(str(obj))})
        if len(out) >= limit:
            break
    return out


def _query_with_python(
    graph: Graph,
    *,
    operation: OntologyOperation,
    class_iri: str | None,
    individual_iri: str | None,
    sparql: str | None,
    expression: str | None = None,
    direct: bool,
    limit: int,
) -> dict[str, Any]:
    """Single pure-Python reasoner (coherence + hierarchy + expressions)."""
    from thot.tools.search.python_reasoner import (
        check_coherence,
        evaluate_expression,
    )

    backend = "python"

    if operation == "consistency":
        return check_coherence(graph, limit=limit)

    if operation == "expression":
        expr = (expression or sparql or "").strip()
        if not expr:
            raise ValueError(
                "expression requires a non-empty Manchester-like string "
                "(e.g. 'Person and age > 20')"
            )
        return evaluate_expression(graph, expr, limit=limit)

    if operation == "sparql":
        if not sparql or not sparql.strip():
            raise ValueError("sparql operation requires a non-empty query")
        rows = _sparql_select(graph, sparql, limit=limit)
        return {
            "operation": operation,
            "backend": backend,
            "results": rows,
            "count": len(rows),
        }

    if operation in {"subclasses", "superclasses"}:
        if not class_iri:
            raise ValueError(f"{operation} requires class_iri")
        direction: TypingLiteral["sub", "super"] = (
            "sub" if operation == "subclasses" else "super"
        )
        results = _rdfs_related_classes(
            graph,
            class_iri,
            direction=direction,
            direct=direct,
            limit=limit,
        )
        return {
            "operation": operation,
            "backend": backend,
            "results": results,
            "count": len(results),
            "note": "RDFS hierarchy walk (pure Python).",
        }

    if operation == "instances":
        if not class_iri:
            raise ValueError("instances requires class_iri")
        results = _instances_python(graph, class_iri, limit=limit)
        return {
            "operation": operation,
            "backend": backend,
            "results": results,
            "count": len(results),
        }

    if operation == "types":
        if not individual_iri:
            raise ValueError("types requires individual_iri")
        results = _types_python(graph, individual_iri, limit=limit)
        return {
            "operation": operation,
            "backend": backend,
            "results": results,
            "count": len(results),
        }

    if operation == "infer":
        # Materialize rdfs:subClassOf transitive closure into a result note.
        inferred = 0
        for cls in list(graph.subjects(RDF.type, OWL.Class)):
            for parent in graph.transitive_objects(cls, RDFS.subClassOf):
                if parent != cls:
                    inferred += 1
        return {
            "operation": operation,
            "backend": backend,
            "results": [{"inferred_subclass_links": str(inferred)}],
            "count": inferred,
            "note": "RDFS transitive subclass materialization count.",
        }

    raise ValueError(f"unsupported operation: {operation}")


def query_merged_ontology(
    json_ld: str,
    *,
    operation: OntologyOperation | str = "sparql",
    class_iri: str | None = None,
    individual_iri: str | None = None,
    sparql: str | None = None,
    expression: str | None = None,
    reasoner: str = DEFAULT_REASONER,
    direct: bool = False,
    limit: int = 50,
    extra_json_ld: str | None = None,
) -> dict[str, Any]:
    """Query a merged ontology with the ``python`` reasoner.

    Args:
        json_ld: Fused ontology ``json_ld`` (JSON-LD or Turtle also accepted).
        operation: One of :data:`SUPPORTED_OPERATIONS`.
        class_iri: Class IRI for hierarchy / instance queries.
        individual_iri: Individual IRI for ``types``.
        sparql: SPARQL SELECT string for ``sparql``.
        expression: Manchester-like expression for ``expression``.
        reasoner: Must be ``python`` (the only supported engine).
        direct: Restrict hierarchy to direct relations when supported.
        limit: Max rows / individuals returned.
        extra_json_ld: Optional business-ontology JSON-LD merged before query.

    Returns:
        Dict with ``operation``, ``backend``, ``reasoner``, ``results``.
    """
    op = str(operation).strip().lower()
    if op not in SUPPORTED_OPERATIONS:
        raise ValueError(
            f"unsupported operation {operation!r}; "
            f"expected one of {SUPPORTED_OPERATIONS}"
        )
    payloads = [json_ld]
    if extra_json_ld and str(extra_json_ld).strip():
        payloads.append(str(extra_json_ld))
    graph = (
        merge_rdf_graphs(payloads)
        if len(payloads) > 1
        else _load_graph(json_ld)
    )
    chosen = normalize_reasoner_name(reasoner)
    meta = {
        "triple_count": len(graph),
        "input_format": detect_rdf_format(json_ld) if json_ld.strip() else "",
        "reasoner": chosen,
    }
    if len(graph) == 0:
        return {
            "operation": op,
            "backend": "none",
            "results": [],
            "count": 0,
            "note": "empty ontology payload",
            "json_ld": results_as_json_ld(
                op,
                results=[],
                class_iri=class_iri,
                individual_iri=individual_iri,
                backend="none",
                reasoner=chosen,
            ),
            **meta,
        }

    result = _query_with_python(
        graph,
        operation=op,  # type: ignore[arg-type]
        class_iri=class_iri,
        individual_iri=individual_iri,
        sparql=sparql,
        expression=expression,
        direct=direct,
        limit=limit,
    )

    result.update(meta)
    result["reasoner"] = chosen
    if not result.get("json_ld"):
        result["json_ld"] = results_as_json_ld(
            op,
            results=list(result.get("results") or []),
            class_iri=class_iri,
            individual_iri=individual_iri,
            consistent=result.get("consistent"),
            backend=str(result.get("backend") or ""),
            reasoner=str(result.get("reasoner") or ""),
        )
    return result
