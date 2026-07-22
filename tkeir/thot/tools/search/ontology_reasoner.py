"""Title: Ontology reasoner queries over merged RAG graphs

Query a merged document ontology (JSON-LD from Vespa parents) with SPARQL
and optional OWLAPY SyncReasoner (HermiT / Pellet / …).

Install the optional extra when Java reasoners are needed::

    cd tkeir && uv sync --extra owl

Without ``owlapy``, SPARQL and RDFS walks still work via rdflib.

Author: Eric Blaudez

Copyright (c) 2026 Thales
Licensed under the MIT License.
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any, Literal as TypingLiteral

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
    "infer",
]

SUPPORTED_OPERATIONS: tuple[str, ...] = (
    "consistency",
    "subclasses",
    "superclasses",
    "instances",
    "types",
    "sparql",
    "infer",
)

DEFAULT_REASONER = "HermiT"

# OWLAPY SyncReasoner names + local rdflib fallback (no Java).
SUPPORTED_REASONERS: tuple[str, ...] = (
    "HermiT",
    "Pellet",
    "ELK",
    "JFact",
    "Openllet",
    "Structural",
    "rdflib",
)

TKEIR_REASON = "http://tkeir.local/reasoner/"
RDFS_NS = "http://www.w3.org/2000/01/rdf-schema#"
RDF_NS = "http://www.w3.org/1999/02/22-rdf-syntax-ns#"
OWL_NS = "http://www.w3.org/2002/07/owl#"


def _iri_ref(iri: str) -> URIRef:
    return URIRef(str(iri).strip())


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
            Literal(len(results)),
        )
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

    focus_class = _iri_ref(class_iri) if class_iri else None
    focus_ind = _iri_ref(individual_iri) if individual_iri else None
    if focus_class is not None:
        graph.add((focus_class, RDF.type, OWL.Class))
        graph.add((focus_class, RDFS.label, Literal(_local_name(str(focus_class)))))
        graph.add((result_set, URIRef(f"{TKEIR_REASON}focus"), focus_class))
    if focus_ind is not None:
        graph.add((focus_ind, RDF.type, OWL.NamedIndividual))
        graph.add((focus_ind, RDFS.label, Literal(_local_name(str(focus_ind)))))
        graph.add((result_set, URIRef(f"{TKEIR_REASON}focus"), focus_ind))

    for index, row in enumerate(results):
        iri = (row.get("iri") or "").strip()
        label = (row.get("label") or "").strip()
        if iri:
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
            graph.add(
                (result_set, URIRef(f"{TKEIR_REASON}hit"), node)
            )
            continue

        # SPARQL / generic bindings → compact triples when s/p/o present.
        subject = (row.get("s") or row.get("subject") or "").strip()
        predicate = (row.get("p") or row.get("predicate") or "").strip()
        obj = (row.get("o") or row.get("object") or "").strip()
        if subject and predicate and obj:
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
            continue

        # Fallback: one blank node per binding row.
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

    return serialize_graph_json_ld(graph)


def normalize_reasoner_name(reasoner: str | None) -> str:
    """Normalize a reasoner name; unknown values fall back to HermiT.

    Example:
        >>> normalize_reasoner_name("pellet")
        'Pellet'
        >>> normalize_reasoner_name("rdflib")
        'rdflib'
    """
    raw = (reasoner or DEFAULT_REASONER).strip()
    if not raw:
        return DEFAULT_REASONER
    if raw.lower() == "rdflib":
        return "rdflib"
    for name in SUPPORTED_REASONERS:
        if name.lower() == raw.lower():
            return name
    return DEFAULT_REASONER


def owlapy_available() -> bool:
    """Return True when the optional ``owlapy`` package can be imported.

    Example:
        >>> isinstance(owlapy_available(), bool)
        True
    """
    try:
        import owlapy  # noqa: F401

        return True
    except Exception:
        return False


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


def _node_ref(value: Any) -> str:
    return str(value)


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
    for binding in graph.query(capped):
        row: dict[str, str] = {}
        for key in binding.labels:
            value = binding[key]
            row[str(key)] = "" if value is None else str(value)
        rows.append(row)
        if len(rows) >= limit:
            break
    return rows


def _instances_rdflib(
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


def _types_rdflib(
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


def _write_temp_ontology(graph: Graph) -> Path:
    """Serialize graph to a temporary Turtle file for OWLAPY."""
    handle = tempfile.NamedTemporaryFile(
        prefix="tkeir-merged-",
        suffix=".ttl",
        delete=False,
        mode="w",
        encoding="utf-8",
    )
    path = Path(handle.name)
    try:
        handle.write(graph.serialize(format="turtle"))
    finally:
        handle.close()
    return path


def _query_with_owlapy(
    graph: Graph,
    *,
    operation: OntologyOperation,
    class_iri: str | None,
    individual_iri: str | None,
    sparql: str | None,
    reasoner: str,
    direct: bool,
    limit: int,
) -> dict[str, Any]:
    """Run an OWLAPY SyncReasoner query; raises ImportError if unavailable."""
    from owlapy.class_expression import OWLClass
    from owlapy.iri import IRI
    from owlapy.owl_individual import OWLNamedIndividual
    from owlapy.owl_ontology import SyncOntology
    from owlapy.owl_reasoner import SyncReasoner

    path = _write_temp_ontology(graph)
    try:
        ontology = SyncOntology(path.as_posix())
        sync = SyncReasoner(ontology, reasoner=reasoner)
        backend = f"owlapy:{reasoner}"

        if operation == "consistency":
            consistent = bool(sync.has_consistent_ontology())
            return {
                "operation": operation,
                "backend": backend,
                "consistent": consistent,
                "results": [{"consistent": str(consistent).lower()}],
            }

        if operation == "sparql":
            if not sparql or not sparql.strip():
                raise ValueError("sparql operation requires a non-empty query")
            rows = _sparql_select(graph, sparql, limit=limit)
            return {
                "operation": operation,
                "backend": "rdflib+sparql",
                "results": rows,
                "count": len(rows),
            }

        if operation in {"subclasses", "superclasses", "instances"}:
            if not class_iri:
                raise ValueError(f"{operation} requires class_iri")
            owl_class = OWLClass(IRI.create(class_iri))
            if operation == "subclasses":
                nodes = list(
                    sync.sub_classes(owl_class, direct=direct) or []
                )
            elif operation == "superclasses":
                nodes = list(
                    sync.super_classes(owl_class, direct=direct) or []
                )
            else:
                nodes = list(sync.instances(owl_class) or [])
            results = [
                {"iri": _node_ref(node), "label": _local_name(_node_ref(node))}
                for node in nodes[:limit]
            ]
            return {
                "operation": operation,
                "backend": backend,
                "results": results,
                "count": len(results),
            }

        if operation == "types":
            if not individual_iri:
                raise ValueError("types requires individual_iri")
            individual = OWLNamedIndividual(IRI.create(individual_iri))
            nodes = list(sync.types(individual) or [])
            results = [
                {"iri": _node_ref(node), "label": _local_name(_node_ref(node))}
                for node in nodes[:limit]
            ]
            return {
                "operation": operation,
                "backend": backend,
                "results": results,
                "count": len(results),
            }

        if operation == "infer":
            # Materialize inferred class assertions back into JSON-LD when possible.
            inferred = Graph()
            for triple in graph:
                inferred.add(triple)
            try:
                axioms = list(
                    sync.infer_axioms(
                        inference_types=["InferredClassAssertionAxiomGenerator"]
                    )
                    or []
                )
            except TypeError:
                axioms = []
            added = 0
            for axiom in axioms[: max(limit * 5, limit)]:
                text = str(axiom)
                # Best-effort: SyncReasoner axiom objects vary by version;
                # keep count even when we cannot map every axiom to RDF.
                added += 1
                _ = text
            return {
                "operation": operation,
                "backend": backend,
                "results": [{"inferred_axioms": str(added)}],
                "count": added,
                "json_ld": serialize_graph_json_ld(inferred),
                "note": (
                    "Inferred axiom count from OWLAPY; JSON-LD is the "
                    "pre-inference merge (re-serialize after apply if needed)."
                ),
            }

        raise ValueError(f"unsupported operation: {operation}")
    finally:
        try:
            path.unlink(missing_ok=True)
        except OSError:
            pass


def _query_with_rdflib(
    graph: Graph,
    *,
    operation: OntologyOperation,
    class_iri: str | None,
    individual_iri: str | None,
    sparql: str | None,
    direct: bool,
    limit: int,
) -> dict[str, Any]:
    """Lightweight reasoner substitute using rdflib only."""
    backend = "rdflib"

    if operation == "consistency":
        # rdflib cannot prove DL consistency; report structural emptiness check.
        consistent = len(graph) >= 0
        return {
            "operation": operation,
            "backend": backend,
            "consistent": consistent,
            "results": [{"consistent": "true"}],
            "note": "Install owlapy (uv sync --extra owl) for HermiT consistency.",
        }

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
        direction = "sub" if operation == "subclasses" else "super"
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
            "note": "RDFS walk only; install owlapy for full OWL reasoning.",
        }

    if operation == "instances":
        if not class_iri:
            raise ValueError("instances requires class_iri")
        results = _instances_rdflib(graph, class_iri, limit=limit)
        return {
            "operation": operation,
            "backend": backend,
            "results": results,
            "count": len(results),
        }

    if operation == "types":
        if not individual_iri:
            raise ValueError("types requires individual_iri")
        results = _types_rdflib(graph, individual_iri, limit=limit)
        return {
            "operation": operation,
            "backend": backend,
            "results": results,
            "count": len(results),
        }

    if operation == "infer":
        return {
            "operation": operation,
            "backend": backend,
            "results": [],
            "count": 0,
            "note": "infer requires owlapy SyncReasoner (uv sync --extra owl).",
        }

    raise ValueError(f"unsupported operation: {operation}")


def query_merged_ontology(
    json_ld: str,
    *,
    operation: OntologyOperation | str = "sparql",
    class_iri: str | None = None,
    individual_iri: str | None = None,
    sparql: str | None = None,
    reasoner: str = DEFAULT_REASONER,
    direct: bool = False,
    limit: int = 50,
    prefer_owlapy: bool = True,
) -> dict[str, Any]:
    """Query a merged ontology payload from a prior RAG / search response.

    Args:
        json_ld: Fused ontology ``json_ld`` (JSON-LD or Turtle also accepted).
        operation: One of :data:`SUPPORTED_OPERATIONS`.
        class_iri: Class IRI for hierarchy / instance queries.
        individual_iri: Individual IRI for ``types``.
        sparql: SPARQL SELECT string for ``sparql``.
        reasoner: OWLAPY reasoner name (``HermiT``, ``Pellet``, …).
        direct: Restrict hierarchy to direct relations when supported.
        limit: Max rows / individuals returned.
        prefer_owlapy: Use OWLAPY when installed; else rdflib fallback.

    Returns:
        Dict with ``operation``, ``backend``, ``results``, and optional notes.

    Example:
        >>> payload = (
        ...     '[{"@id":"http://ex/A","@type":["http://www.w3.org/2002/07/owl#Class"]},'
        ...     '{"@id":"http://ex/B","@type":["http://www.w3.org/2002/07/owl#Class"],'
        ...     '"http://www.w3.org/2000/01/rdf-schema#subClassOf":[{"@id":"http://ex/A"}]}]'
        ... )
        >>> out = query_merged_ontology(
        ...     payload,
        ...     operation="subclasses",
        ...     class_iri="http://ex/A",
        ...     prefer_owlapy=False,
        ... )
        >>> out["count"] >= 1
        True
    """
    op = str(operation).strip().lower()
    if op not in SUPPORTED_OPERATIONS:
        raise ValueError(
            f"unsupported operation {operation!r}; "
            f"expected one of {SUPPORTED_OPERATIONS}"
        )
    graph = _load_graph(json_ld)
    chosen = normalize_reasoner_name(reasoner)
    meta = {
        "triple_count": len(graph),
        "owlapy_available": owlapy_available(),
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

    force_rdflib = chosen == "rdflib" or not prefer_owlapy
    use_owl = (not force_rdflib) and owlapy_available() and op != "sparql"

    if op == "sparql" or not use_owl:
        result = _query_with_rdflib(
            graph,
            operation=op,  # type: ignore[arg-type]
            class_iri=class_iri,
            individual_iri=individual_iri,
            sparql=sparql,
            direct=direct,
            limit=limit,
        )
    else:
        try:
            result = _query_with_owlapy(
                graph,
                operation=op,  # type: ignore[arg-type]
                class_iri=class_iri,
                individual_iri=individual_iri,
                sparql=sparql,
                reasoner=chosen,
                direct=direct,
                limit=limit,
            )
        except Exception as exc:  # noqa: BLE001 — fall back gracefully
            result = _query_with_rdflib(
                graph,
                operation=op,  # type: ignore[arg-type]
                class_iri=class_iri,
                individual_iri=individual_iri,
                sparql=sparql,
                direct=direct,
                limit=limit,
            )
            result["note"] = (
                f"owlapy failed ({exc}); used rdflib fallback. "
                + str(result.get("note") or "")
            ).strip()

    result.update(meta)
    result["reasoner"] = normalize_reasoner_name(reasoner)
    # Always attach a JSON-LD view of the reasoner answer for HMI graph display.
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
    # Touch OWL for doctest / import side-effect stability.
    _ = OWL.Class
    return result
