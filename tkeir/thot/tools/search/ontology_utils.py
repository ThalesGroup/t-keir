"""Title: Ontology utils

In-memory RDF graph merge and HMI-oriented ontology export.

Author: Eric Blaudez

Copyright (c) 2026 Thales
Licensed under the MIT License.
"""

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
        "SubOntology",
        "Statement",
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
        TKEIR.importanceScore,
        TKEIR.linkWeight,
        TKEIR.mentionedIn,
        TKEIR.inChunk,
        TKEIR.hasSubOntology,
        TKEIR.subject,
        TKEIR.predicate,
        TKEIR.object,
        TKEIR.chunkSupport,
        TKEIR.sharedConceptCount,
        TKEIR.intersectionWeight,
        RDF.type,
        RDFS.label,
    }
)

_STRUCTURAL_PREDICATE_LABELS = frozenset(
    {
        "haskeyword",
        "hasmention",
        "haschunk",
        "hasstatement",
        "hastag",
        "istagof",
        "hascontent",
        "hasnumericvalue",
        "importancescore",
        "linkweight",
        "mentionedin",
        "inchunk",
        "hassubontology",
        "subject",
        "predicate",
        "object",
        "chunksupport",
        "sharedconceptcount",
        "intersectionweight",
        "type",
        "label",
    }
)


