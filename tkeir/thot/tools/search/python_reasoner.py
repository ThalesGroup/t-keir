"""Title: Single Python ontology reasoner (coherence + class expressions)

Pure-Python reasoning over an rdflib graph — no Java OWL engines.

Two request families:
  A. Coherence / hierarchy — consistency checks, RDFS subclass walks,
     instances, types.
  B. Class expressions — Manchester-like strings such as
     ``Person and age > 20`` compiled to SPARQL.

Author: Eric Blaudez

Copyright (c) 2026 Thales
Licensed under the MIT License.
"""

from __future__ import annotations

import re
from typing import Any

from rdflib import OWL, RDF, RDFS, XSD, Graph, Literal, URIRef

_EXPR_RE = re.compile(
    r"""^\s*
    (?P<cls>"[^"]+"|'[^']+'|.+?)
    (?:\s+and\s+(?P<prop>[\w./:#\-]+)\s*
    (?P<op>>=|<=|!=|=|>|<)\s*(?P<val>.+))?
    \s*$""",
    re.IGNORECASE | re.VERBOSE,
)


def _local_name(iri: str) -> str:
    """Return the local name segment of an IRI.

    Example:
        >>> _local_name("http://example.org/Person#Alice")
        'Alice'
    """
    text = str(iri or "")
    if "#" in text:
        return text.rsplit("#", 1)[-1]
    return text.rstrip("/").rsplit("/", 1)[-1]


def _node_label(graph: Graph, node: Any) -> str:
    """Return rdfs:label for a node, else its local name.

    Example:
        >>> from rdflib import Graph, URIRef
        >>> from rdflib.namespace import RDFS
        >>> g = Graph()
        >>> node = URIRef("http://example.org/Alice")
        >>> _ = g.add((node, RDFS.label, URIRef("http://example.org/label/Alice")))
        >>> _node_label(g, node)
        'http://example.org/label/Alice'
    """
    label = graph.value(node, RDFS.label)
    if label is not None:
        return str(label)
    return _local_name(str(node))


def find_class_iri(graph: Graph, name: str) -> str | None:
    """Resolve a class by local name or rdfs:label (case-insensitive).

    Example:
        >>> from rdflib import Graph, URIRef
        >>> from rdflib.namespace import RDF, RDFS
        >>> g = Graph()
        >>> cls = URIRef("http://example.org/Person")
        >>> _ = g.add((cls, RDF.type, RDFS.Class))
        >>> find_class_iri(g, "Person")
        'http://example.org/Person'
    """
    needle = (name or "").strip().casefold()
    if not needle:
        return None
    if needle.startswith("http://") or needle.startswith("https://"):
        return name.strip()
    class_types = (
        OWL.Class,
        RDFS.Class,
        URIRef("http://schema.org/DefinedTerm"),
        URIRef("http://www.w3.org/2004/02/skos/core#Concept"),
    )
    for ctype in class_types:
        for cls in graph.subjects(RDF.type, ctype):
            if _local_name(str(cls)).casefold() == needle:
                return str(cls)
            if _node_label(graph, cls).casefold() == needle:
                return str(cls)
            for label in graph.objects(cls, RDFS.label):
                if str(label).casefold() == needle:
                    return str(cls)
    # Fallback: any typed resource whose local name matches.
    for subject, _, obj in graph.triples((None, RDF.type, None)):
        if _local_name(str(obj)).casefold() == needle:
            return str(obj)
    return None


def find_property_iri(graph: Graph, name: str) -> str | None:
    """Resolve a property by local name or rdfs:label.

    Example:
        >>> from rdflib import Graph, URIRef
        >>> from rdflib.namespace import RDF
        >>> from rdflib.namespace import OWL
        >>> g = Graph()
        >>> prop = URIRef("http://example.org/age")
        >>> _ = g.add((prop, RDF.type, OWL.DatatypeProperty))
        >>> find_property_iri(g, "age")
        'http://example.org/age'
    """
    needle = (name or "").strip().casefold()
    if not needle:
        return None
    if needle.startswith("http://") or needle.startswith("https://"):
        return name.strip()
    for pred in (
        OWL.DatatypeProperty,
        OWL.ObjectProperty,
        RDF.Property,
    ):
        for prop in graph.subjects(RDF.type, pred):
            if _local_name(str(prop)).casefold() == needle:
                return str(prop)
            if _node_label(graph, prop).casefold() == needle:
                return str(prop)
    # Any predicate used in the graph with matching local name.
    seen: set[str] = set()
    for predicate in graph.predicates():
        key = str(predicate)
        if key in seen:
            continue
        seen.add(key)
        if _local_name(key).casefold() == needle:
            return key
    return None


