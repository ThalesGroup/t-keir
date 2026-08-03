"""Title: Question Builder

Generate synthetic retrieval questions for golden chunks.

Author: Eric Blaudez

Copyright (c) 2026 Thales
Licensed under the MIT License.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class QuestionGenerationSettings:
    """QuestionGenerationSettings container.
    
        Example:
            >>> from thot.tasks.chunk_questions.QuestionBuilder import QuestionGenerationSettings
            >>> callable(QuestionGenerationSettings)
            True
    """
    min_questions: int = 3
    max_questions: int = 5
    enable_multilingual: bool = True


def _clean(text: str) -> str:
    """Normalize whitespace in text.

    Args:
        text: Raw text to clean.

    Returns:
        Text with collapsed whitespace and stripped ends.

    Example:
        >>> from thot.tasks.chunk_questions.QuestionBuilder import _clean
        >>> _clean('  hello   world  ')
        'hello world'
    """
    return " ".join(text.split()).strip()


def _detect_language(document: dict) -> str:
    """Detect the document language code.

    Args:
        document: T-KEIR document with optional language metadata.

    Returns:
        Two-letter language code, defaulting to ``en``.

    Example:
        >>> from thot.tasks.chunk_questions.QuestionBuilder import _detect_language
        >>> _detect_language({'language-detection': {'language': 'fr-FR'}})
        'fr'
    """
    detection = document.get("language-detection") or {}
    language = detection.get("language") or document.get("language") or "en"
    return str(language).split("-")[0].lower()


def _question_templates(
    language: str, enable_multilingual: bool
) -> dict[str, list[str]]:
    """Return question templates keyed by generation strategy.

    Args:
        language: Two-letter language code.
        enable_multilingual: Whether to use localized templates.

    Returns:
        Mapping of question type to template strings.

    Example:
        >>> from thot.tasks.chunk_questions.QuestionBuilder import _question_templates
        >>> templates = _question_templates('en', False)
        >>> 'SVO-driven' in templates
        True
    """
    if enable_multilingual and language == "fr":
        return {
            "SVO-driven": [
                "Qu'est-ce que {subject} {verb} {object}?",
                "Qui ou quoi {verb} {object} selon ce passage?",
            ],
            "Entity-driven": [
                "Quelles informations sont données sur {entity}?",
                "Que dit ce passage au sujet de {entity}?",
            ],
            "Summary-driven": [
                "Quel est le sujet principal de cette section?",
                "De quoi parle ce fragment du document?",
            ],
        }
    return {
        "SVO-driven": [
            "What did {subject} {verb} {object}?",
            "Who or what {verb} {object} in this section?",
        ],
        "Entity-driven": [
            "What information is provided about {entity}?",
            "What does this section say regarding {entity}?",
        ],
        "Summary-driven": [
            "What is the main topic of this section?",
            "What key point does this chunk convey?",
        ],
    }


def _top_entities(chunk: dict, limit: int = 3) -> list[str]:
    """Extract top primary entities from a golden chunk.

    Args:
        chunk: Golden chunk with metadata.
        limit: Maximum number of entities to return.

    Returns:
        Ordered list of entity texts.

    Example:
        >>> from thot.tasks.chunk_questions.QuestionBuilder import _top_entities
        >>> chunk = {'metadata': {'primary_entities': {'person': ['Alice', 'Bob']}}}
        >>> _top_entities(chunk, limit=2)
        ['Alice', 'Bob']
    """
    entities: list[str] = []
    primary = chunk.get("metadata", {}).get("primary_entities") or {}
    for label in sorted(primary):
        for value in primary[label][:2]:
            if value not in entities:
                entities.append(value)
            if len(entities) >= limit:
                return entities
    return entities


def _summary_snippet(text_raw: str, max_words: int = 12) -> str:
    """Build a short summary snippet from chunk text.

    Args:
        text_raw: Raw chunk text.
        max_words: Maximum words to keep.

    Returns:
        Truncated text or a fallback phrase when empty.

    Example:
        >>> from thot.tasks.chunk_questions.QuestionBuilder import _summary_snippet
        >>> _summary_snippet('one two three four five', max_words=3)
        'one two three'
    """
    words = _clean(text_raw).split()
    if not words:
        return "this section"
    return " ".join(words[:max_words])


def _dedupe_questions(questions: list[dict]) -> list[dict]:
    """Remove duplicate questions by normalized text.

    Args:
        questions: Candidate question dicts with ``question_text``.

    Returns:
        Deduplicated question list preserving order.

    Example:
        >>> from thot.tasks.chunk_questions.QuestionBuilder import _dedupe_questions
        >>> items = [
        ...     {'question_text': 'What is X?'},
        ...     {'question_text': 'what is x?'},
        ... ]
        >>> len(_dedupe_questions(items))
        1
    """
    seen: set[str] = set()
    unique: list[dict] = []
    for item in questions:
        key = item["question_text"].lower()
        if key in seen:
            continue
        seen.add(key)
        unique.append(item)
    return unique


def _select_diverse_questions(
    candidates: list[dict], settings: QuestionGenerationSettings
) -> list[dict]:
    """Select a diverse subset of questions within configured bounds.

    Args:
        candidates: Candidate question dicts.
        settings: Min/max question limits and strategy flags.

    Returns:
        Selected questions up to ``max_questions``.

    Example:
        >>> from thot.tasks.chunk_questions.QuestionBuilder import (
        ...     QuestionGenerationSettings, _select_diverse_questions,
        ... )
        >>> settings = QuestionGenerationSettings(min_questions=1, max_questions=2)
        >>> candidates = [
        ...     {'question_text': 'A', 'question_type': 'SVO-driven'},
        ...     {'question_text': 'B', 'question_type': 'Entity-driven'},
        ... ]
        >>> len(_select_diverse_questions(candidates, settings))
        2
    """
    buckets: dict[str, list[dict]] = {
        "SVO-driven": [],
        "Entity-driven": [],
        "Summary-driven": [],
    }
    for question in candidates:
        buckets.setdefault(question["question_type"], []).append(question)

    selected: list[dict] = []
    for question_type in ("SVO-driven", "Entity-driven", "Summary-driven"):
        if buckets[question_type] and len(selected) < settings.max_questions:
            selected.append(buckets[question_type][0])

    for question_type in buckets:
        for question in buckets[question_type]:
            if len(selected) >= settings.max_questions:
                break
            if question not in selected:
                selected.append(question)

    while len(selected) < settings.min_questions and candidates:
        before = len(selected)
        for question in candidates:
            if question not in selected:
                selected.append(question)
            if len(selected) >= settings.min_questions:
                break
        if len(selected) == before:
            break
    return selected[: settings.max_questions]


def _structural_projection_questions(chunk: dict) -> list[dict]:
    """Build language-agnostic embedding texts from SVO / NER / snippet.

    Uses only structural pipeline signals (no language templates).

    Args:
        chunk: Golden chunk with ``metadata`` and ``text_raw``.

    Returns:
        Candidate question dicts for embedding.

    Example:
        >>> qs = _structural_projection_questions({
        ...     'text_raw': 'Alice built a parser.',
        ...     'metadata': {
        ...         'svo_triplets': [['Alice', 'built', 'parser']],
        ...         'primary_entities': {'person': ['Alice']},
        ...     },
        ... })
        >>> any('Alice' in q['question_text'] for q in qs)
        True
    """
    questions: list[dict] = []
    metadata = chunk.get("metadata") or {}
    for triplet in (metadata.get("svo_triplets") or [])[:3]:
        if isinstance(triplet, (list, tuple)) and len(triplet) >= 2:
            parts = [_clean(part) for part in triplet[:3] if _clean(part)]
        elif isinstance(triplet, dict):
            parts = [
                _clean(triplet.get(key) or "")
                for key in ("subject", "verb", "object")
            ]
            parts = [part for part in parts if part]
        else:
            continue
        if len(parts) < 2:
            continue
        questions.append(
            {
                "question_text": " ".join(parts),
                "question_type": "SVO-driven",
            }
        )
    for entity in _top_entities(chunk):
        questions.append(
            {
                "question_text": entity,
                "question_type": "Entity-driven",
            }
        )
    snippet = _summary_snippet(chunk.get("text_raw") or "")
    if snippet:
        questions.append(
            {
                "question_text": snippet,
                "question_type": "Summary-driven",
            }
        )
    return questions


def generate_chunk_questions(
    chunk: dict,
    language: str,
    settings: QuestionGenerationSettings,
) -> list[dict]:
    """Generate synthetic questions for a single golden chunk.

    Projections are built from SVO / entity / snippet structure so the
    embedding text stays language-agnostic (no hard-coded prompt phrases).

    Args:
        chunk: Golden chunk with text and metadata.
        language: Two-letter language code (kept for API compatibility).
        settings: Question generation limits and flags.

    Returns:
        Selected synthetic questions for the chunk.

    Example:
        >>> from thot.tasks.chunk_questions.QuestionBuilder import (
        ...     QuestionGenerationSettings, generate_chunk_questions,
        ... )
        >>> chunk = {
        ...     'text_raw': 'Alice built a parser.',
        ...     'metadata': {
        ...         'svo_triplets': [['Alice', 'built', 'parser']],
        ...         'primary_entities': {'person': ['Alice']},
        ...     },
        ... }
        >>> questions = generate_chunk_questions(
        ...     chunk, 'en', QuestionGenerationSettings(min_questions=1, max_questions=3),
        ... )
        >>> len(questions) >= 1
        True
    """
    del language  # structural projections do not use language templates
    questions = _structural_projection_questions(chunk)
    questions = _dedupe_questions(questions)
    if len(questions) < settings.min_questions:
        fallback = _clean(chunk.get("text_raw") or "")
        if fallback:
            questions.append(
                {
                    "question_text": (
                        fallback[:180] + ("..." if len(fallback) > 180 else "")
                    ),
                    "question_type": "Summary-driven",
                }
            )
        questions = _dedupe_questions(questions)

    return _select_diverse_questions(questions, settings)


def enrich_golden_chunks_with_questions(
    document: dict,
    settings: QuestionGenerationSettings | None = None,
) -> list[dict]:
    """Append synthetic_questions to each golden chunk.

    Args:
        document: T-KEIR document with ``golden_chunks``.
        settings: Optional generation settings.

    Returns:
        Golden chunks enriched with ``synthetic_questions``.

    Example:
        >>> from thot.tasks.chunk_questions.QuestionBuilder import (
        ...     enrich_golden_chunks_with_questions,
        ... )
        >>> doc = {
        ...     'golden_chunks': [{
        ...         'text_raw': 'Bob wrote code.',
        ...         'metadata': {'svo_triplets': [['Bob', 'wrote', 'code']], 'primary_entities': {}},
        ...     }],
        ... }
        >>> enriched = enrich_golden_chunks_with_questions(doc)
        >>> 'synthetic_questions' in enriched[0]
        True
    """
    settings = settings or QuestionGenerationSettings()
    language = _detect_language(document)
    chunks = document.get("golden_chunks") or []
    enriched: list[dict] = []

    for chunk in chunks:
        updated = dict(chunk)
        updated["synthetic_questions"] = generate_chunk_questions(
            chunk, language, settings
        )
        enriched.append(updated)
    return enriched
