# -*- coding: utf-8 -*-
"""In-memory RDF graph merge and HMI-oriented ontology export."""

from __future__ import annotations

import re
from collections import defaultdict
from typing import Any

from rdflib import Graph, Literal, URIRef
from rdflib.namespace import RDF, RDFS, Namespace

from thot.core.KeywordRules import is_valid_keyword_label

TKEIR = Namespace("http://tkeir.local/ontology/")

_STRUCTURAL_ENTITY_TYPES = frozenset(
    {
        "Document",
        "DocumentChunk",
        "Keyword",
        "Tag",
        "Entity",
        "Metric",
    }
)


def detect_rdf_format(payload: str) -> str:
    """Detect whether an RDF payload is JSON-LD or Turtle.

    Example:
        >>> detect_rdf_format('[{"@id": "http://example.org/a"}]')
        'json-ld'
        >>> detect_rdf_format('@prefix ex: <http://example.org/> .')
        'turtle'
    """
    stripped = (payload or "").lstrip()
    if stripped.startswith("{") or stripped.startswith("["):
        return "json-ld"
    return "turtle"


def merge_rdf_graphs(rdf_documents: list[str]) -> Graph:
    """Merge multiple RDF payloads (JSON-LD or Turtle) into one graph.

    Args:
        rdf_documents: Serialized RDF graphs from pipeline documents or Vespa.

    Returns:
        Combined :class:`rdflib.Graph`.

    Example:
        >>> from thot.tools.search.ontology_utils import merge_rdf_graphs
        >>> graph = merge_rdf_graphs([
        ...     '[{"@id": "http://example.org/Alice", "@type": "http://example.org/Person"}]'
        ... ])
        >>> len(graph)
        1
    """
    graph = Graph()
    graph.bind("tkeir", TKEIR)
    for document in _unique_rdf_documents(rdf_documents):
        graph.parse(data=document, format=detect_rdf_format(document))
    return graph


def merge_turtle_graphs(turtle_documents: list[str]) -> Graph:
    """Merge multiple Turtle ontology payloads into one RDF graph.

    Args:
        turtle_documents: Serialized RDF graphs from pipeline documents.

    Returns:
        Combined :class:`rdflib.Graph`.

    Example:
        >>> from thot.tools.search.ontology_utils import merge_turtle_graphs
        >>> graph = merge_turtle_graphs([
        ...     '@prefix ex: <http://example.org/> .\\nex:Alice a ex:Person .'
        ... ])
        >>> len(graph)
        1
    """
    return merge_rdf_graphs(turtle_documents)


def serialize_graph_json_ld(graph: Graph) -> str:
    """Serialize an RDF graph as JSON-LD for storage or HMI display.

    Example:
        >>> from rdflib import Graph, URIRef
        >>> from rdflib.namespace import RDF
        >>> from thot.tools.search.ontology_utils import serialize_graph_json_ld
        >>> graph = Graph()
        >>> node = URIRef("http://example.org/Alice")
        >>> _ = graph.add((node, RDF.type, URIRef("http://example.org/Person")))
        >>> payload = serialize_graph_json_ld(graph)
        >>> payload.startswith('[')
        True
    """
    if len(graph) == 0:
        return "[]"
    return graph.serialize(format="json-ld")


_FOCUS_STOPWORDS = frozenset(
    {
        "who",
        "what",
        "when",
        "where",
        "why",
        "how",
        "had",
        "has",
        "have",
        "was",
        "were",
        "are",
        "been",
        "being",
        "the",
        "and",
        "for",
        "that",
        "this",
        "with",
        "from",
        "into",
        "your",
        "you",
        "did",
        "does",
        "do",
        "replace",
        "replaced",
    }
)


def _focus_query_terms(query_text: str) -> set[str]:
    """Return query terms suited for passage ranking (stopwords removed).

    Example:
        >>> terms = _focus_query_terms("Who report Yang had replace Donald Trump ?")
        >>> {"yang", "trump", "donald", "report"}.issubset(terms)
        True
    """
    terms = _query_terms(query_text) - _FOCUS_STOPWORDS
    return terms or _query_terms(query_text)