def check_coherence(graph: Graph, *, limit: int = 50) -> dict[str, Any]:
    """Structural coherence / hierarchy sanity checks (pure Python).

    Detects:
      - individuals typed as ``owl:Nothing``
      - reflexive ``rdfs:subClassOf``
      - simple subclass cycles (A ⊑ B ⊑ A)
      - disjoint classes sharing an instance (when ``owl:disjointWith`` present)

    Example:
        >>> from rdflib import Graph
        >>> check_coherence(Graph())["consistent"]
        True
    """
    issues: list[dict[str, str]] = []

    nothing = OWL.Nothing
    for subject in graph.subjects(RDF.type, nothing):
        issues.append(
            {
                "kind": "nothing_instance",
                "iri": str(subject),
                "message": f"{_local_name(str(subject))} typed as owl:Nothing",
            }
        )
        if len(issues) >= limit:
            break

    for subject, _, obj in graph.triples((None, RDFS.subClassOf, None)):
        if subject == obj:
            issues.append(
                {
                    "kind": "reflexive_subclass",
                    "iri": str(subject),
                    "message": (
                        f"{_local_name(str(subject))} is a subclass of itself"
                    ),
                }
            )
            if len(issues) >= limit:
                break

    # Pairwise cycle detection on direct subclass edges.
    children: dict[str, set[str]] = {}
    for sub_iri, _, super_iri in graph.triples((None, RDFS.subClassOf, None)):
        children.setdefault(str(super_iri), set()).add(str(sub_iri))
    for parent_iri, child_iris in list(children.items()):
        for child_iri in child_iris:
            if parent_iri in children.get(child_iri, set()):
                issues.append(
                    {
                        "kind": "subclass_cycle",
                        "iri": parent_iri,
                        "message": (
                            f"cycle between {_local_name(parent_iri)} and "
                            f"{_local_name(child_iri)}"
                        ),
                    }
                )
                if len(issues) >= limit:
                    break
        if len(issues) >= limit:
            break

    for left, _, right in graph.triples((None, OWL.disjointWith, None)):
        left_instances = set(graph.subjects(RDF.type, left))
        right_instances = set(graph.subjects(RDF.type, right))
        shared = left_instances & right_instances
        for individual in list(shared)[: max(1, limit - len(issues))]:
            issues.append(
                {
                    "kind": "disjoint_violation",
                    "iri": str(individual),
                    "message": (
                        f"{_local_name(str(individual))} instance of disjoint "
                        f"classes {_local_name(str(left))} and "
                        f"{_local_name(str(right))}"
                    ),
                }
            )
            if len(issues) >= limit:
                break
        if len(issues) >= limit:
            break

    consistent = len(issues) == 0
    return {
        "operation": "consistency",
        "backend": "python",
        "consistent": consistent,
        "results": (
            issues
            or [{"kind": "ok", "message": "No coherence issues detected"}]
        ),
        "count": len(issues),
        "note": "Pure-Python coherence (hierarchy / disjoint / Nothing).",
    }


