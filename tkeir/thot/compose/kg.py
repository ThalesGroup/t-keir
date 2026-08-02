"""Title: Per-``user_space`` fused knowledge graph with SPARQL (rdflib backend).

Reuse :func:`thot.tools.search.ontology_utils.merge_turtle_graphs`. The
SPARQL surface is isolated behind :class:`SparqlBackend` so oxigraph (or
another store) can replace rdflib later without touching the composer.

Author: Eric Blaudez

Copyright (c) 2026 Thales
Licensed under the MIT License.
"""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Protocol

from rdflib import Graph, Literal, URIRef
from rdflib.namespace import RDF, RDFS, Namespace

from thot.tools.search.ontology_utils import (
    TKEIR,
    merge_turtle_graphs,
    summarize_graph_for_prompt,
)

LOGGER = logging.getLogger(__name__)

TKEIRDOC = Namespace("http://tkeir.local/doc/")

_STRUCTURAL_TYPES = frozenset(
    {
        str(TKEIR.Document),
        str(TKEIR.DocumentChunk),
        str(TKEIR.SubOntology),
        str(TKEIR.Statement),
        str(TKEIR.Keyword),
        str(TKEIR.Tag),
        str(TKEIR.Entity),
        str(TKEIR.Metric),
    }
)


class SparqlBackend(Protocol):
    """Swappable SPARQL/query backend over a fused graph."""

    def set_graph(self, graph: Graph) -> None:
        """Replace the working graph."""

    def query(self, sparql: str) -> list[dict[str, str]]:
        """Run a SELECT query; return list of binding dicts (str values)."""

    def graph(self) -> Graph:
        """Return the underlying rdflib Graph (read-only use)."""


class RdflibSparqlBackend:
    """Default SPARQL backend using rdflib.

    Example:
        >>> from rdflib import Graph, URIRef, Literal
        >>> from rdflib.namespace import RDFS
        >>> from thot.compose.kg import RdflibSparqlBackend
        >>> g = Graph()
        >>> _ = g.add((URIRef("http://ex/A"), RDFS.label, Literal("Acme")))
        >>> be = RdflibSparqlBackend()
        >>> be.set_graph(g)
        >>> rows = be.query(
        ...     "SELECT ?label WHERE { ?s <http://www.w3.org/2000/01/rdf-schema#label> ?label }"
        ... )
        >>> rows[0]["label"]
        'Acme'
    """

    def __init__(self) -> None:
        self._graph = Graph()

    def set_graph(self, graph: Graph) -> None:
        self._graph = graph

    def graph(self) -> Graph:
        return self._graph

    def query(self, sparql: str) -> list[dict[str, str]]:
        results = self._graph.query(sparql)
        rows: list[dict[str, str]] = []
        vars_ = list(results.vars or [])
        for row in results:
            binding: dict[str, str] = {}
            # rdflib ResultRow supports asdict(); avoid fragile indexing types.
            if hasattr(row, "asdict"):
                raw = row.asdict()  # type: ignore[union-attr]
                for key, val in raw.items():
                    binding[str(key)] = "" if val is None else str(val)
            else:
                for index, var in enumerate(vars_):
                    key = str(var)
                    try:
                        val = row[index]  # type: ignore[index]
                    except Exception:  # noqa: BLE001
                        val = None
                    binding[key] = "" if val is None else str(val)
            rows.append(binding)
        return rows


@dataclass
class FusedGraphEntry:
    """Cached fused graph for one ``user_space``."""

    user_space: str
    graph: Graph
    document_ids: list[str] = field(default_factory=list)
    turtle_fingerprints: list[str] = field(default_factory=list)
    loaded_at: float = field(default_factory=time.time)
    generation: int = 0


def _fingerprint(turtle: str) -> str:
    import hashlib

    return hashlib.sha256(turtle.encode("utf-8")).hexdigest()[:16]


def _node_label(graph: Graph, node: Any) -> str:
    if isinstance(node, Literal):
        return str(node)
    label = graph.value(node, RDFS.label)
    if label is not None:
        return str(label)
    text = str(node)
    if "/" in text:
        return text.rsplit("/", 1)[-1]
    return text


def _local_type(graph: Graph, node: URIRef) -> str:
    for t in graph.objects(node, RDF.type):
        text = str(t)
        if text.startswith(str(TKEIR)):
            return text.rsplit("/", 1)[-1]
    return "Entity"