def _split_sentences(text: str) -> list[str]:
    """Split text into sentence-like spans for passage ranking.

    Example:
        >>> _split_sentences("Alice went home. Bob stayed.")
        ['Alice went home.', 'Bob stayed.']
    """
    parts = re.split(r"(?<=[.!?])\s+", text.strip())
    return [part.strip() for part in parts if part.strip()]


def _sentence_relevance(sentence: str, terms: set[str]) -> int:
    """Score a sentence by how many query terms it contains.

    Example:
        >>> _sentence_relevance("Andrew Yang replaced Trump", {"yang", "trump"})
        2
    """
    haystack = sentence.lower()
    return sum(1 for term in terms if term in haystack)


def extract_focus_passages(
    chunk_texts: list[tuple[str, str]],
    query_text: str,
    *,
    max_passages: int = 8,
) -> str:
    """Rank sentences from retrieved chunks that best match the user query.

    Args:
        chunk_texts: ``(chunk_id, text_raw)`` pairs in retrieval order.
        query_text: User question used to score sentences.
        max_passages: Maximum number of passages to return.

    Returns:
        Bullet list of focused passages or a fallback message.

    Example:
        >>> extract_focus_passages([
        ...     ("c1", "National Review reported Yang replaced Donald Trump."),
        ... ], "Who reported Yang Trump?")
        '- [c1] National Review reported Yang replaced Donald Trump.'
    """
    terms = _focus_query_terms(query_text)
    if not terms:
        return "No focused passages identified."

    scored: list[tuple[int, int, str, str]] = []
    min_score = 2 if len(terms) >= 2 else 1
    for rank, (chunk_id, text_raw) in enumerate(chunk_texts):
        for sentence in _split_sentences(text_raw):
            score = _sentence_relevance(sentence, terms)
            if score >= min_score:
                scored.append((score, -rank, chunk_id, sentence))

    if not scored:
        return "No focused passages identified."

    scored.sort(key=lambda item: (item[0], item[1]), reverse=True)
    lines = [
        f"- [{chunk_id}] {sentence}"
        for _score, _rank, chunk_id, sentence in scored[:max_passages]
    ]
    return "\n".join(lines)


def truncate_for_prompt(
    text: str,
    *,
    max_chars: int,
) -> str:
    """Truncate long text for LLM prompts while preserving the head.

    Example:
        >>> truncate_for_prompt("abcdef", max_chars=3)
        'abc…'
    """
    cleaned = text.strip()
    if len(cleaned) <= max_chars:
        return cleaned
    return f"{cleaned[:max_chars].rstrip()}…"


def _query_terms(query_text: str) -> set[str]:
    """Extract searchable terms from a user query.

    Args:
        query_text: Raw query string.

    Returns:
        Lowercased token set.

    Example:
        >>> "alice" in _query_terms("Who is Alice?")
        True
    """
    return {
        token
        for token in re.findall(
            r"[A-Za-z0-9][A-Za-z0-9'._-]{2,}", query_text.lower()
        )
    }


def extract_query_highlight_terms(query_text: str) -> list[str]:
    """Return query tokens and phrases for UI highlighting (longest first).

    Labels are taken from the user query surface form — no stopword list.

    Example:
        >>> "Charles Sutton" in extract_query_highlight_terms(
        ...     "In which document appears Charles Sutton"
        ... )
        True
    """
    query = (query_text or "").strip()
    if not query:
        return []

    tokens = re.findall(r"[A-Za-z0-9][A-Za-z0-9'._-]{2,}", query)
    if not tokens:
        return []

    seen: set[str] = set()
    labels: list[str] = []

    def add(label: str) -> None:
        key = label.lower()
        if key not in seen:
            seen.add(key)
            labels.append(label)

    if len(tokens) >= 2:
        for start in range(len(tokens)):
            for end in range(len(tokens), start, -1):
                add(" ".join(tokens[start:end]))

    for token in tokens:
        add(token)

    labels.sort(key=len, reverse=True)
    return labels