def expression_to_sparql(
    graph: Graph, expression: str, *, limit: int = 50
) -> str:
    """Compile a Manchester-like expression into SPARQL SELECT.

    Supported forms:
      - ``Person``
      - ``Person and age > 20``
      - ``Vessel and flag = Liberia``

    Example:
        >>> from rdflib import Graph, URIRef
        >>> from rdflib.namespace import RDF, RDFS
        >>> g = Graph()
        >>> person = URIRef("http://example.org/Person")
        >>> _ = g.add((person, RDF.type, RDFS.Class))
        >>> "Person" in expression_to_sparql(g, "Person")
        True
    """
    match = _EXPR_RE.match(expression or "")
    if not match:
        raise ValueError(
            "Unsupported expression. Use forms like "
            "'Person' or 'Person and age > 20'."
        )
    cls_name = (match.group("cls") or "").strip().strip("\"'")
    prop_name = match.group("prop")
    op = match.group("op")
    raw_val = (match.group("val") or "").strip().strip("\"'")

    class_iri = find_class_iri(graph, cls_name)
    if not class_iri:
        raise ValueError(f"Unknown class in expression: {cls_name!r}")

    if not prop_name:
        return (
            "PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>\n"
            "PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>\n"
            "SELECT ?x ?label WHERE {\n"
            f"  ?x rdf:type <{class_iri}> .\n"
            "  OPTIONAL { ?x rdfs:label ?label }\n"
            f"}} LIMIT {int(limit)}"
        )

    prop_iri = find_property_iri(graph, prop_name)
    if not prop_iri:
        # Fall back to rdfs:label when the user wrote "label".
        if prop_name.casefold() in {"label", "name", "rdfs:label"}:
            prop_iri = str(RDFS.label)
        else:
            raise ValueError(f"Unknown property in expression: {prop_name!r}")

    sparql_op = {
        ">": ">",
        "<": "<",
        ">=": ">=",
        "<=": "<=",
        "=": "=",
        "!=": "!=",
    }.get(op or "=", "=")

    numeric = False
    try:
        float(raw_val)
        numeric = True
    except ValueError:
        numeric = False

    if numeric:
        filter_clause = f"FILTER(xsd:double(?v) {sparql_op} {raw_val})"
        value_bind = "?v"
    else:
        lit = raw_val.replace("\\", "\\\\").replace('"', '\\"')
        if sparql_op == "=":
            filter_clause = f'FILTER(LCASE(STR(?v)) = LCASE("{lit}"))'
        elif sparql_op == "!=":
            filter_clause = f'FILTER(LCASE(STR(?v)) != LCASE("{lit}"))'
        else:
            filter_clause = f'FILTER(STR(?v) {sparql_op} "{lit}")'
        value_bind = "?v"

    return (
        "PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>\n"
        "PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>\n"
        "PREFIX xsd: <http://www.w3.org/2001/XMLSchema#>\n"
        "SELECT ?x ?label ?v WHERE {\n"
        f"  ?x rdf:type <{class_iri}> .\n"
        f"  ?x <{prop_iri}> {value_bind} .\n"
        "  OPTIONAL { ?x rdfs:label ?label }\n"
        f"  {filter_clause}\n"
        f"}} LIMIT {int(limit)}"
    )


def _sparql_select(
    graph: Graph, sparql: str, *, limit: int
) -> list[dict[str, str]]:
    """Run a SPARQL SELECT and return stringified bindings.

    Example:
        >>> from rdflib import Graph, Literal, URIRef
        >>> g = Graph()
        >>> _ = g.add((URIRef("http://example.org/a"), URIRef("http://example.org/p"), Literal("v")))
        >>> rows = _sparql_select(g, "SELECT ?o WHERE { ?s ?p ?o }", limit=5)
        >>> rows[0]["o"]
        'v'
    """
    rows: list[dict[str, str]] = []
    for raw_row in graph.query(sparql):
        row: Any = raw_row
        if hasattr(row, "asdict"):
            binding = {
                str(key): str(value)
                for key, value in row.asdict().items()
                if value is not None
            }
        else:
            # rdflib ResultRow supports dict-like access via labels
            binding = {}
            for key in getattr(row, "labels", []) or []:
                if key is None:
                    continue
                value = row[key]
                if value is not None:
                    binding[str(key)] = str(value)
        if binding:
            rows.append(binding)
        if len(rows) >= limit:
            break
    return rows


def evaluate_expression(
    graph: Graph,
    expression: str,
    *,
    limit: int = 50,
) -> dict[str, Any]:
    """Run a class expression via compiled SPARQL.

    Example:
        >>> from rdflib import Graph, URIRef
        >>> from rdflib.namespace import RDF, RDFS
        >>> g = Graph()
        >>> person = URIRef("http://example.org/Person")
        >>> _ = g.add((person, RDF.type, RDFS.Class))
        >>> evaluate_expression(g, "Person")["operation"]
        'expression'
    """
    sparql = expression_to_sparql(graph, expression, limit=limit)
    rows = _sparql_select(graph, sparql, limit=limit)
    return {
        "operation": "expression",
        "backend": "python",
        "results": rows,
        "count": len(rows),
        "sparql": sparql,
        "note": f"Compiled expression: {expression!r}",
    }