def _is_structural_predicate_label(predicate: str) -> bool:
    """Is structural predicate label.

    Example:
        >>> from thot.tools.search.ontology_utils import _is_structural_predicate_label
        >>> _is_structural_predicate_label("hasKeyword")
        True
    """

    compact = (
        (predicate or "")
        .casefold()
        .replace("_", "")
        .replace("-", "")
        .replace(" ", "")
    )
    return compact in _STRUCTURAL_PREDICATE_LABELS


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
    analysis: dict[str, Any] | None = None,
) -> str:
    """Rank tight sentence windows in each chunk that best match the query.

    Args:
        chunk_texts: ``(chunk_id, text_raw)`` pairs in retrieval order.
        query_text: User question used to score sentences.
        max_passages: Maximum number of passages to return.
        context_sentences: Optional padding around the best proximity window.
        max_chars_per_passage: Maximum characters kept per expanded passage.
        analysis: Optional NLP analysis (lemmas / search_terms) for scoring.

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
    terms = _focus_query_terms(query_text, analysis)
    if not terms:
        return "No focused passages identified."

    scored: list[tuple[int, int, str, str]] = []
    # Entity-centric questions often have 1–2 content terms (e.g. Suez); requiring
    # two overlapping tokens then yields empty KEY PASSAGES and an unavailable LLM.
    min_score = 1 if len(terms) <= 2 else 2
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

    if not scored and min_score > 1:
        # Soft fallback: accept single-term entity hits.
        for rank, (chunk_id, text_raw) in enumerate(chunk_texts):
            sentences = _split_sentences(text_raw)
            result = _find_best_proximity_passage(
                sentences,
                terms,
                query_text,
                min_sentence_score=1,
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


def _query_terms(
    query_text: str,
    *,
    content_terms: set[str] | list[str] | None = None,
) -> set[str]:
    """Extract searchable terms from a user query.

    When ``content_terms`` is provided (NLP lemmas / search terms), those are
    used instead of whitespace tokens so interrogatives like ``What`` do not
    match unrelated ``what appeared…`` passages.

    Args:
        query_text: Raw query string.
        content_terms: Optional NLP content terms to prefer.

    Returns:
        Lowercased token set.

    Example:
        >>> "alice" in _query_terms("Who is Alice?")
        True
        >>> _query_terms("What happen at Suez", content_terms={"Suez"})
        {'suez'}
    """
    if content_terms is not None:
        return {
            str(term).strip().lower()
            for term in content_terms
            if str(term).strip() and len(str(term).strip()) >= 2
        }
    return {
        token
        for token in re.findall(
            r"[A-Za-z0-9][A-Za-z0-9'._-]{2,}", query_text.lower()
        )
    }


def extract_query_highlight_terms(
    query_text: str,
    *,
    content_terms: set[str] | list[str] | None = None,
    morphosyntax: list[dict[str, Any]] | None = None,
) -> list[str]:
    """Return query tokens and phrases for UI highlighting (longest first).

    When ``morphosyntax`` / ``content_terms`` from the NLP pipeline are given,
    closed-class POS tokens (DET, PRON, CCONJ, ADP, …) such as ``and`` /
    ``the`` are excluded so reports do not highlight stopwords.

    Example:
        >>> "Charles Sutton" in extract_query_highlight_terms(
        ...     "In which document appears Charles Sutton"
        ... )
        True
        >>> "and" not in [
        ...     t.lower()
        ...     for t in extract_query_highlight_terms(
        ...         "risks and recommended attention",
        ...         morphosyntax=[
        ...             {"text": "risks", "lemma": "risk", "pos": "NOUN"},
        ...             {"text": "and", "lemma": "and", "pos": "CCONJ"},
        ...             {"text": "recommended", "lemma": "recommend", "pos": "VERB"},
        ...             {"text": "attention", "lemma": "attention", "pos": "NOUN"},
        ...         ],
        ...     )
        ... ]
        True
    """
    from thot.tools.search.query_analyzer import (
        content_terms_from_morphosyntax,
    )

    query = (query_text or "").strip()
    if not query:
        return []

    tokens = re.findall(r"[A-Za-z0-9][A-Za-z0-9'._-]{2,}", query)
    if not tokens:
        return []

    allowed: set[str] | None = None
    if morphosyntax is not None or content_terms is not None:
        allowed = {
            str(term).strip().lower()
            for term in content_terms or []
            if str(term).strip()
        }
        if morphosyntax:
            allowed |= {
                term.lower()
                for term in content_terms_from_morphosyntax(morphosyntax)
            }

    seen: set[str] = set()
    labels: list[str] = []

    def add(label: str) -> None:
        key = label.lower()
        if key in seen:
            return
        if allowed is not None:
            parts = [part.lower() for part in label.split() if part]
            # Keep multi-word phrases that contain ≥1 content token; drop
            # pure closed-class singles like "and" / "the" / "for".
            if not parts or not any(part in allowed for part in parts):
                return
            if len(parts) == 1 and parts[0] not in allowed:
                return
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
    *,
    content_terms: set[str] | list[str] | None = None,
    morphosyntax: list[dict[str, Any]] | None = None,
) -> list[str]:
    """Keep query highlight labels that appear in at least one chunk body.

    Example:
        >>> highlight_query_terms_in_chunks(
        ...     "Charles Sutton",
        ...     ["Active entities: Charles Sutton, AFLW."],
        ... )
        ['Charles Sutton', 'Charles', 'Sutton']
    """
    candidates = extract_query_highlight_terms(
        query_text,
        content_terms=content_terms,
        morphosyntax=morphosyntax,
    )
    if not candidates or not chunk_texts:
        return candidates

    corpus = "\n".join(chunk_texts).lower()
    return [label for label in candidates if label.lower() in corpus]


def chunk_text_matches_query(
    query_text: str,
    chunk_text: str,
    *,
    content_terms: set[str] | list[str] | None = None,
) -> bool:
    """Return whether any query term appears in a chunk body.

    Example:
        >>> chunk_text_matches_query("Charles Sutton", "Charles Sutton Medal")
        True
        >>> chunk_text_matches_query(
        ...     "What happen at Suez",
        ...     "Source observed what appeared to be a UAV",
        ...     content_terms={"Suez"},
        ... )
        False
    """
    terms = _query_terms(query_text, content_terms=content_terms)
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

    Prefer *maximal* capitalized spans (``MT RED SEA EAGLE``) over adjacent
    bigrams (``red sea``), which otherwise match geographic noise.

    Example:
        >>> _distinctive_query_phrases("Who interpret the album Abbey Road")
        ['abbey road']
        >>> _distinctive_query_phrases(
        ...     "Tell me everything about MT RED SEA EAGLE"
        ... )[0]
        'mt red sea eagle'
    """
    tokens = re.findall(r"[A-Za-z0-9][A-Za-z0-9'._-]*", query_text or "")
    # Keep short ALL-CAPS vessel prefixes (MT, MV, SS, …) and drop other tiny tokens.
    cleaned_tokens: list[str] = []
    for token in tokens:
        token = token.strip("._-")
        if not token:
            continue
        if len(token) >= 3 or (len(token) == 2 and token.isupper()):
            cleaned_tokens.append(token)
    tokens = cleaned_tokens
    phrases: list[str] = []
    index = 0
    while index < len(tokens):
        token = tokens[index]
        if token[:1].isupper():
            end = index + 1
            while end < len(tokens) and tokens[end][:1].isupper():
                end += 1
            if end - index >= 2:
                phrases.append(" ".join(tokens[index:end]).lower())
            index = end
            continue
        index += 1
    if phrases:
        # Longest first; keep unique.
        phrases.sort(key=len, reverse=True)
        return list(dict.fromkeys(phrases))

    multi_word = [
        label
        for label in extract_query_highlight_terms(query_text)
        if len(label.split()) >= 2
    ]
    multi_word.sort(key=len, reverse=True)
    return [label.lower() for label in multi_word[:2]]