def highlight_query_terms_in_chunks(
    query_text: str,
    chunk_texts: list[str],
) -> list[str]:
    """Keep query highlight labels that appear in at least one chunk body.

    Example:
        >>> highlight_query_terms_in_chunks(
        ...     "Charles Sutton",
        ...     ["Active entities: Charles Sutton, AFLW."],
        ... )
        ['Charles Sutton', 'Charles', 'Sutton']
    """
    candidates = extract_query_highlight_terms(query_text)
    if not candidates or not chunk_texts:
        return candidates

    corpus = "\n".join(chunk_texts).lower()
    return [label for label in candidates if label.lower() in corpus]


def chunk_text_matches_query(query_text: str, chunk_text: str) -> bool:
    """Return whether any query term appears in a chunk body.

    Example:
        >>> chunk_text_matches_query("Charles Sutton", "Charles Sutton Medal")
        True
    """
    terms = _query_terms(query_text)
    if not terms:
        return False
    haystack = chunk_text.lower()
    return any(term in haystack for term in terms)


def prioritize_chunks_by_query_match(
    chunks: list[Any],
    query_text: str,
) -> list[Any]:
    """Sort chunks so query-matching bodies rank above pure vector matches.

    Example:
        >>> chunks = [
        ...     {"text_raw": "unrelated", "relevance": 0.9},
        ...     {"text_raw": "Charles Sutton Medal", "relevance": 0.5},
        ... ]
        >>> prioritize_chunks_by_query_match(chunks, "Charles Sutton")[0]["text_raw"]
        'Charles Sutton Medal'
    """
    terms = _query_terms(query_text)

    def match_score(chunk: Any) -> int:
        text = (
            chunk.text_raw
            if hasattr(chunk, "text_raw")
            else str(chunk.get("text_raw") or "")
        )
        haystack = text.lower()
        return sum(1 for term in terms if term in haystack)

    def relevance_score(chunk: Any) -> float:
        relevance = (
            chunk.relevance
            if hasattr(chunk, "relevance")
            else chunk.get("relevance")
        )
        return float(relevance or 0.0)

    return sorted(
        chunks,
        key=lambda chunk: (match_score(chunk), relevance_score(chunk)),
        reverse=True,
    )


def _node_label(graph: Graph, node: URIRef | Literal) -> str:
    """Return a human-readable label for an RDF node.

    Example:
        >>> from rdflib import Graph, Literal
        >>> _node_label(Graph(), Literal("Alice"))
        'Alice'
    """
    if isinstance(node, Literal):
        return str(node)
    label = graph.value(node, RDFS.label)
    if label is not None:
        return str(label)
    type_label = graph.value(node, RDF.type)
    if type_label is not None:
        return str(type_label).split("/")[-1].split("#")[-1]
    return str(node).split("/")[-1]


def _node_type(graph: Graph, node: URIRef) -> str:
    """Return the RDF type label for a URI node.

    Example:
        >>> from rdflib import Graph, URIRef
        >>> _node_type(Graph(), URIRef("http://example.org/Alice"))
        'Entity'
    """
    type_label = graph.value(node, RDF.type)
    if type_label is None:
        return "Entity"
    return str(type_label).split("/")[-1].split("#")[-1]


def _predicate_label(predicate: URIRef) -> str:
    """Return a short predicate label from a URI.

    Example:
        >>> from rdflib import URIRef
        >>> _predicate_label(URIRef("http://tkeir.local/ontology/worksAt"))
        'worksAt'
    """
    value = str(predicate)
    if value.startswith(str(TKEIR)):
        return value.rsplit("/", 1)[-1]
    return value.rsplit("/", 1)[-1].rsplit("#", 1)[-1]


def _chunk_uri_map(graph: Graph) -> dict[str, str]:
    """Map chunk URIs to human-readable labels in a graph.

    Example:
        >>> _chunk_uri_map(Graph())
        {}
    """
    mapping: dict[str, str] = {}
    for chunk_uri in graph.subjects(RDF.type, TKEIR.DocumentChunk):
        label = graph.value(chunk_uri, RDFS.label)
        if label is not None:
            mapping[str(chunk_uri)] = str(label)
    return mapping