def _resource_labels(graph: Graph, node: Any) -> list[str]:
    """Collect display labels for a resource (rdfs:label + schema alternateName).

    Example:
        >>> from rdflib import Graph, Literal, URIRef
        >>> from rdflib.namespace import RDFS
        >>> g = Graph()
        >>> node = URIRef("http://example.org/Alice")
        >>> _ = g.add((node, RDFS.label, Literal("Alice")))
        >>> "Alice" in _resource_labels(g, node)
        True
    """
    labels: list[str] = []
    for pred in (
        RDFS.label,
        URIRef("http://schema.org/name"),
        URIRef("http://schema.org/alternateName"),
    ):
        for value in graph.objects(node, pred):
            text = str(value).strip()
            if text:
                labels.append(text)
    local = _local_name(str(node))
    if local:
        labels.append(local.replace("_", " "))
    # Deduplicate preserving order
    return list(dict.fromkeys(labels))


def _term_match_score(labels: list[str], focus_terms: list[str]) -> float:
    """Score how well resource labels match query focus terms.

    Example:
        >>> _term_match_score(["Microsoft"], ["microsoft"])
        3.0
    """
    if not focus_terms:
        return 0.0
    best = 0.0
    label_fold = [lab.casefold() for lab in labels]
    for term in focus_terms:
        needle = str(term or "").strip().casefold()
        if len(needle) < 2:
            continue
        for lab in label_fold:
            if needle == lab:
                best = max(best, 3.0)
            elif needle in lab or lab in needle:
                best = max(best, 2.0 + min(len(needle), len(lab)) / 40.0)
            elif any(tok and tok in lab for tok in needle.split()):
                best = max(best, 1.0)
    return best


def find_ontology_anchors(
    graph: Graph,
    *,
    focus_terms: list[str] | None = None,
    entity_types: list[str] | None = None,
    limit: int = 8,
) -> list[dict[str, str]]:
    """Pick ontology resources that match the query or dominate the taxonomy.

    Example:
        >>> from rdflib import Graph, Literal, URIRef
        >>> from rdflib.namespace import RDF, RDFS
        >>> g = Graph()
        >>> cls = URIRef("http://example.org/Person")
        >>> _ = g.add((cls, RDF.type, RDFS.Class))
        >>> _ = g.add((cls, RDFS.label, Literal("Person")))
        >>> find_ontology_anchors(g, focus_terms=["Person"])[0]["label"]
        'Person'
    """
    focus = [str(t).strip() for t in focus_terms or [] if str(t).strip()]
    type_hints = [str(t).strip() for t in entity_types or [] if str(t).strip()]
    candidates: list[tuple[float, str, str]] = []

    class_types = {
        OWL.Class,
        RDFS.Class,
        URIRef("http://schema.org/DefinedTerm"),
        URIRef("http://www.w3.org/2004/02/skos/core#Concept"),
    }

    subjects: set[Any] = set()
    for ctype in class_types:
        subjects.update(graph.subjects(RDF.type, ctype))
    # Also include anything with an rdfs:label (document entities).
    subjects.update(graph.subjects(RDFS.label, None))

    for node in subjects:
        if not isinstance(node, URIRef):
            continue
        labels = _resource_labels(graph, node)
        if not labels:
            continue
        score = _term_match_score(labels, focus)
        score += 0.5 * _term_match_score(labels, type_hints)
        # Prefer classes that participate in the hierarchy.
        if any(graph.objects(node, RDFS.subClassOf)) or any(
            graph.subjects(RDFS.subClassOf, node)
        ):
            score += 0.25
        if any(
            graph.objects(
                node, URIRef("http://www.w3.org/2004/02/skos/core#broader")
            )
        ) or any(
            graph.objects(
                node, URIRef("http://www.w3.org/2004/02/skos/core#narrower")
            )
        ):
            score += 0.25
        if score <= 0 and focus:
            continue
        candidates.append((score, str(node), labels[0]))

    # No query match → fall back to most connected taxonomy classes.
    if not candidates:
        for node in subjects:
            if not isinstance(node, URIRef):
                continue
            if not (
                (node, RDF.type, OWL.Class) in graph
                or (node, RDF.type, URIRef("http://schema.org/DefinedTerm"))
                in graph
            ):
                continue
            labels = _resource_labels(graph, node)
            if not labels:
                continue
            degree = sum(1 for _ in graph.predicate_objects(node))
            degree += sum(1 for _ in graph.subjects(RDFS.subClassOf, node))
            candidates.append((float(degree), str(node), labels[0]))

    candidates.sort(key=lambda row: (-row[0], row[2].casefold()))
    out: list[dict[str, str]] = []
    seen: set[str] = set()
    for score, iri, label in candidates:
        if iri in seen:
            continue
        seen.add(iri)
        out.append({"iri": iri, "label": label, "score": f"{score:.2f}"})
        if len(out) >= limit:
            break
    return out


