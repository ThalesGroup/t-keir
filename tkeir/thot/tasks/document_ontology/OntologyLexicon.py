"""Title: Ontology lexicon

Extract labels from external reference ontologies and match them in
document tokens so NER / syntax can reinforce coherence before
document-ontology derivation.

Author: Eric Blaudez

Copyright (c) 2026 Thales
Licensed under the MIT License.
"""

from __future__ import annotations

import hashlib
from functools import lru_cache
from typing import Any

from thot.core.ThotLogger import ThotLogger
from thot.tasks.document_ontology.OntologyDerivation import (
    extract_reference_concepts,
    load_reference_graph,
)

# Cap phrase length so greedy token matching stays cheap.
_MAX_LABEL_TOKENS = 8
_MIN_LABEL_CHARS = 3


def normalize_ontology_path_list(raw: Any) -> list[str]:
    """Normalize a single value or list of ontology paths.

    Args:
        raw: ``None``, a path string, or a sequence of path strings.

    Returns:
        Deduplicated ordered non-empty path strings.

    Example:
        >>> normalize_ontology_path_list(["a.ttl", "a.ttl", " b.owl "])
        ['a.ttl', 'b.owl']
    """
    if raw is None:
        return []
    values: list[Any]
    if isinstance(raw, str):
        values = [raw]
    elif isinstance(raw, (list, tuple)):
        values = list(raw)
    else:
        return []
    ordered: list[str] = []
    seen: set[str] = set()
    for item in values:
        path = str(item).strip()
        if not path or path in seen:
            continue
        seen.add(path)
        ordered.append(path)
    return ordered


def ontology_paths_from_document(tkeir_doc: dict[str, Any]) -> list[str]:
    """Collect per-document external ontology paths from all known keys.

    Document keys: ``ontologies``, ``derive_from_ontologies``,
    ``ontology_sources``, and the same keys under ``metadata``.

    Args:
        tkeir_doc: T-KEIR / ingest document dict.

    Returns:
        Deduplicated ordered ontology paths.

    Example:
        >>> ontology_paths_from_document(
        ...     {"ontologies": ["a.ttl"], "metadata": {"ontologies": ["b.owl"]}}
        ... )
        ['a.ttl', 'b.owl']
    """
    paths: list[str] = []
    for key in ("ontologies", "derive_from_ontologies", "ontology_sources"):
        paths.extend(normalize_ontology_path_list(tkeir_doc.get(key)))
    metadata = tkeir_doc.get("metadata")
    if isinstance(metadata, dict):
        for key in (
            "ontologies",
            "derive_from_ontologies",
            "ontology_sources",
        ):
            paths.extend(normalize_ontology_path_list(metadata.get(key)))
    return normalize_ontology_path_list(paths)


def stamp_document_ontologies(
    target: dict[str, Any],
    paths: list[str] | None,
) -> dict[str, Any]:
    """Write canonical ``ontologies`` / ``derive_from_ontologies`` on a document.

    Args:
        target: Document or extras dict to update in place.
        paths: Ontology paths (already normalized preferred).

    Returns:
        The updated ``target``.

    Example:
        >>> stamp_document_ontologies({}, ["a.ttl"])["ontologies"]
        ['a.ttl']
    """
    ordered = normalize_ontology_path_list(paths)
    if not ordered:
        return target
    target["ontologies"] = list(ordered)
    target["derive_from_ontologies"] = list(ordered)
    metadata = target.get("metadata")
    if not isinstance(metadata, dict):
        metadata = {}
        target["metadata"] = metadata
    metadata["ontologies"] = list(ordered)
    metadata["derive_from_ontologies"] = list(ordered)
    return target


def _token_texts(tokens: list[Any]) -> list[str]:
    texts: list[str] = []
    for tok in tokens:
        if isinstance(tok, dict):
            texts.append(str(tok.get("text") or tok.get("token") or ""))
        else:
            texts.append(str(tok))
    return texts


def _normalize_phrase(text: str) -> tuple[str, ...]:
    parts = [p for p in text.strip().lower().split() if p]
    return tuple(parts)