def _unique_rdf_documents(rdf_documents: list[str]) -> list[str]:
    """Deduplicate non-empty RDF payloads.

    Example:
        >>> _unique_rdf_documents(['@prefix ex: <> .', '@prefix ex: <> .'])
        ['@prefix ex: <> .']
    """
    unique: list[str] = []
    seen: set[str] = set()
    for document in rdf_documents:
        payload = (document or "").strip()
        if not payload or payload in seen:
            continue
        seen.add(payload)
        unique.append(payload)
    return unique


def _unique_turtle_documents(turtle_documents: list[str]) -> list[str]:
    """Deduplicate non-empty Turtle payloads.

    Example:
        >>> _unique_turtle_documents(["@prefix ex: <> .", "@prefix ex: <> ."])
        ['@prefix ex: <> .']
    """
    return _unique_rdf_documents(turtle_documents)


def _document_uri_for_chunk(graph: Graph, chunk_uri: URIRef) -> URIRef | None:
    """Find the parent document URI linked to a chunk URI.

    Example:
        >>> _document_uri_for_chunk(Graph(), URIRef("http://example.org/chunk/1")) is None
        True
    """
    for doc_uri in graph.subjects(TKEIR.hasChunk, chunk_uri):
        if isinstance(doc_uri, URIRef):
            return doc_uri
    return None


def _keyword_in_chunk_text(keyword: str, chunk_text: str) -> bool:
    """Return whether a keyword appears in chunk text.

    Example:
        >>> _keyword_in_chunk_text("Paris", "The capital is Paris.")
        True
    """
    keyword_text = keyword.strip().lower()
    if not keyword_text:
        return False
    haystack = chunk_text.lower()
    if keyword_text in haystack:
        return True
    return any(
        part in haystack for part in keyword_text.split() if len(part) > 3
    )


def build_hmi_ontology(
    rdf_documents: list[str],
    retrieved_chunk_ids: list[str],
    *,
    chunk_texts: dict[str, str] | None = None,
    max_entities: int = 120,
    max_keywords: int = 60,
    min_keyword_length: int = 3,
) -> dict[str, Any]:
    """Export chunk-linked NER entities, keywords, and JSON-LD for HMI display.

    Args:
        rdf_documents: Parent document RDF payloads from Vespa (JSON-LD or Turtle).
        retrieved_chunk_ids: Chunk ids returned by hybrid search.
        chunk_texts: Optional map of ``chunk_id`` to indexed text for keyword linking.
        max_entities: Maximum number of entity records to return.
        max_keywords: Maximum number of keyword records to return.
        min_keyword_length: Minimum character length for exported keyword labels.

    Returns:
        Dict with ``entities``, ``keywords``, and ``json_ld``; entity items contain
        ``label``, ``chunk_ids``, and ``type``.

    Example:
        >>> from thot.tools.search.ontology_utils import build_hmi_ontology
        >>> build_hmi_ontology([], [])
        {'entities': [], 'keywords': [], 'json_ld': '[]'}
    """
    graph = merge_rdf_graphs(_unique_rdf_documents(rdf_documents))
    if len(graph) == 0:
        return {"entities": [], "keywords": [], "json_ld": "[]"}

    chunk_texts = chunk_texts or {}
    chunk_uri_by_id = {
        chunk_id: uri for uri, chunk_id in _chunk_uri_map(graph).items()
    }
    retrieved_ids = [
        chunk_id
        for chunk_id in retrieved_chunk_ids
        if chunk_id in chunk_uri_by_id
    ]

    entity_chunks: dict[tuple[str, str], set[str]] = defaultdict(set)
    keyword_chunks: dict[str, set[str]] = defaultdict(set)
    chunks_by_doc: dict[str, set[str]] = defaultdict(set)

    for chunk_id in retrieved_ids:
        chunk_uri = URIRef(chunk_uri_by_id[chunk_id])
        doc_uri = _document_uri_for_chunk(graph, chunk_uri)
        if doc_uri is not None:
            chunks_by_doc[str(doc_uri)].add(chunk_id)

        for _subject, _predicate, entity in graph.triples(
            (chunk_uri, TKEIR.hasMention, None)
        ):
            if not isinstance(entity, URIRef):
                continue
            entity_type = _node_type(graph, entity)
            if entity_type in _STRUCTURAL_ENTITY_TYPES:
                continue
            label = _node_label(graph, entity).strip()
            if not label:
                continue
            entity_chunks[(label, entity_type)].add(chunk_id)

    for doc_uri, chunk_ids in chunks_by_doc.items():
        doc_ref = URIRef(doc_uri)
        for _subject, _predicate, keyword_node in graph.triples(
            (doc_ref, TKEIR.hasKeyword, None)
        ):
            if not isinstance(keyword_node, URIRef):
                continue
            if _node_type(graph, keyword_node) != "Keyword":
                continue
            label = _node_label(graph, keyword_node).strip()
            if not label or not is_valid_keyword_label(
                label,
                min_length=min_keyword_length,
            ):
                continue
            for chunk_id in chunk_ids:
                if _keyword_in_chunk_text(
                    label, chunk_texts.get(chunk_id, "")
                ):
                    keyword_chunks[label].add(chunk_id)

    entities = [
        {
            "label": label,
            "type": entity_type,
            "chunk_ids": sorted(chunk_ids),
        }
        for (label, entity_type), chunk_ids in sorted(
            entity_chunks.items(),
            key=lambda item: (-len(item[1]), item[0][0].lower()),
        )[:max_entities]
    ]
    keywords = [
        {
            "label": label,
            "chunk_ids": sorted(chunk_ids),
        }
        for label, chunk_ids in sorted(
            keyword_chunks.items(),
            key=lambda item: (-len(item[1]), item[0].lower()),
        )[:max_keywords]
        if chunk_ids
    ]
    return {
        "entities": entities,
        "keywords": keywords,
        "json_ld": serialize_graph_json_ld(graph),
    }