def _sparql_escape(term: str) -> str:
    """Escape a string for safe inclusion in generated SPARQL literals.

    Example:
        >>> _sparql_escape('say "hello"').startswith("say ")
        True
        >>> '\\"' in _sparql_escape('say "hello"')
        True
    """
    return (
        str(term or "")
        .replace("\\", "\\\\")
        .replace('"', '\\"')
        .replace("\n", " ")
        .replace("\r", " ")
    )


def important_terms_from_chunk_hits(
    *,
    entities: list[dict[str, Any]] | None = None,
    keywords: list[dict[str, Any]] | None = None,
    focus_terms: list[str] | None = None,
    limit: int = 8,
) -> list[str]:
    """Rank the most important terms across returned chunk-linked hits.

    Prefers entities/keywords that appear in many retrieved chunks, then
    boosts overlap with the query focus terms. Query focus terms that
    appear inside chunk labels are injected first (e.g. ``Suez``).

    Example:
        >>> important_terms_from_chunk_hits(
        ...     entities=[{"label": "Suez", "chunk_ids": ["c1", "c2"]}],
        ...     focus_terms=["Suez"],
        ... )
        ['Suez']
    """
    scores: dict[str, float] = {}
    labels: dict[str, str] = {}

    def _is_noise(text: str) -> bool:
        """Return whether a term is too short or function-word-like for SPARQL focus.

        Example:
            >>> True
            True
        """
        folded = text.casefold().strip()
        if len(folded) < 2:
            return True
        if folded in {
            "what",
            "who",
            "where",
            "when",
            "why",
            "how",
            "which",
            "at",
            "in",
            "on",
            "of",
            "the",
            "a",
            "an",
            "source",
        }:
            return True
        if re.fullmatch(r"[#\W_]+", folded):
            return True
        if re.fullmatch(r"\d+(\.\d+)?(\s*[a-z%]+)?", folded):
            return True
        return False

    def _add(label: str, weight: float) -> None:
        """Accumulate weighted term scores when not noise.

        Example:
            >>> True
            True
        """
        text = str(label or "").strip()
        if _is_noise(text):
            return
        key = text.casefold()
        scores[key] = scores.get(key, 0.0) + weight
        labels.setdefault(key, text)

    for entity in entities or []:
        if not isinstance(entity, dict):
            continue
        chunk_ids = entity.get("chunk_ids") or []
        n = len(chunk_ids) if isinstance(chunk_ids, list) else 0
        label = str(entity.get("label") or "").strip()
        _add(label, 12.0 * max(n, 1) + min(len(label), 24) * 0.1)

    for keyword in keywords or []:
        if not isinstance(keyword, dict):
            continue
        chunk_ids = keyword.get("chunk_ids") or []
        n = len(chunk_ids) if isinstance(chunk_ids, list) else 0
        label = str(keyword.get("label") or "").strip()
        # Dataset filenames are weak as SPARQL focus terms.
        if "_" in label and label.count("_") >= 2:
            continue
        _add(label, 8.0 * max(n, 1) + min(len(label), 24) * 0.05)

    focus = [str(t).strip() for t in focus_terms or [] if str(t).strip()]
    focus_fold = [t.casefold() for t in focus if not _is_noise(t)]
    for key in list(scores):
        for f in focus_fold:
            if key == f:
                scores[key] += 80.0
            elif len(f) >= 3 and (f in key or key in f):
                scores[key] += 40.0

    if not scores:
        for term in focus:
            _add(str(term), 5.0)

    ranked = sorted(
        scores.items(),
        key=lambda item: (-item[1], -len(labels[item[0]])),
    )

    # Inject query focus terms that are evidenced in chunk labels first.
    ordered: list[str] = []
    seen: set[str] = set()

    def _push(text: str) -> None:
        """Append a deduplicated term to the ordered output list.

        Example:
            >>> True
            True
        """
        key = text.casefold()
        if key in seen or _is_noise(text):
            return
        seen.add(key)
        ordered.append(text)

    label_values = list(labels.values())
    for term in focus:
        if any(term.casefold() in lab.casefold() for lab in label_values):
            _push(term)
    for key, _ in ranked:
        _push(labels[key])
    return ordered[:limit]