@lru_cache(maxsize=32)
def _cached_label_phrases(
    paths_key: tuple[str, ...],
) -> tuple[tuple[str, ...], ...]:
    """Load reference ontologies and return normalized multi-token phrases."""
    if not paths_key:
        return ()
    try:
        graph = load_reference_graph(list(paths_key))
    except FileNotFoundError:
        return ()
    concepts = extract_reference_concepts(
        graph, min_label_length=_MIN_LABEL_CHARS
    )
    phrases: set[tuple[str, ...]] = set()
    for concept in concepts:
        phrase = _normalize_phrase(concept.label)
        if (
            not phrase
            or len(phrase) > _MAX_LABEL_TOKENS
            or sum(len(p) for p in phrase) < _MIN_LABEL_CHARS
        ):
            continue
        phrases.add(phrase)
    return tuple(sorted(phrases, key=lambda p: (-len(p), p)))


def ontology_label_phrases(
    paths: list[str] | tuple[str, ...],
    *,
    call_context=None,
) -> tuple[tuple[str, ...], ...]:
    """Return cached normalized label phrases for ontology paths.

    Args:
        paths: Ontology file paths.
        call_context: Optional logger context.

    Returns:
        Phrases sorted longest-first for greedy matching.

    Example:
        >>> ontology_label_phrases([])
        ()
    """
    ordered = tuple(normalize_ontology_path_list(list(paths)))
    if not ordered:
        return ()
    try:
        phrases = _cached_label_phrases(ordered)
    except Exception as exc:  # pragma: no cover - defensive
        ThotLogger.warning(
            f"Ontology lexicon load failed: {exc}",
            context=call_context,
        )
        return ()
    if phrases:
        ThotLogger.info(
            f"Ontology lexicon: {len(phrases)} phrases "
            f"from {len(ordered)} file(s)",
            context=call_context,
        )
    return phrases


def match_ontology_phrases_in_tokens(
    tokens: list[Any],
    phrases: tuple[tuple[str, ...], ...] | list[tuple[str, ...]],
    *,
    label: str = "concept",
) -> list[dict[str, Any]]:
    """Greedy left-to-right match of ontology phrases against token texts.

    Args:
        tokens: Token dicts (``text``) or raw strings.
        phrases: Normalized phrase token tuples (longest first preferred).
        label: NER label assigned to matches.

    Returns:
        Non-overlapping NER-style spans ``{start,end,label,text}``.

    Example:
        >>> match_ontology_phrases_in_tokens(
        ...     [{"text": "Ground"}, {"text": "Unit"}, {"text": "ready"}],
        ...     [("ground", "unit")],
        ... )
        [{'start': 0, 'end': 2, 'label': 'concept', 'text': 'Ground Unit'}]
    """
    texts = _token_texts(tokens)
    lower = [t.lower() for t in texts]
    n = len(lower)
    if n == 0 or not phrases:
        return []
    ordered = sorted(phrases, key=lambda p: (-len(p), p))
    occupied = [False] * n
    spans: list[dict[str, Any]] = []
    for i in range(n):
        if occupied[i]:
            continue
        for phrase in ordered:
            length = len(phrase)
            if i + length > n:
                continue
            if any(occupied[i : i + length]):
                continue
            if tuple(lower[i : i + length]) != phrase:
                continue
            spans.append(
                {
                    "start": i,
                    "end": i + length,
                    "label": label,
                    "text": " ".join(texts[i : i + length]),
                }
            )
            for j in range(i, i + length):
                occupied[j] = True
            break
    return spans


def ontology_ner_spans_for_document(
    tkeir_doc: dict[str, Any],
    *,
    call_context=None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Build ontology-driven NER spans for title and content tokens.

    Args:
        tkeir_doc: Document with optional ``ontologies`` and token fields.
        call_context: Optional logger context.

    Returns:
        ``(title_spans, content_spans)``.

    Example:
        >>> ontology_ner_spans_for_document({})
        ([], [])
    """
    paths = ontology_paths_from_document(tkeir_doc)
    if not paths:
        return [], []
    phrases = ontology_label_phrases(paths, call_context=call_context)
    if not phrases:
        return [], []
    title = match_ontology_phrases_in_tokens(
        tkeir_doc.get("title_tokens") or [], phrases
    )
    content = match_ontology_phrases_in_tokens(
        tkeir_doc.get("content_tokens") or [], phrases
    )
    return title, content


def ontology_paths_fingerprint(paths: list[str] | tuple[str, ...]) -> str:
    """Stable short fingerprint for caching / logging.

    Example:
        >>> len(ontology_paths_fingerprint(["a.ttl"])) == 16
        True
    """
    blob = "\n".join(normalize_ontology_path_list(list(paths))).encode()
    return hashlib.sha256(blob).hexdigest()[:16]
