# -*- coding: utf-8 -*-
"""In-memory RDF graph merge and HMI-oriented ontology export."""

from __future__ import annotations

import re
from collections import defaultdict
from typing import Any

from rdflib import Graph, Literal, URIRef
from rdflib.namespace import RDF, RDFS, Namespace

from thot.core.KeywordRules import is_valid_keyword_label
from thot.tools.search.chunk_index_labels import is_chunk_protocol_sentence
from thot.tools.search.vespa_client import (
    clean_chunk_text_for_prompt,
    trim_passage_leading_noise,
)

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

_STRUCTURAL_PREDICATES = frozenset(
    {
        TKEIR.hasStatement,
        TKEIR.hasChunk,
        TKEIR.hasMention,
        TKEIR.hasKeyword,
        TKEIR.hasTag,
        TKEIR.isTagOf,
        TKEIR.hasNumericValue,
        RDF.type,
        RDFS.label,
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


def _focus_query_terms(
    query_text: str,
    analysis: dict[str, Any] | None = None,
) -> set[str]:
    """Return query terms suited for passage ranking.

    Prefers NLP lemmas/search terms from query analysis when available.

    Example:
        >>> terms = _focus_query_terms("Who report Yang had replace Donald Trump ?")
        >>> {"yang", "trump", "donald"}.issubset(terms)
        True
    """
    if analysis:
        ranked: list[str] = []
        for key in ("lemmas", "search_terms"):
            for token in analysis.get(key) or []:
                text = str(token).strip().lower()
                if len(text) >= 2:
                    ranked.append(text)
        if ranked:
            return set(ranked)
    return _query_terms(query_text)


def _is_metadata_sentence(sentence: str) -> bool:
    """Return whether a sentence is indexing metadata rather than body text.

    Example:
        >>> _is_metadata_sentence("Topic: critic Jon Landau regards song")
        True
    """
    return is_chunk_protocol_sentence(sentence)


def _split_sentences(text: str) -> list[str]:
    """Split text into sentence-like spans for passage ranking.

    Example:
        >>> _split_sentences("Alice went home. Bob stayed.")
        ['Alice went home.', 'Bob stayed.']
    """
    cleaned = clean_chunk_text_for_prompt(text)
    parts = re.split(r"(?<=[.!?])\s+", cleaned.strip())
    return [
        part.strip()
        for part in parts
        if part.strip()
        and (len(part.strip()) > 15 or part.endswith((".", "!", "?")))
    ]


def _sentence_relevance(
    sentence: str, terms: set[str], query_text: str = ""
) -> int:
    """Score a sentence by query term and phrase overlap.

    Example:
        >>> _sentence_relevance(
        ...     "George Harrison liked Abbey Road",
        ...     {"abbey", "road", "album"},
        ...     "Abbey Road album",
        ... )
        5
    """
    if _is_metadata_sentence(sentence):
        return -10
    haystack = sentence.lower()
    score = sum(1 for term in terms if term in haystack)
    if query_text:
        for label in extract_query_highlight_terms(query_text):
            if len(label.split()) >= 2 and label.lower() in haystack:
                score += 3
    return score


def _window_proximity_score(
    sentences: list[str],
    start: int,
    end: int,
    terms: set[str],
    query_text: str,
    sentence_scores: list[int],
) -> int:
    """Score a contiguous window by query overlap divided by sentence span.

    Tighter windows with strong query alignment rank above loose windows that
    include distant filler sentences.

    Example:
        >>> sentences = [
        ...     "Unrelated filler about music.",
        ...     "George Harrison liked Abbey Road.",
        ...     "More unrelated filler.",
        ... ]
        >>> scores = [
        ...     _sentence_relevance(s, {"abbey", "road", "harrison"}, "Abbey Road")
        ...     for s in sentences
        ... ]
        >>> tight = _window_proximity_score(
        ...     sentences, 1, 1, {"abbey", "road", "harrison"}, "Abbey Road", scores
        ... )
        >>> loose = _window_proximity_score(
        ...     sentences, 0, 2, {"abbey", "road", "harrison"}, "Abbey Road", scores
        ... )
        >>> tight > loose
        True
    """
    span = end - start + 1
    if span <= 0:
        return 0
    window_sentences = sentences[start : end + 1]
    if all(_is_metadata_sentence(sentence) for sentence in window_sentences):
        return -10_000

    total = sum(sentence_scores[start : end + 1])
    window_text = " ".join(window_sentences).lower()
    term_coverage = sum(1 for term in terms if term in window_text)
    phrase_bonus = 0
    if query_text:
        for label in extract_query_highlight_terms(query_text):
            if len(label.split()) >= 2 and label.lower() in window_text:
                phrase_bonus += 4

    numer = total + term_coverage + phrase_bonus
    return (numer * 1000) // span if numer > 0 else 0


def _find_best_proximity_passage(
    sentences: list[str],
    terms: set[str],
    query_text: str,
    *,
    min_sentence_score: int,
    max_chars: int,
    context_sentences: int,
) -> tuple[str, int] | None:
    """Return the tightest window whose sentences best match the query.

    Example:
        >>> result = _find_best_proximity_passage(
        ...     ["Alice arrived.", "Bob reported the claim.", "Later events."],
        ...     {"bob", "report"},
        ...     "Who reported the claim?",
        ...     min_sentence_score=1,
        ...     max_chars=500,
        ...     context_sentences=1,
        ... )
        >>> result is not None and "Bob reported" in result[0]
        True
    """
    if not sentences:
        return None

    sentence_scores = [
        _sentence_relevance(sentence, terms, query_text)
        for sentence in sentences
    ]
    if not any(score >= min_sentence_score for score in sentence_scores):
        return None

    best_score = -1
    best_start = 0
    best_end = 0
    for start, _sentence in enumerate(sentences):
        for end in range(start, len(sentences)):
            if not any(
                sentence_scores[index] >= min_sentence_score
                for index in range(start, end + 1)
            ):
                continue
            score = _window_proximity_score(
                sentences,
                start,
                end,
                terms,
                query_text,
                sentence_scores,
            )
            if score > best_score:
                best_score = score
                best_start = start
                best_end = end

    start = max(0, best_start - max(0, context_sentences))
    end = min(len(sentences) - 1, best_end + max(0, context_sentences))
    passage = truncate_for_prompt(
        " ".join(sentences[start : end + 1]),
        max_chars=max_chars,
    )
    return passage, best_score


def _build_passage_window(
    sentences: list[str],
    center_index: int,
    *,
    before: int,
    after: int,
    max_chars: int,
) -> str:
    """Join neighboring sentences around a high-scoring sentence for context.

    Example:
        >>> sentences = ["Alice arrived.", "Bob reported the claim.", "Later events."]
        >>> window = _build_passage_window(sentences, 1, before=1, after=1, max_chars=500)
        >>> "Alice arrived." in window and "Later events." in window
        True
    """
    start = max(0, center_index - before)
    end = min(len(sentences), center_index + after + 1)
    passage = " ".join(sentences[start:end])
    return truncate_for_prompt(passage, max_chars=max_chars)


def _dedupe_focus_passages(
    scored: list[tuple[int, int, str, str]],
    *,
    max_passages: int,
) -> list[tuple[int, int, str, str]]:
    """Drop overlapping passages from the same chunk, keeping higher scores.

    Example:
        >>> scored = [
        ...     (10, 0, "c1", "Alice arrived. Bob reported."),
        ...     (8, 1, "c1", "Bob reported the claim."),
        ... ]
        >>> kept = _dedupe_focus_passages(scored, max_passages=2)
        >>> len(kept) == 2 and kept[0][0] > kept[1][0]
        True
    """
    selected: list[tuple[int, int, str, str]] = []
    for item in scored:
        _score, _rank, chunk_id, passage = item
        passage_lower = passage.lower()
        if any(
            existing_chunk == chunk_id
            and (
                passage_lower in existing_passage.lower()
                or existing_passage.lower() in passage_lower
            )
            for _s, _r, existing_chunk, existing_passage in selected
        ):
            continue
        selected.append(item)
        if len(selected) >= max_passages:
            break
    return selected


def extract_focus_passages(
    chunk_texts: list[tuple[str, str]],
    query_text: str,
    *,
    max_passages: int = 8,
    context_sentences: int = 2,
    max_chars_per_passage: int = 1800,
) -> str:
    """Rank tight sentence windows in each chunk that best match the query.

    Args:
        chunk_texts: ``(chunk_id, text_raw)`` pairs in retrieval order.
        query_text: User question used to score sentences.
        max_passages: Maximum number of passages to return.
        context_sentences: Optional padding around the best proximity window.
        max_chars_per_passage: Maximum characters kept per expanded passage.

    Returns:
        Bullet list of focused passages or a fallback message.

    Example:
        >>> text = (
        ...     "Unrelated music essay. "
        ...     "National Review reported Yang replaced Donald Trump. "
        ...     "More unrelated music content."
        ... )
        >>> passages = extract_focus_passages(
        ...     [("c1", text)],
        ...     "Who report Yang Trump?",
        ...     context_sentences=0,
        ... )
        >>> "National Review" in passages and "Unrelated music essay" not in passages
        True
    """
    terms = _focus_query_terms(query_text)
    if not terms:
        return "No focused passages identified."

    scored: list[tuple[int, int, str, str]] = []
    min_score = 2 if len(terms) >= 2 else 1
    context = max(0, context_sentences)
    for rank, (chunk_id, text_raw) in enumerate(chunk_texts):
        sentences = _split_sentences(text_raw)
        result = _find_best_proximity_passage(
            sentences,
            terms,
            query_text,
            min_sentence_score=min_score,
            max_chars=max_chars_per_passage,
            context_sentences=context,
        )
        if result is None:
            continue
        passage, score = result
        scored.append((score, -rank, chunk_id, passage))

    if not scored:
        return "No focused passages identified."

    scored.sort(key=lambda item: (item[0], item[1]), reverse=True)
    selected = _dedupe_focus_passages(scored, max_passages=max_passages)
    focal_entity = query_text.strip() if len(query_text.split()) <= 5 else ""
    lines = [
        f"- [{chunk_id}] {trim_passage_leading_noise(passage, focal_entity)}"
        for _score, _rank, chunk_id, passage in selected
    ]
    return "\n".join(line for line in lines if line.split("]", 1)[-1].strip())


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


def _distinctive_query_phrases(query_text: str) -> list[str]:
    """Return high-precision phrases for scoping prompt chunks to the query.

    Example:
        >>> _distinctive_query_phrases("Who interpret the album Abbey Road")
        ['abbey road']
    """
    tokens = re.findall(r"[A-Za-z0-9][A-Za-z0-9'._-]{2,}", query_text or "")
    phrases: list[str] = []
    for index in range(len(tokens) - 1):
        left, right = tokens[index], tokens[index + 1]
        if left[:1].isupper() and right[:1].isupper():
            phrases.append(f"{left} {right}".lower())
    if phrases:
        return list(dict.fromkeys(phrases))

    multi_word = [
        label
        for label in extract_query_highlight_terms(query_text)
        if len(label.split()) >= 2
    ]
    multi_word.sort(key=len, reverse=True)
    return [label.lower() for label in multi_word[:2]]


def filter_query_relevant_chunks(
    chunks: list[Any],
    query_text: str,
    *,
    max_chunks: int = 8,
) -> list[Any]:
    """Keep chunks whose cleaned body matches the query for prompt assembly.

    Example:
        >>> chunks = [
        ...     {"text_raw": "George Harrison liked Abbey Road.", "relevance": 0.9},
        ...     {"text_raw": "Unrelated vaporwave essay.", "relevance": 0.95},
        ... ]
        >>> kept = filter_query_relevant_chunks(chunks, "Abbey Road")
        >>> kept[0]["text_raw"].startswith("George")
        True
    """
    ranked = prioritize_chunks_by_query_match(chunks, query_text)
    key_phrases = _distinctive_query_phrases(query_text)
    if key_phrases:
        phrase_matching = [
            chunk
            for chunk in ranked
            if any(
                phrase
                in clean_chunk_text_for_prompt(
                    chunk.text_raw
                    if hasattr(chunk, "text_raw")
                    else str(chunk.get("text_raw") or "")
                ).lower()
                for phrase in key_phrases
            )
        ]
        if phrase_matching:
            return phrase_matching[:max_chunks]

    matching = [
        chunk
        for chunk in ranked
        if chunk_text_matches_query(
            query_text,
            clean_chunk_text_for_prompt(
                chunk.text_raw
                if hasattr(chunk, "text_raw")
                else str(chunk.get("text_raw") or "")
            ),
        )
    ]
    if matching:
        return matching[:max_chunks]
    return ranked[:max_chunks]


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


def _is_structural_subject(graph: Graph, subject: URIRef | Literal) -> bool:
    """Return whether a subject node is a structural entity type.

    Example:
        >>> from thot.tools.search.ontology_utils import _is_structural_subject
        >>> from rdflib import Graph, Literal
        >>> _is_structural_subject(Graph(), Literal("chunk-1"))
        True
    """
    if not isinstance(subject, URIRef):
        return True
    return _node_type(graph, subject) in _STRUCTURAL_ENTITY_TYPES


def _chunk_entity_uris(graph: Graph, chunk_ids: list[str]) -> set[str]:
    """Return entity URIs mentioned in the requested chunk ids.

    Example:
        >>> from thot.tools.search.ontology_utils import _chunk_entity_uris
        >>> from rdflib import Graph
        >>> _chunk_entity_uris(Graph(), [])
        set()
    """
    id_to_uri = {
        chunk_id: uri for uri, chunk_id in _chunk_uri_map(graph).items()
    }
    entities: set[str] = set()
    for chunk_id in chunk_ids:
        chunk_uri = id_to_uri.get(chunk_id)
        if not chunk_uri:
            continue
        for _subject, _predicate, entity in graph.triples(
            (URIRef(chunk_uri), TKEIR.hasMention, None)
        ):
            if isinstance(entity, URIRef):
                entities.add(str(entity))
    return entities


def extract_deduplicated_svo_triples(
    graph: Graph,
    query_text: str = "",
    *,
    chunk_ids: list[str] | None = None,
    max_triples: int = 80,
) -> list[str]:
    """Extract deduplicated subject-verb-object lines from an ontology graph.

    Keeps semantic predicates between typed entities or literals, scoped to
    entities linked to ``chunk_ids`` when provided.

    Example:
        >>> from thot.tools.search.ontology_utils import (
        ...     extract_deduplicated_svo_triples,
        ...     merge_turtle_graphs,
        ... )
        >>> turtle = '''
        ... @prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
        ... @prefix tkeir: <http://tkeir.local/ontology/> .
        ... @prefix tkeirdoc: <http://tkeir.local/doc/> .
        ... tkeirdoc:doc_a a tkeir:Document ;
        ...     tkeir:hasChunk <http://tkeir.local/doc/doc_a/Chunk/chunk_1> .
        ... <http://tkeir.local/doc/doc_a/Chunk/chunk_1> a tkeir:DocumentChunk ;
        ...     rdfs:label "doc.pdf#chunk-1" ;
        ...     tkeir:hasMention <http://tkeir.local/doc/doc_a/Company/acme> .
        ... <http://tkeir.local/doc/doc_a/Company/acme> a tkeir:Company ;
        ...     rdfs:label "Acme" ;
        ...     tkeir:createdBy <http://tkeir.local/doc/doc_a/Product/widget> .
        ... <http://tkeir.local/doc/doc_a/Product/widget> a tkeir:Product ;
        ...     rdfs:label "Widget" .
        ... '''
        >>> graph = merge_turtle_graphs([turtle])
        >>> lines = extract_deduplicated_svo_triples(
        ...     graph,
        ...     "Acme",
        ...     chunk_ids=["doc.pdf#chunk-1"],
        ... )
        >>> lines
        ['Acme | createdBy | Widget']
    """
    if len(graph) == 0:
        return []

    chunk_entities: set[str] | None
    if chunk_ids is None:
        chunk_entities = None
    else:
        chunk_entities = _chunk_entity_uris(graph, chunk_ids)
        if not chunk_entities:
            return []

    terms = _query_terms(query_text)
    matched: list[str] = []
    fallback: list[str] = []
    seen: set[tuple[str, str, str]] = set()

    for subject, predicate, obj in graph:
        if predicate in _STRUCTURAL_PREDICATES:
            continue
        if _is_structural_subject(graph, subject):
            continue

        subject_uri = str(subject) if isinstance(subject, URIRef) else ""
        object_uri = str(obj) if isinstance(obj, URIRef) else ""
        if chunk_entities is not None:
            if (
                subject_uri not in chunk_entities
                and object_uri not in chunk_entities
            ):
                continue

        subject_label = _node_label(graph, subject).strip()
        predicate_label = _predicate_label(predicate).strip()
        object_label = _node_label(graph, obj).strip()
        if not subject_label or not predicate_label:
            continue

        key = (
            subject_label.lower(),
            predicate_label.lower(),
            object_label.lower(),
        )
        if key in seen:
            continue
        seen.add(key)

        line = f"{subject_label} | {predicate_label} | {object_label}"
        haystack = line.lower()
        if terms and any(term in haystack for term in terms):
            matched.append(line)
        else:
            fallback.append(line)

    selected = matched + fallback
    return selected[:max_triples]


def format_svo_ontology_context(
    graph: Graph,
    query_text: str,
    chunks: list[Any],
    *,
    empty_message: str,
    max_triples: int = 80,
) -> str:
    """Format deduplicated ontology SVO lines for LLM prompt injection.

    Example:
        >>> from thot.tools.search.app import RetrievedChunk
        >>> from thot.tools.search.ontology_utils import (
        ...     format_svo_ontology_context,
        ...     merge_turtle_graphs,
        ... )
        >>> turtle = '''
        ... @prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
        ... @prefix tkeir: <http://tkeir.local/ontology/> .
        ... @prefix tkeirdoc: <http://tkeir.local/doc/> .
        ... tkeirdoc:doc_a a tkeir:Document ;
        ...     tkeir:hasChunk <http://tkeir.local/doc/doc_a/Chunk/chunk_1> .
        ... <http://tkeir.local/doc/doc_a/Chunk/chunk_1> a tkeir:DocumentChunk ;
        ...     rdfs:label "c1" ;
        ...     tkeir:hasMention <http://tkeir.local/doc/doc_a/Company/acme> .
        ... <http://tkeir.local/doc/doc_a/Company/acme> a tkeir:Company ;
        ...     rdfs:label "Acme" ;
        ...     tkeir:createdBy <http://tkeir.local/doc/doc_a/Product/widget> .
        ... <http://tkeir.local/doc/doc_a/Product/widget> a tkeir:Product ;
        ...     rdfs:label "Widget" .
        ... '''
        >>> graph = merge_turtle_graphs([turtle])
        >>> chunk = RetrievedChunk(
        ...     chunk_id="c1",
        ...     text_raw="Acme launched Widget.",
        ...     parent_doc_id="file://doc.pdf",
        ... )
        >>> text = format_svo_ontology_context(
        ...     graph,
        ...     "Acme",
        ...     [chunk],
        ...     empty_message="none",
        ... )
        >>> "Acme | createdBy | Widget" in text
        True
    """
    chunk_ids = [
        str(
            chunk.chunk_id if hasattr(chunk, "chunk_id") else chunk["chunk_id"]
        )
        for chunk in chunks
    ]
    triples = extract_deduplicated_svo_triples(
        graph,
        query_text,
        chunk_ids=chunk_ids,
        max_triples=max_triples,
    )
    if not triples:
        return empty_message
    return "\n".join(f"- {line}" for line in triples)