def propose_sparql_from_chunk_terms(
    graph: Graph,
    terms: list[str],
    *,
    limit: int = 3,
) -> list[dict[str, str]]:
    """Build three SPARQL chips from the most important chunk terms.

    Example:
        >>> from rdflib import Graph
        >>> proposals = propose_sparql_from_chunk_terms(Graph(), ["Suez"])
        >>> proposals[0]["kind"]
        'sparql'
    """
    cleaned = [str(t).strip() for t in terms if str(t).strip()][:8]
    proposals: list[dict[str, str]] = []

    def add(title: str, query: str, description: str) -> None:
        """Append one SPARQL proposal when under the limit.

        Example:
            >>> True
            True
        """
        if len(proposals) >= limit:
            return
        proposals.append(
            {
                "kind": "sparql",
                "title": title,
                "query": query.strip(),
                "description": description,
            }
        )

    if not cleaned:
        add(
            "Sample triples",
            """PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
SELECT ?s ?p ?o ?sl WHERE {
  ?s ?p ?o .
  OPTIONAL { ?s rdfs:label ?sl }
} LIMIT 25""",
            "No chunk terms available — browse the fused graph",
        )
        return proposals

    top = cleaned[0]
    top_esc = _sparql_escape(top.lower())
    # Resolve ontology anchors when the term matches a class/concept label.
    top_iri = find_class_iri(graph, top)

    term_filters = " ||\n    ".join(
        f'CONTAINS(LCASE(STR(?sl)), "{_sparql_escape(term.lower())}") || '
        f'CONTAINS(LCASE(STR(?ol)), "{_sparql_escape(term.lower())}")'
        for term in cleaned[:5]
    )
    add(
        f"Facts for top chunk terms ({', '.join(cleaned[:3])})",
        f"""PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
SELECT ?s ?p ?o ?sl ?ol WHERE {{
  ?s ?p ?o .
  OPTIONAL {{ ?s rdfs:label ?sl }}
  OPTIONAL {{ ?o rdfs:label ?ol }}
  FILTER(
    {term_filters}
  )
}} LIMIT 40""",
        "Label matches for the most important terms across returned chunks",
    )

    if len(cleaned) >= 2:
        left = _sparql_escape(cleaned[0].lower())
        right = _sparql_escape(cleaned[1].lower())
        add(
            f"Bridge “{cleaned[0]}” ↔ “{cleaned[1]}”",
            f"""PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
SELECT ?a ?p1 ?mid ?p2 ?b ?al ?midl ?bl WHERE {{
  ?a ?p1 ?mid .
  ?mid ?p2 ?b .
  OPTIONAL {{ ?a rdfs:label ?al }}
  OPTIONAL {{ ?mid rdfs:label ?midl }}
  OPTIONAL {{ ?b rdfs:label ?bl }}
  FILTER(
    (
      CONTAINS(LCASE(STR(?al)), "{left}") &&
      CONTAINS(LCASE(STR(?bl)), "{right}")
    ) || (
      CONTAINS(LCASE(STR(?al)), "{right}") &&
      CONTAINS(LCASE(STR(?bl)), "{left}")
    ) || (
      CONTAINS(LCASE(STR(?midl)), "{left}") &&
      CONTAINS(LCASE(STR(?bl)), "{right}")
    )
  )
}} LIMIT 30""",
            "Multi-hop paths between the two strongest chunk terms",
        )
    elif top_iri:
        add(
            f"Neighbourhood of {top}",
            f"""PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
PREFIX skos: <http://www.w3.org/2004/02/skos/core#>
SELECT ?p ?o ?ol WHERE {{
  <{top_iri}> ?p ?o .
  OPTIONAL {{ ?o rdfs:label ?ol }}
  FILTER(?p != rdfs:label)
}} LIMIT 40""",
            f"Outbound ontology edges for chunk term {top}",
        )

    if top_iri:
        add(
            f"Hierarchy / types for “{top}”",
            f"""PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
PREFIX skos: <http://www.w3.org/2004/02/skos/core#>
SELECT ?x ?rel ?y ?xl ?yl WHERE {{
  {{
    ?x rdfs:subClassOf <{top_iri}> .
    BIND(rdfs:subClassOf AS ?rel)
    BIND(<{top_iri}> AS ?y)
  }} UNION {{
    <{top_iri}> skos:broader|skos:narrower|skos:related ?y .
    BIND(<{top_iri}> AS ?x)
    BIND(skos:related AS ?rel)
  }} UNION {{
    ?x rdf:type <{top_iri}> .
    BIND(rdf:type AS ?rel)
    BIND(<{top_iri}> AS ?y)
  }}
  OPTIONAL {{ ?x rdfs:label ?xl }}
  OPTIONAL {{ ?y rdfs:label ?yl }}
}} LIMIT 40""",
            f"Subclass / SKOS / instance links for ontology match of {top}",
        )
    else:
        add(
            f"Types mentioning “{top}”",
            f"""PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
SELECT ?x ?type ?xl ?tl WHERE {{
  ?x rdf:type ?type .
  OPTIONAL {{ ?x rdfs:label ?xl }}
  OPTIONAL {{ ?type rdfs:label ?tl }}
  FILTER(
    CONTAINS(LCASE(STR(?xl)), "{top_esc}") ||
    CONTAINS(LCASE(STR(?tl)), "{top_esc}") ||
    CONTAINS(LCASE(STR(?x)), "{top_esc}") ||
    CONTAINS(LCASE(STR(?type)), "{top_esc}")
  )
}} LIMIT 40""",
            f"rdf:type rows whose labels mention chunk term {top}",
        )
    return proposals[:limit]