class UserSpaceKG:
    """Fused per-tenant KG with cache + invalidation.

    Example:
        >>> from thot.compose.kg import UserSpaceKG
        >>> turtle = '''
        ... @prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
        ... @prefix tkeir: <http://tkeir.local/ontology/> .
        ... <http://ex/Acme> a tkeir:Company ; rdfs:label "Acme" .
        ... '''
        >>> kg = UserSpaceKG("alice")
        >>> _ = kg.load([turtle], document_ids=["doc-a"])
        >>> entities = kg.find_entities(label="Acme")
        >>> entities[0]["label"]
        'Acme'
        >>> kg.invalidate()
        >>> kg.is_empty()
        True
    """

    _lock = threading.RLock()
    _cache: dict[str, FusedGraphEntry] = {}

    def __init__(
        self,
        user_space: str,
        *,
        backend: SparqlBackend | None = None,
        use_process_cache: bool = True,
    ) -> None:
        self.user_space = user_space
        self.backend: SparqlBackend = backend or RdflibSparqlBackend()
        self.use_process_cache = use_process_cache
        self._entry: FusedGraphEntry | None = None
        if use_process_cache:
            with self._lock:
                cached = self._cache.get(user_space)
                if cached is not None:
                    self._entry = cached
                    self.backend.set_graph(cached.graph)

    def is_empty(self) -> bool:
        """Return whether the working graph has no triples."""
        return self._entry is None or len(self._entry.graph) == 0

    def load(
        self,
        turtles: list[str],
        *,
        document_ids: list[str] | None = None,
    ) -> FusedGraphEntry:
        """Merge Turtle/JSON-LD payloads and update the cache.

        Example:
            >>> from thot.compose.kg import UserSpaceKG
            >>> kg = UserSpaceKG("bob", use_process_cache=False)
            >>> entry = kg.load(["@prefix ex: <http://ex/> . ex:A a ex:T ."])
            >>> entry.generation >= 1
            True
        """
        docs = [t for t in turtles if isinstance(t, str) and t.strip()]
        graph = merge_turtle_graphs(docs) if docs else Graph()
        graph.bind("tkeir", TKEIR)
        fps = [_fingerprint(t) for t in docs]
        generation = 1
        if self._entry is not None:
            generation = self._entry.generation + 1
        entry = FusedGraphEntry(
            user_space=self.user_space,
            graph=graph,
            document_ids=list(document_ids or []),
            turtle_fingerprints=fps,
            generation=generation,
        )
        self._entry = entry
        self.backend.set_graph(graph)
        if self.use_process_cache:
            with self._lock:
                self._cache[self.user_space] = entry
        return entry

    def invalidate(self, *, reason: str = "supersede") -> None:
        """Drop the fused graph (e.g. on document supersede).

        Example:
            >>> from thot.compose.kg import UserSpaceKG
            >>> kg = UserSpaceKG("carol", use_process_cache=False)
            >>> _ = kg.load(["@prefix ex: <http://ex/> . ex:A a ex:T ."])
            >>> kg.invalidate(reason="test")
            >>> kg.is_empty()
            True
        """
        LOGGER.info(
            "kg invalidate user_space=%s reason=%s", self.user_space, reason
        )
        self._entry = None
        self.backend.set_graph(Graph())
        if self.use_process_cache:
            with self._lock:
                self._cache.pop(self.user_space, None)

    def sparql(self, query: str) -> list[dict[str, str]]:
        """Run SPARQL SELECT against the fused graph.

        Example:
            >>> from thot.compose.kg import UserSpaceKG
            >>> kg = UserSpaceKG("dave", use_process_cache=False)
            >>> _ = kg.load([
            ...     '@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> . '
            ...     '<http://ex/A> rdfs:label "X" .'
            ... ])
            >>> kg.sparql(
            ...     "SELECT ?label WHERE { ?s <http://www.w3.org/2000/01/rdf-schema#label> ?label }"
            ... )[0]["label"]
            'X'
        """
        if self.is_empty():
            return []
        return self.backend.query(query)

    def summary(self, topic: str = "", *, max_triples: int = 40) -> str:
        """Prompt-oriented triple summary."""
        if self.is_empty() or self._entry is None:
            return "No structured facts available."
        return summarize_graph_for_prompt(
            self._entry.graph, topic or "*", max_triples=max_triples
        )

    def find_entities(
        self,
        *,
        label: str | None = None,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        """List non-structural entities, optionally filtered by label substring."""
        if self.is_empty() or self._entry is None:
            return []
        graph = self._entry.graph
        needle = (label or "").strip().lower()
        out: list[dict[str, Any]] = []
        seen: set[str] = set()
        for subject in graph.subjects(RDF.type, None):
            if not isinstance(subject, URIRef):
                continue
            types = {str(t) for t in graph.objects(subject, RDF.type)}
            if types & _STRUCTURAL_TYPES:
                continue
            lab = _node_label(graph, subject)
            if needle and needle not in lab.lower():
                continue
            key = str(subject)
            if key in seen:
                continue
            seen.add(key)
            chunks = self.chunk_ids_for_node(subject)
            docs = self.document_ids_for_node(subject)
            out.append(
                {
                    "uri": key,
                    "label": lab,
                    "type": _local_type(graph, subject),
                    "chunk_ids": chunks,
                    "document_ids": docs,
                }
            )
            if len(out) >= limit:
                break
        return out

    def find_keywords(self, *, limit: int = 20) -> list[dict[str, Any]]:
        """List ``tkeir:Keyword`` nodes with provenance."""
        if self.is_empty() or self._entry is None:
            return []
        graph = self._entry.graph
        out: list[dict[str, Any]] = []
        for subject in graph.subjects(RDF.type, TKEIR.Keyword):
            lab = _node_label(graph, subject)
            out.append(
                {
                    "uri": str(subject),
                    "label": lab,
                    "chunk_ids": self.chunk_ids_for_node(subject),
                    "document_ids": self.document_ids_for_node(subject),
                }
            )
            if len(out) >= limit:
                break
        return out

    def find_svo(
        self,
        *,
        focus: str | None = None,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        """Extract non-structural SVO triples as slot values."""
        if self.is_empty() or self._entry is None:
            return []
        graph = self._entry.graph
        needle = (focus or "").strip().lower()
        structural_preds = {
            RDF.type,
            RDFS.label,
            TKEIR.hasChunk,
            TKEIR.hasMention,
            TKEIR.hasKeyword,
            TKEIR.hasTag,
            TKEIR.isTagOf,
            TKEIR.hasStatement,
            TKEIR.hasNumericValue,
        }
        out: list[dict[str, Any]] = []
        for s, p, o in graph:
            if p in structural_preds:
                continue
            if not isinstance(s, URIRef):
                continue
            types = {str(t) for t in graph.objects(s, RDF.type)}
            if types & _STRUCTURAL_TYPES:
                continue
            subj = _node_label(graph, s)
            pred = str(p).rsplit("/", 1)[-1]
            obj = _node_label(graph, o)
            line = f"{subj} | {pred} | {obj}"
            if needle and needle not in line.lower():
                continue
            chunks = sorted(
                set(self.chunk_ids_for_node(s) + self.chunk_ids_for_node(o))
            )
            docs = sorted(
                set(
                    self.document_ids_for_node(s)
                    + self.document_ids_for_node(o)
                )
            )
            out.append(
                {
                    "triple": line,
                    "subject": subj,
                    "predicate": pred,
                    "object": obj,
                    "chunk_ids": chunks,
                    "document_ids": docs,
                }
            )
            if len(out) >= limit:
                break
        return out

    def chunk_ids_for_node(self, node: Any) -> list[str]:
        """Resolve DocumentChunk labels linked via mention / statement incidence."""
        if self.is_empty() or self._entry is None:
            return []
        if not isinstance(node, (URIRef, str)):
            return []
        graph = self._entry.graph
        uri = URIRef(str(node)) if not isinstance(node, URIRef) else node
        chunks: set[str] = set()

        def _add_chunk(chunk: Any) -> None:
            lab = graph.value(chunk, RDFS.label)
            if lab is not None:
                chunks.add(str(lab))

        for chunk in graph.subjects(TKEIR.hasMention, uri):
            _add_chunk(chunk)
        for chunk in graph.objects(uri, TKEIR.mentionedIn):
            _add_chunk(chunk)
        for chunk in graph.subjects(TKEIR.hasStatement, uri):
            _add_chunk(chunk)
        # Reified statements that reference this node as subject/object.
        for stmt in graph.subjects(TKEIR.subject, uri):
            for chunk in graph.objects(stmt, TKEIR.inChunk):
                _add_chunk(chunk)
            for chunk in graph.subjects(TKEIR.hasStatement, stmt):
                _add_chunk(chunk)
        for stmt in graph.subjects(TKEIR.object, uri):
            for chunk in graph.objects(stmt, TKEIR.inChunk):
                _add_chunk(chunk)
            for chunk in graph.subjects(TKEIR.hasStatement, stmt):
                _add_chunk(chunk)
        # Document-level: any chunk under docs that mention this entity
        for doc in graph.subjects(TKEIR.hasMention, uri):
            if (doc, RDF.type, TKEIR.Document) in graph:
                for chunk in graph.objects(doc, TKEIR.hasChunk):
                    _add_chunk(chunk)
        return sorted(chunks)

    def document_ids_for_node(self, node: Any) -> list[str]:
        """Best-effort document ids from URI path or cached load list."""
        if self._entry is None:
            return []
        text = str(node)
        docs: set[str] = set(self._entry.document_ids)
        # http://tkeir.local/doc/<doc_key>/...
        marker = "http://tkeir.local/doc/"
        if text.startswith(marker):
            rest = text[len(marker) :]
            docs.add(rest.split("/", 1)[0])
        return sorted(docs)