def extract_relevant_triples(
    graph: Graph,
    query_text: str,
    *,
    max_triples: int = 60,
) -> list[str]:
    """Select triple lines whose labels match query terms.

    Args:
        graph: Merged RDF graph from parent documents.
        query_text: User question used to filter triples.
        max_triples: Maximum number of triple lines to return.

    Returns:
        Human-readable ``subject | predicate | object`` lines.

    Example:
        >>> from rdflib import Graph, Literal, URIRef
        >>> from thot.tools.search.ontology_utils import extract_relevant_triples
        >>> graph = Graph()
        >>> alice = URIRef("http://example.org/Alice")
        >>> _ = graph.add((alice, URIRef("http://example.org/type"), Literal("Person")))
        >>> lines = extract_relevant_triples(graph, "Alice")
        >>> any("Alice" in line for line in lines)
        True
    """
    terms = _query_terms(query_text)
    selected: list[str] = []
    for subject, predicate, obj in graph:
        subject_label = _node_label(graph, subject)
        object_label = _node_label(graph, obj)
        predicate_label = _predicate_label(predicate)
        line = f"{subject_label} | {predicate_label} | {object_label}"
        haystack = line.lower()
        if not terms or any(term in haystack for term in terms):
            selected.append(line)
        if len(selected) >= max_triples:
            break
    return selected


def summarize_graph_for_prompt(
    graph: Graph,
    query_text: str,
    *,
    max_triples: int = 60,
) -> str:
    """Format graph triples as bullet lines for LLM prompts.

    Args:
        graph: Merged RDF graph.
        query_text: User question used to prioritize triples.
        max_triples: Maximum triples in the summary.

    Returns:
        Markdown-style bullet list or a fallback message.

    Example:
        >>> from rdflib import Graph
        >>> from thot.tools.search.ontology_utils import summarize_graph_for_prompt
        >>> summarize_graph_for_prompt(Graph(), "anything")
        'No structured facts available.'
    """
    if len(graph) == 0:
        return "No structured facts available."
    relevant = extract_relevant_triples(
        graph,
        query_text,
        max_triples=max_triples,
    )
    if relevant:
        return "\n".join(f"- {line}" for line in relevant)
    fallback = []
    for subject, predicate, obj in list(graph)[:max_triples]:
        fallback.append(
            f"- {_node_label(graph, subject)} | {_predicate_label(predicate)} | {_node_label(graph, obj)}"
        )
    return "\n".join(fallback)