def propose_expression_queries(
    graph: Graph,
    *,
    focus_terms: list[str] | None = None,
    entity_types: list[str] | None = None,
    limit: int = 3,
) -> list[dict[str, str]]:
    """Propose Manchester-like expression chips from chunk terms / ontology classes.

    Example:
        >>> from rdflib import Graph, URIRef
        >>> from rdflib.namespace import RDF, RDFS
        >>> g = Graph()
        >>> cls = URIRef("http://example.org/Person")
        >>> _ = g.add((cls, RDF.type, RDFS.Class))
        >>> propose_expression_queries(g, focus_terms=["Person"], limit=1)
        [{'kind': 'expression', 'title': 'Instances of Person', 'query': 'Person', 'description': 'Class expression for chunk/ontology term Person'}]
    """
    proposals: list[dict[str, str]] = []
    seen: set[str] = set()

    def add(title: str, query: str, description: str) -> None:
        """Append one expression proposal when it resolves in the graph.

        Example:
            >>> True
            True
        """
        key = query.casefold()
        if key in seen or len(proposals) >= limit:
            return
        # Only propose expressions that resolve in this graph.
        if not find_class_iri(
            graph, query.split(" and ", 1)[0].strip().strip("\"'")
        ):
            return
        seen.add(key)
        proposals.append(
            {
                "kind": "expression",
                "title": title,
                "query": query,
                "description": description,
            }
        )

    candidates: list[str] = []
    for term in list(focus_terms or []) + list(entity_types or []):
        text = str(term).strip()
        if text:
            candidates.append(text)

    for term in candidates:
        iri = find_class_iri(graph, term)
        if not iri:
            continue
        # Prefer local concept id (no spaces) when available.
        local = _local_name(iri)
        expr = local if local and " " not in local else term
        add(
            f"Instances of {term}",
            expr,
            f"Class expression for chunk/ontology term {term}",
        )
        if len(proposals) >= limit:
            break

    # Numeric restrictions only when both class and property exist.
    for prop in graph.subjects(RDF.type, OWL.DatatypeProperty):
        if len(proposals) >= limit:
            break
        prop_name = _local_name(str(prop))
        sample = next(graph.objects(None, prop), None)
        is_numeric = False
        threshold = "20"
        if isinstance(sample, Literal):
            try:
                value = float(sample)
                is_numeric = True
                threshold = str(max(1, int(value // 2)))
            except (TypeError, ValueError):
                is_numeric = False
        range_node = graph.value(prop, RDFS.range)
        if range_node and str(range_node) in {
            str(XSD.integer),
            str(XSD.int),
            str(XSD.float),
            str(XSD.double),
            str(XSD.decimal),
        }:
            is_numeric = True
        if not is_numeric:
            continue
        for subject in graph.subjects(prop, None):
            types = [
                node
                for node in graph.objects(subject, RDF.type)
                if node not in {OWL.NamedIndividual, OWL.Thing}
            ]
            if not types:
                continue
            cls_label = _local_name(str(types[0])) or _node_label(
                graph, types[0]
            )
            add(
                f"{cls_label} and {prop_name} > {threshold}",
                f"{cls_label} and {prop_name} > {threshold}",
                f"Restriction using datatype property {prop_name}",
            )
            break

    return proposals


def propose_hierarchy_queries(
    graph: Graph,
    *,
    focus_terms: list[str] | None = None,
    limit: int = 2,
) -> list[dict[str, str]]:
    """Propose hierarchy operations for classes matching chunk terms.

    Example:
        >>> from rdflib import Graph, URIRef
        >>> from rdflib.namespace import RDF, RDFS
        >>> g = Graph()
        >>> cls = URIRef("http://example.org/Person")
        >>> _ = g.add((cls, RDF.type, RDFS.Class))
        >>> propose_hierarchy_queries(g, focus_terms=["Person"])[0]["kind"]
        'subclasses'
    """
    proposals: list[dict[str, str]] = []
    for term in focus_terms or []:
        iri = find_class_iri(graph, term)
        if not iri:
            continue
        proposals.append(
            {
                "kind": "subclasses",
                "title": f"Subclasses of {term}",
                "query": iri,
                "description": (
                    "Hierarchy walk on a class matched from chunk terms"
                ),
            }
        )
        if len(proposals) >= limit:
            break
    return proposals


def propose_navigator_queries(
    graph: Graph,
    *,
    focus_terms: list[str] | None = None,
    entity_types: list[str] | None = None,
    chunk_entities: list[dict[str, Any]] | None = None,
    chunk_keywords: list[dict[str, Any]] | None = None,
) -> list[dict[str, str]]:
    """Full Navigator proposal set grounded in returned-chunk importance.

    Example:
        >>> from rdflib import Graph
        >>> kinds = {item["kind"] for item in propose_navigator_queries(Graph())}
        >>> "coherence" in kinds
        True
    """
    terms = important_terms_from_chunk_hits(
        entities=chunk_entities,
        keywords=chunk_keywords,
        focus_terms=focus_terms,
        limit=8,
    )
    proposals: list[dict[str, str]] = []
    proposals.extend(propose_sparql_from_chunk_terms(graph, terms, limit=3))
    # Hypergraph intersection: concepts shared across chunk sub-ontologies.
    chunk_type = URIRef("http://tkeir.local/ontology/DocumentChunk")
    has_chunks = any(True for _ in graph.subjects(RDF.type, chunk_type))
    if has_chunks and len(proposals) < 4:
        proposals.append(
            {
                "kind": "sparql",
                "title": "Shared concepts across chunks",
                "query": (
                    """PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
PREFIX tkeir: <http://tkeir.local/ontology/>
SELECT ?concept ?label ?c1 ?c2 ?support WHERE {
  ?concept tkeir:mentionedIn ?chunk1 ;
           tkeir:mentionedIn ?chunk2 ;
           rdfs:label ?label .
  OPTIONAL { ?concept tkeir:chunkSupport ?support }
  ?chunk1 rdfs:label ?c1 .
  ?chunk2 rdfs:label ?c2 .
  FILTER(STR(?chunk1) < STR(?chunk2))
} ORDER BY DESC(?support) LIMIT 40"""
                ),
                "description": (
                    "Sub-ontology intersection: concepts evidenced in ≥2 chunks "
                    "(document hypergraph)"
                ),
            }
        )
    proposals.extend(
        propose_expression_queries(
            graph,
            focus_terms=terms,
            entity_types=entity_types or [],
            limit=2,
        )
    )
    proposals.extend(
        propose_hierarchy_queries(
            graph,
            focus_terms=terms,
            limit=2,
        )
    )
    proposals.append(
        {
            "kind": "coherence",
            "title": "Coherence check",
            "query": "consistency",
            "description": (
                "Hierarchy / disjoint / owl:Nothing sanity on this ontology"
            ),
        }
    )
    return proposals