def _chunk_prompt_text(chunk: Any) -> str:
    """Chunk prompt text.

    Example:
        >>> from thot.tools.search.ontology_utils import _chunk_prompt_text
        >>> _chunk_prompt_text({"text_raw": "Hello"})
        'hello'
    """

    raw = (
        chunk.text_raw
        if hasattr(chunk, "text_raw")
        else str(chunk.get("text_raw") or chunk.get("text") or "")
    )
    return clean_chunk_text_for_prompt(raw).lower()


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
    # Try longest phrase first so "mt red sea eagle" wins over "red sea".
    for phrase in key_phrases:
        phrase_matching = [
            chunk for chunk in ranked if phrase in _chunk_prompt_text(chunk)
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


def _collect_entity_chunks_for_retrieved(
    graph: Graph,
    retrieved_ids: list[str],
    chunk_uri_by_id: dict[str, str],
    *,
    chunk_texts: dict[str, str] | None = None,
) -> tuple[dict[tuple[str, str], set[str]], dict[str, set[str]]]:
    """Map retrieved chunks to entity labels and document chunk groups.

    Sources (reinforced, never replaced by external BO alone):

    1. ``DocumentChunk --hasMention-->`` (NER ``primary_entities`` + kg args)
    2. ``DocumentChunk --hasStatement-->`` subjects and their objects (kg SVO)
    3. Parent ``Document --hasMention-->`` when the label appears in chunk text
       (document-level ``content_ner`` reinforcement)

    Example:
        >>> from thot.tools.search.ontology_utils import _collect_entity_chunks_for_retrieved
        >>> from rdflib import Graph
        >>> ents, docs = _collect_entity_chunks_for_retrieved(Graph(), [], {})
        >>> ents == {} and docs == {}
        True
    """
    chunk_texts = chunk_texts or {}
    entity_chunks: dict[tuple[str, str], set[str]] = defaultdict(set)
    chunks_by_doc: dict[str, set[str]] = defaultdict(set)

    def _add_entity(entity: URIRef, chunk_id: str) -> None:
        entity_type = _node_type(graph, entity)
        if entity_type in _STRUCTURAL_ENTITY_TYPES:
            return
        label = _node_label(graph, entity).strip()
        if not label:
            return
        entity_chunks[(label, entity_type)].add(chunk_id)

    for chunk_id in retrieved_ids:
        chunk_uri = URIRef(chunk_uri_by_id[chunk_id])
        doc_uri = _document_uri_for_chunk(graph, chunk_uri)
        if doc_uri is not None:
            chunks_by_doc[str(doc_uri)].add(chunk_id)

        for _subject, _predicate, entity in graph.triples(
            (chunk_uri, TKEIR.hasMention, None)
        ):
            if isinstance(entity, URIRef):
                _add_entity(entity, chunk_id)

        # kg SVO: reified Statement nodes and legacy hasStatement → subject.
        for _subject, _predicate, stmt_or_entity in graph.triples(
            (chunk_uri, TKEIR.hasStatement, None)
        ):
            if not isinstance(stmt_or_entity, URIRef):
                continue
            stmt_type = _node_type(graph, stmt_or_entity)
            if stmt_type == "Statement":
                for role_pred in (TKEIR.subject, TKEIR.object):
                    for _s, _p, node in graph.triples(
                        (stmt_or_entity, role_pred, None)
                    ):
                        if isinstance(node, URIRef):
                            _add_entity(node, chunk_id)
                continue
            _add_entity(stmt_or_entity, chunk_id)
            for _s, predicate, obj in graph.triples(
                (stmt_or_entity, None, None)
            ):
                if predicate in _STRUCTURAL_PREDICATES:
                    continue
                if str(predicate).endswith("importanceScore"):
                    continue
                if isinstance(obj, URIRef):
                    _add_entity(obj, chunk_id)

        # Hypergraph incidence: concept --mentionedIn--> chunk.
        for concept, _predicate, _chunk in graph.triples(
            (None, TKEIR.mentionedIn, chunk_uri)
        ):
            if isinstance(concept, URIRef):
                _add_entity(concept, chunk_id)

    # Document-level content_ner mentions → retrieved chunks with text evidence.
    for doc_uri, chunk_ids in list(chunks_by_doc.items()):
        doc_ref = URIRef(doc_uri)
        for _subject, _predicate, entity in graph.triples(
            (doc_ref, TKEIR.hasMention, None)
        ):
            if not isinstance(entity, URIRef):
                continue
            entity_type = _node_type(graph, entity)
            if entity_type in _STRUCTURAL_ENTITY_TYPES:
                continue
            label = _node_label(graph, entity).strip()
            if not label:
                continue
            for chunk_id in chunk_ids:
                text = chunk_texts.get(chunk_id, "")
                if text and not _keyword_in_chunk_text(label, text):
                    continue
                # No chunk text available → still attach (basket / analyzed fuse).
                entity_chunks[(label, entity_type)].add(chunk_id)

    return entity_chunks, chunks_by_doc


def _collect_keyword_chunks_for_docs(
    graph: Graph,
    chunks_by_doc: dict[str, set[str]],
    chunk_texts: dict[str, str],
    *,
    min_keyword_length: int,
) -> dict[str, set[str]]:
    """Map document keywords to retrieved chunk ids when text matches.

    When ``chunk_texts`` is empty (e.g. basket brief with analyzed RDF but no
    Vespa hits yet), attach keywords to all chunks of the parent document so
    the Ontology navigator is still populated.

    Example:
        >>> from thot.tools.search.ontology_utils import _collect_keyword_chunks_for_docs
        >>> from rdflib import Graph
        >>> dict(_collect_keyword_chunks_for_docs(Graph(), {}, {}, min_keyword_length=3))
        {}
    """
    keyword_chunks: dict[str, set[str]] = defaultdict(set)
    require_text_match = bool(chunk_texts)
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
                if not require_text_match or _keyword_in_chunk_text(
                    label, chunk_texts.get(chunk_id, "")
                ):
                    keyword_chunks[label].add(chunk_id)
    return keyword_chunks


def _count_label_occurrences(label: str, text: str) -> int:
    """Count case-insensitive whole-phrase occurrences of ``label`` in text.

    Example:
        >>> from thot.tools.search.ontology_utils import _count_label_occurrences
        >>> _count_label_occurrences("Paris", "Paris is Paris.")
        2
    """
    needle = (label or "").strip()
    haystack = text or ""
    if len(needle) < 2 or not haystack:
        return 0
    pattern = re.compile(
        r"(?<!\w)" + re.escape(needle) + r"(?!\w)",
        flags=re.IGNORECASE,
    )
    return len(pattern.findall(haystack))


def _surface_weight(
    label: str,
    chunk_ids: set[str] | list[str],
    chunk_texts: dict[str, str],
    *,
    coverage_coef: float = 10.0,
    text_coef: float = 2.0,
) -> tuple[float, int, int]:
    """Weight a label by chunk coverage + summed text hits across fuse.

    Returns:
        ``(weight, mention_count, text_hits)`` where ``mention_count`` is the
        number of contributing chunks and ``text_hits`` is the sum of
        occurrences in those chunk texts.

    Example:
        >>> from thot.tools.search.ontology_utils import _surface_weight
        >>> _surface_weight("Paris", ["c1"], {"c1": "Paris is nice."})[0] > 0
        True
    """
    ids = [str(cid) for cid in chunk_ids if str(cid).strip()]
    mention_count = len(ids)
    text_hits = 0
    for chunk_id in ids:
        text_hits += _count_label_occurrences(
            label, chunk_texts.get(chunk_id, "")
        )
    # Coverage alone still counts when chunk texts are unavailable.
    weight = coverage_coef * max(mention_count, 1) + text_coef * text_hits
    return float(weight), mention_count, text_hits


def _aggregate_relation_weights(
    rdf_documents: list[str],
) -> dict[tuple[str, str, str], float]:
    """Sum non-structural relation occurrences across source RDF payloads.

    Identical ``(source_label, predicate, target_label)`` edges from different
    chunk/parent ontologies add their counts (fuse sum).

    Example:
        >>> from thot.tools.search.ontology_utils import _aggregate_relation_weights
        >>> dict(_aggregate_relation_weights([]))
        {}
    """
    counts: dict[tuple[str, str, str], float] = defaultdict(float)
    for document in _unique_rdf_documents(rdf_documents):
        graph = Graph()
        try:
            graph.parse(data=document, format=detect_rdf_format(document))
        except Exception:  # noqa: BLE001
            continue
        for subject, predicate, obj in graph:
            if predicate in _STRUCTURAL_PREDICATES:
                continue
            if not isinstance(subject, URIRef):
                continue
            if _node_type(graph, subject) in _STRUCTURAL_ENTITY_TYPES:
                continue
            if isinstance(predicate, URIRef) and (
                str(predicate).endswith("importanceScore")
                or str(predicate).endswith("linkWeight")
                or str(predicate).endswith("chunkSupport")
                or str(predicate).endswith("sharedConceptCount")
                or str(predicate).endswith("intersectionWeight")
            ):
                continue
            source = _node_label(graph, subject).strip()
            pred = (
                _predicate_label(predicate)
                if isinstance(predicate, URIRef)
                else str(predicate)
            )
            if isinstance(obj, Literal):
                target = str(obj).strip()
            elif isinstance(obj, URIRef):
                if _node_type(graph, obj) in _STRUCTURAL_ENTITY_TYPES:
                    continue
                target = _node_label(graph, obj).strip()
            else:
                continue
            if not source or not target or not pred:
                continue
            if len(target) > 80:
                continue
            support = 1.0
            for _s, _p, lit in graph.triples(
                (subject, TKEIR.chunkSupport, None)
            ):
                try:
                    support = max(support, float(lit))
                except (TypeError, ValueError):
                    pass
            counts[(source, pred, target)] += support
    return counts


def _strip_technical_ontology_predicates(graph: Graph) -> None:
    """Remove ranking/scaffold literals that must not appear as ontology.

    ``importanceScore`` / ``linkWeight`` / hypergraph support counters are fuse
    ranking signals for HMI weight maps, not ontological relations — strip them
    from the RDF before JSON-LD export.

    Example:
        >>> from thot.tools.search.ontology_utils import _strip_technical_ontology_predicates, TKEIR
        >>> from rdflib import Graph, Literal, URIRef
        >>> graph = Graph()
        >>> node = URIRef("http://ex/A")
        >>> _ = graph.add((node, TKEIR.importanceScore, Literal(1.0)))
        >>> _strip_technical_ontology_predicates(graph)
        >>> len(graph)
        0
    """
    for predicate in (
        TKEIR.importanceScore,
        TKEIR.linkWeight,
        TKEIR.chunkSupport,
        TKEIR.sharedConceptCount,
        TKEIR.intersectionWeight,
    ):
        for triple in list(graph.triples((None, predicate, None))):
            graph.remove(triple)


def build_hmi_ontology(
    rdf_documents: list[str],
    retrieved_chunk_ids: list[str],
    *,
    chunk_texts: dict[str, str] | None = None,
    document_ids: list[str] | None = None,
    max_entities: int = 120,
    max_keywords: int = 60,
    min_keyword_length: int = 3,
    max_relations: int = 200,
) -> dict[str, Any]:
    """Export merged Vespa parent ontologies for HMI / RAG responses.

    Merges unique ``json_ld`` (or Turtle) payloads from retrieved parent
    documents into one RDF graph, then exports NER entities and keywords
    linked to retrieved chunk ids plus the fused JSON-LD for display and
    follow-up ontology reasoner queries.

    Node/link **weights** measure text importance summed across the fuse:
    chunk coverage + occurrence counts in retrieved chunk texts for nodes,
    and per-source relation multiplicity for links. Weights are exported only
    on entities/keywords/relations (API maps for the HMI graph). Technical
    predicates such as ``tkeir:importanceScore`` are stripped from JSON-LD.

    When retrieval returns no matching chunk ids (common for My-files basket
    briefs that fuse analyzed dumps by ``source_ref``), falls back to every
    ``DocumentChunk`` in the graph so the Ontology navigator is still filled.

    Args:
        rdf_documents: Parent document RDF payloads from Vespa (JSON-LD or Turtle).
        retrieved_chunk_ids: Chunk ids returned by hybrid search.
        chunk_texts: Optional map of ``chunk_id`` to indexed text for keyword linking.
        document_ids: Optional parent ``source_doc_id`` values that contributed
            ontology payloads (surfaced as merge metadata).
        max_entities: Maximum number of entity records to return.
        max_keywords: Maximum number of keyword records to return.
        min_keyword_length: Minimum character length for exported keyword labels.
        max_relations: Maximum weighted relations to export for the HMI graph.

    Returns:
        Dict with ``entities``, ``keywords``, ``relations``, ``json_ld``,
        ``triple_count``, ``source_count``, and ``document_ids``.

    Example:
        >>> from thot.tools.search.ontology_utils import build_hmi_ontology
        >>> build_hmi_ontology([], [])["json_ld"]
        '[]'
    """
    unique_docs = _unique_rdf_documents(rdf_documents)
    graph = merge_rdf_graphs(unique_docs)
    doc_ids = sorted(
        {
            str(doc_id).strip()
            for doc_id in document_ids or []
            if str(doc_id).strip()
        }
    )
    empty = {
        "entities": [],
        "keywords": [],
        "relations": [],
        "json_ld": "[]",
        "triple_count": 0,
        "source_count": 0,
        "document_ids": doc_ids,
    }
    if len(graph) == 0:
        return empty

    chunk_texts = chunk_texts or {}
    chunk_uri_by_id = {
        chunk_id: uri for uri, chunk_id in _chunk_uri_map(graph).items()
    }
    # Dual-hybrid passages often use source_ref as passage_id while ontology
    # chunk labels look like ``<source_ref>#chunk-N-…``. Resolve flexibly and
    # map ontology labels back to the retrieved hit ids for HMI filtering.
    ontology_to_retrieved: dict[str, str] = {}
    for retrieved_id in retrieved_chunk_ids:
        rid = str(retrieved_id or "").strip()
        if not rid:
            continue
        if rid in chunk_uri_by_id:
            ontology_to_retrieved[rid] = rid
            continue
        for label in chunk_uri_by_id:
            if (
                label.startswith(f"{rid}#")
                or label.startswith(f"{rid}/")
                or rid in label
            ):
                ontology_to_retrieved.setdefault(label, rid)
    if not ontology_to_retrieved and doc_ids:
        for label in chunk_uri_by_id:
            for doc_id in doc_ids:
                if doc_id and doc_id in label:
                    ontology_to_retrieved.setdefault(label, doc_id)
                    break
    # Basket / analyzed-only fuse: no Vespa chunk ids matched — export all
    # DocumentChunk nodes so entities/keywords still populate the navigator.
    if not ontology_to_retrieved and chunk_uri_by_id:
        for label in chunk_uri_by_id:
            ontology_to_retrieved[label] = label

    retrieved_ids = list(ontology_to_retrieved.keys())

    entity_chunks, chunks_by_doc = _collect_entity_chunks_for_retrieved(
        graph,
        retrieved_ids,
        chunk_uri_by_id,
        chunk_texts=chunk_texts,
    )
    # Remap ontology chunk labels → retrieved hit ids for the navigator.
    remapped_entities: dict[tuple[str, str], set[str]] = defaultdict(set)
    for key, chunk_ids in entity_chunks.items():
        for chunk_id in chunk_ids:
            remapped_entities[key].add(
                ontology_to_retrieved.get(chunk_id, chunk_id)
            )
    entity_chunks = remapped_entities

    remapped_by_doc: dict[str, set[str]] = defaultdict(set)
    for doc_uri, chunk_ids in chunks_by_doc.items():
        for chunk_id in chunk_ids:
            remapped_by_doc[doc_uri].add(
                ontology_to_retrieved.get(chunk_id, chunk_id)
            )
    chunks_by_doc = remapped_by_doc

    keyword_chunks = _collect_keyword_chunks_for_docs(
        graph,
        chunks_by_doc,
        chunk_texts,
        min_keyword_length=min_keyword_length,
    )

    entity_rows: list[dict[str, Any]] = []
    # Reinforce NER/kg entities over keyword flood when ranking for the graph.
    _ENTITY_WEIGHT_BOOST = 1.75
    for (label, entity_type), chunk_ids in entity_chunks.items():
        weight, mention_count, text_hits = _surface_weight(
            label, chunk_ids, chunk_texts
        )
        weight *= _ENTITY_WEIGHT_BOOST
        entity_rows.append(
            {
                "label": label,
                "type": entity_type,
                "chunk_ids": sorted(chunk_ids),
                "weight": round(weight, 3),
                "mention_count": mention_count,
                "text_hits": text_hits,
            }
        )
    entity_rows.sort(
        key=lambda row: (-float(row["weight"]), row["label"].lower())
    )
    entities = entity_rows[:max_entities]

    keyword_rows: list[dict[str, Any]] = []
    for label, chunk_ids in keyword_chunks.items():
        if not chunk_ids:
            continue
        weight, mention_count, text_hits = _surface_weight(
            label, chunk_ids, chunk_texts, coverage_coef=8.0, text_coef=2.5
        )
        keyword_rows.append(
            {
                "label": label,
                "chunk_ids": sorted(chunk_ids),
                "weight": round(weight, 3),
                "mention_count": mention_count,
                "text_hits": text_hits,
            }
        )
    keyword_rows.sort(
        key=lambda row: (-float(row["weight"]), row["label"].lower())
    )
    keywords = keyword_rows[:max_keywords]

    relation_counts = _aggregate_relation_weights(unique_docs)
    relations = [
        {
            "source": source,
            "predicate": predicate,
            "target": target,
            "weight": round(float(weight), 3),
        }
        for (source, predicate, target), weight in sorted(
            relation_counts.items(),
            key=lambda item: (
                -item[1],
                item[0][0].lower(),
                item[0][2].lower(),
            ),
        )[:max_relations]
        if weight > 0 and not _is_structural_predicate_label(predicate)
    ]

    _strip_technical_ontology_predicates(graph)

    return {
        "entities": entities,
        "keywords": keywords,
        "relations": relations,
        "json_ld": serialize_graph_json_ld(graph),
        "triple_count": len(graph),
        "source_count": len(unique_docs),
        "document_ids": doc_ids,
    }


def _surface_in_text(label: str, text: str) -> bool:
    """True when ``label`` appears in chunk text (case-insensitive phrase).

    Example:
        >>> from thot.tools.search.ontology_utils import _surface_in_text
        >>> _surface_in_text("Paris", "The capital is Paris.")
        True
    """
    needle = (label or "").strip()
    hay = text or ""
    if len(needle) < 2 or not hay:
        return False
    if needle.casefold() in hay.casefold():
        return True
    return _keyword_in_chunk_text(needle, hay)


def _surface_tokens_in_text(
    label: str, text: str, *, min_token_len: int = 4
) -> bool:
    """True when the full phrase or any contentful token appears in text.

    Used for kg object slots whose phrases are longer than a retrieved chunk
    window (e.g. ``consistent with a ship-to-ship transfer``).

    Example:
        >>> from thot.tools.search.ontology_utils import _surface_tokens_in_text
        >>> _surface_tokens_in_text("ship transfer", "observed ship activity")
        True
    """
    if _surface_in_text(label, text):
        return True
    hay = (text or "").casefold()
    if not hay:
        return False
    tokens = [
        tok
        for tok in re.findall(r"[A-Za-z0-9][A-Za-z0-9'%-]*", label or "")
        if len(tok) >= min_token_len
    ]
    return any(tok.casefold() in hay for tok in tokens)


def _ner_type_label(raw: str) -> str:
    """Ner type label.

    Example:
        >>> from thot.tools.search.ontology_utils import _ner_type_label
        >>> _ner_type_label("person")
        'Person'
    """

    text = (raw or "entity").strip() or "entity"
    return text[:1].upper() + text[1:] if text else "Entity"


def enrich_hmi_ontology_from_analyzed_documents(
    hmi: dict[str, Any],
    *,
    analyzed_documents: dict[str, dict[str, Any]],
    chunk_parent_ids: dict[str, str],
    chunk_texts: dict[str, str],
    max_entities: int = 120,
    max_keywords: int = 60,
    max_relations: int = 200,
    min_keyword_length: int = 3,
) -> dict[str, Any]:
    """Reinforce HMI ontology from TKEIR analyzed dumps (search/RAG time).

    For each retrieved chunk, loads signals from the parent
    ``analyzed_document.json`` written at index time:

    - ``content_ner`` → entities
    - ``kg`` → entities + relations (SVO)
    - ``keywords`` → keywords

    Only surfaces evidenced in the chunk text are attached (no ingest change).
    External / business ontology already present in ``hmi`` is kept; NLP
    signals are merged in and preferred when capping.

    Example:
        >>> from thot.tools.search.ontology_utils import enrich_hmi_ontology_from_analyzed_documents
        >>> enrich_hmi_ontology_from_analyzed_documents(
        ...     {"entities": [], "keywords": [], "relations": []},
        ...     analyzed_documents={},
        ...     chunk_parent_ids={},
        ...     chunk_texts={},
        ... )["entities"]
        []
    """
    from thot.tools.search.chunk_ontology import _kg_node_text

    if not analyzed_documents or not chunk_parent_ids:
        return hmi

    entity_map: dict[tuple[str, str], dict[str, Any]] = {}
    for row in hmi.get("entities") or []:
        if not isinstance(row, dict):
            continue
        label = str(row.get("label") or "").strip()
        etype = str(row.get("type") or "Entity").strip() or "Entity"
        if not label:
            continue
        key = (label.casefold(), etype.casefold())
        entity_map[key] = {
            "label": label,
            "type": etype,
            "chunk_ids": set(str(c) for c in row.get("chunk_ids") or [] if c),
            "weight": float(row.get("weight") or 0.0),
            "mention_count": int(row.get("mention_count") or 0),
            "text_hits": int(row.get("text_hits") or 0),
        }

    keyword_map: dict[str, dict[str, Any]] = {}
    for row in hmi.get("keywords") or []:
        if not isinstance(row, dict):
            continue
        label = str(row.get("label") or "").strip()
        if not label:
            continue
        key = label.casefold()
        keyword_map[key] = {
            "label": label,
            "chunk_ids": set(str(c) for c in row.get("chunk_ids") or [] if c),
            "weight": float(row.get("weight") or 0.0),
            "mention_count": int(row.get("mention_count") or 0),
            "text_hits": int(row.get("text_hits") or 0),
        }

    display_relations: dict[tuple[str, str, str], float] = {}
    for row in hmi.get("relations") or []:
        if not isinstance(row, dict):
            continue
        source = str(row.get("source") or "").strip()
        predicate = str(row.get("predicate") or "").strip()
        target = str(row.get("target") or "").strip()
        if not source or not predicate:
            continue
        display_relations[(source, predicate, target)] = max(
            display_relations.get((source, predicate, target), 0.0),
            float(row.get("weight") or 1.0),
        )

    def _add_entity(label: str, etype: str, chunk_id: str, text: str) -> None:
        lab = (label or "").strip()
        if len(lab) < 2 or not _surface_in_text(lab, text):
            return
        typ = _ner_type_label(etype)
        key = (lab.casefold(), typ.casefold())
        weight, mention_count, text_hits = _surface_weight(
            lab, {chunk_id}, {chunk_id: text}
        )
        weight *= 1.75
        existing = entity_map.get(key)
        if existing is None:
            entity_map[key] = {
                "label": lab,
                "type": typ,
                "chunk_ids": {chunk_id},
                "weight": weight,
                "mention_count": mention_count,
                "text_hits": text_hits,
            }
            return
        existing["chunk_ids"].add(chunk_id)
        existing["weight"] = max(float(existing["weight"]), weight)
        existing["mention_count"] = len(existing["chunk_ids"])
        existing["text_hits"] = int(existing["text_hits"]) + text_hits

    def _add_keyword(label: str, chunk_id: str, text: str) -> None:
        lab = (label or "").strip()
        if not is_valid_keyword_label(lab, min_length=min_keyword_length):
            return
        if not _surface_in_text(lab, text):
            return
        key = lab.casefold()
        weight, mention_count, text_hits = _surface_weight(
            lab, {chunk_id}, {chunk_id: text}, coverage_coef=8.0, text_coef=2.5
        )
        existing = keyword_map.get(key)
        if existing is None:
            keyword_map[key] = {
                "label": lab,
                "chunk_ids": {chunk_id},
                "weight": weight,
                "mention_count": mention_count,
                "text_hits": text_hits,
            }
            return
        existing["chunk_ids"].add(chunk_id)
        existing["weight"] = max(float(existing["weight"]), weight)
        existing["mention_count"] = len(existing["chunk_ids"])
        existing["text_hits"] = int(existing["text_hits"]) + text_hits

    def _add_relation(
        subject: str, predicate: str, obj: str, chunk_id: str, text: str
    ) -> None:
        subj = (subject or "").strip()
        pred = (predicate or "").strip()
        obj_t = (obj or "").strip()
        if not subj or not pred:
            return
        # Never treat structural scaffolding as a kg verb.
        if _is_structural_predicate_label(pred):
            return
        if not _surface_in_text(subj, text):
            return
        # Keep kg.property even when the object phrase is only partially in the
        # retrieved chunk (long SVO values are common in analyzed dumps).
        if obj_t and not _surface_tokens_in_text(obj_t, text):
            return
        key = (subj, pred, obj_t)
        # Prefer analyzed kg verbs over scaffolding when capping relations.
        display_relations[key] = max(display_relations.get(key, 0.0), 3.0)
        _add_entity(subj, "Entity", chunk_id, text)
        if obj_t and _surface_in_text(obj_t, text):
            _add_entity(obj_t, "Entity", chunk_id, text)
        elif obj_t:
            # Soft-matched object: still keep the relation endpoint as an entity.
            typ = "Entity"
            ek = (obj_t.casefold(), typ.casefold())
            if ek not in entity_map:
                entity_map[ek] = {
                    "label": obj_t,
                    "type": typ,
                    "chunk_ids": {chunk_id},
                    "weight": 1.5,
                    "mention_count": 1,
                    "text_hits": 0,
                }
            else:
                entity_map[ek]["chunk_ids"].add(chunk_id)
                entity_map[ek]["mention_count"] = len(
                    entity_map[ek]["chunk_ids"]
                )

    chunks_by_parent: dict[str, list[str]] = defaultdict(list)
    for chunk_id, parent_id in chunk_parent_ids.items():
        if parent_id:
            chunks_by_parent[parent_id].append(chunk_id)

    for parent_id, chunk_ids in chunks_by_parent.items():
        document = analyzed_documents.get(parent_id)
        if not isinstance(document, dict):
            # Try alternate keys (source_ref vs source_doc_id).
            document = analyzed_documents.get(parent_id.strip())
        if not isinstance(document, dict):
            continue

        for chunk_id in chunk_ids:
            text = chunk_texts.get(chunk_id, "")
            if not text.strip():
                continue

            for span in document.get("content_ner") or []:
                if not isinstance(span, dict):
                    continue
                _add_entity(
                    str(span.get("text") or ""),
                    str(span.get("label") or "entity"),
                    chunk_id,
                    text,
                )
            for span in document.get("title_ner") or []:
                if not isinstance(span, dict):
                    continue
                _add_entity(
                    str(span.get("text") or ""),
                    str(span.get("label") or "entity"),
                    chunk_id,
                    text,
                )

            for triple in document.get("kg") or []:
                if not isinstance(triple, dict):
                    continue
                if str(triple.get("field_type") or "") == "keywords":
                    continue
                subject = _kg_node_text(triple.get("subject"))
                predicate = _kg_node_text(triple.get("property"))
                obj = _kg_node_text(triple.get("value"))
                _add_relation(subject, predicate, obj, chunk_id, text)

            for keyword in document.get("keywords") or []:
                if isinstance(keyword, dict):
                    _add_keyword(
                        str(keyword.get("text") or ""), chunk_id, text
                    )
                elif keyword:
                    _add_keyword(str(keyword), chunk_id, text)

    entity_rows = [
        {
            "label": row["label"],
            "type": row["type"],
            "chunk_ids": sorted(row["chunk_ids"]),
            "weight": round(float(row["weight"]), 3),
            "mention_count": int(row["mention_count"]),
            "text_hits": int(row["text_hits"]),
        }
        for row in entity_map.values()
    ]
    entity_rows.sort(
        key=lambda row: (-float(row["weight"]), row["label"].lower())
    )

    keyword_rows = [
        {
            "label": row["label"],
            "chunk_ids": sorted(row["chunk_ids"]),
            "weight": round(float(row["weight"]), 3),
            "mention_count": int(row["mention_count"]),
            "text_hits": int(row["text_hits"]),
        }
        for row in keyword_map.values()
    ]
    keyword_rows.sort(
        key=lambda row: (-float(row["weight"]), row["label"].lower())
    )

    relations = [
        {
            "source": source,
            "predicate": predicate,
            "target": target,
            "weight": round(float(weight), 3),
        }
        for (source, predicate, target), weight in sorted(
            display_relations.items(),
            key=lambda item: (
                -item[1],
                item[0][0].lower(),
                item[0][2].lower(),
            ),
        )[:max_relations]
        if weight > 0 and not _is_structural_predicate_label(predicate)
    ]

    out = dict(hmi)
    out["entities"] = entity_rows[:max_entities]
    out["keywords"] = keyword_rows[:max_keywords]
    out["relations"] = relations
    return out


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
        chunk_ref = URIRef(chunk_uri)
        for _subject, _predicate, entity in graph.triples(
            (chunk_ref, TKEIR.hasMention, None)
        ):
            if isinstance(entity, URIRef):
                entities.add(str(entity))
        for concept, _predicate, _chunk in graph.triples(
            (None, TKEIR.mentionedIn, chunk_ref)
        ):
            if isinstance(concept, URIRef):
                entities.add(str(concept))
        for _subject, _predicate, stmt in graph.triples(
            (chunk_ref, TKEIR.hasStatement, None)
        ):
            if not isinstance(stmt, URIRef):
                continue
            if _node_type(graph, stmt) != "Statement":
                entities.add(str(stmt))
                continue
            for role in (TKEIR.subject, TKEIR.object):
                for _s, _p, node in graph.triples((stmt, role, None)):
                    if isinstance(node, URIRef):
                        entities.add(str(node))
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
