# -*- coding: utf-8 -*-
"""Refine RAG search queries with the T-KEIR NLP pipeline."""

from __future__ import annotations

from thot.core.ThotLogger import ThotLogger
from thot.tasks.pipeline.PipelineRunner import PipelineRunner

_POS_TO_SUPPRESS = frozenset(
    {
        "ADP",
        "ADV",
        "AUX",
        "CONJ",
        "CCONJ",
        "DET",
        "INTJ",
        "PART",
        "SCONJ",
        "SYM",
        "SPACE",
        "X",
        "PRON",
        "PUNCT",
    }
)


def meaningful_tokens_from_morphosyntax(morphosyntax: list[dict]) -> list[str]:
    """Keep surface tokens whose spaCy POS tags carry lexical meaning.

    Args:
        morphosyntax: ``content_morphosyntax`` tokens from the pipeline.

    Returns:
        Ordered list of token texts with stopword-like POS tags removed.

    Example:
        >>> from thot.tools.search.query_refiner import meaningful_tokens_from_morphosyntax
        >>> tokens = [
        ...     {"text": "Who", "pos": "PRON"},
        ...     {"text": "report", "pos": "VERB"},
        ...     {"text": "Yang", "pos": "PROPN"},
        ... ]
        >>> meaningful_tokens_from_morphosyntax(tokens)
        ['report', 'Yang']
    """
    tokens: list[str] = []
    seen: set[str] = set()
    for token in morphosyntax:
        pos = str(token.get("pos", ""))
        text = str(token.get("text", "")).strip()
        if not text or pos in _POS_TO_SUPPRESS:
            continue
        key = text.lower()
        if key in seen:
            continue
        seen.add(key)
        tokens.append(text)
    return tokens


def refine_search_query_text(
    runner: PipelineRunner,
    query_text: str,
    *,
    language: str | None = None,
) -> str:
    """Run tokenizer and morphosyntax on a query and drop stopword-like tokens.

    Requires spaCy models installed via ``make install-spacy-models``. The
    original ``query_text`` is preserved for embedding and generation; this
    helper returns a keyword-oriented variant for Vespa ``text_raw`` retrieval.

    Args:
        runner: Configured pipeline runner.
        query_text: Raw user query.
        language: Optional language hint (``en`` or ``fr``).

    Returns:
        Space-joined meaningful tokens, or ``query_text`` when refinement fails
        or yields no tokens.

    Example:
        >>> from thot.tools.search.query_refiner import refine_search_query_text
        >>> callable(refine_search_query_text)
        True
    """
    normalized = (query_text or "").strip()
    if not normalized:
        return query_text

    document: dict = {"content": [normalized]}
    if language:
        document["language-detection"] = {"language": language}

    try:
        processed = runner.run(
            document,
            skip_converter=True,
            tasks=["morphosyntax"],
        )
    except Exception as error:
        ThotLogger.warning(
            "Query refinement failed; using original query text",
            trace=str(error),
        )
        return query_text

    morphosyntax = processed.get("content_morphosyntax") or []
    tokens = meaningful_tokens_from_morphosyntax(morphosyntax)
    if not tokens:
        return query_text

    refined = " ".join(tokens)
    ThotLogger.info(
        f"RAG search query refined: {query_text!r} -> {refined!r}"
    )
    return refined
