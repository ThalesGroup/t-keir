"""TF-IDF vectorization of ontology labels using token lemmas."""

from __future__ import annotations

import re
from collections.abc import Callable

import numpy as np
from scipy.sparse import hstack
from sklearn.feature_extraction.text import TfidfVectorizer

LabelVectorFn = Callable[[list[str]], list[list[float]]]

_CAMEL_BOUNDARY = re.compile(
    r"(?<!^)(?=[A-Z])|(?<=[a-z])(?=[0-9])|(?<=[0-9])(?=[A-Za-z])"
)
_TOKEN_SPLIT = re.compile(r"[^a-zA-Z0-9]+")


def _lemma_token(token: str) -> str:
    """Normalize a token to a coarse lemma for clustering.

    Example:
        >>> _lemma_token('writers')
        'writer'
    """
    normalized = token.lower().strip()
    if not normalized:
        return ""
    if len(normalized) > 3 and normalized.endswith("ies"):
        return normalized[:-3] + "y"
    if (
        len(normalized) > 3
        and normalized.endswith("s")
        and not normalized.endswith("ss")
    ):
        return normalized[:-1]
    return normalized


def label_tokens(label: str) -> list[str]:
    """Split a class or property label into raw tokens.

    Example:
        >>> label_tokens('writtenBy')
        ['written', 'By']
    """
    text = str(label).strip()
    if not text:
        return []
    spaced = _CAMEL_BOUNDARY.sub(" ", text)
    return [token for token in _TOKEN_SPLIT.split(spaced) if token]


def label_lemmas(label: str) -> list[str]:
    """Return deduplicated lemma tokens for a label.

    Example:
        >>> label_lemmas("writtenBy")
        ['written', 'by']
        >>> label_lemmas("Writers")
        ['writer']
    """
    lemmas: list[str] = []
    seen: set[str] = set()
    for token in label_tokens(label):
        lemma = _lemma_token(token)
        if lemma and lemma not in seen:
            seen.add(lemma)
            lemmas.append(lemma)
    return lemmas


def label_lemma_text(label: str) -> str:
    """Join label lemmas into a TF-IDF document string.

    Example:
        >>> label_lemma_text("createdBy")
        'created by'
    """
    return " ".join(label_lemmas(label))


def vectorize_labels_tfidf(labels: list[str]) -> list[list[float]]:
    """Vectorize labels with TF-IDF over lemma tokens.

    Args:
        labels: Class or property labels observed in the document/graph.

    Returns:
        Dense TF-IDF vectors aligned with ``labels``.

    Example:
        >>> vectors = vectorize_labels_tfidf(["Writer", "Writers"])
        >>> len(vectors) == 2
        True
    """
    if not labels:
        return []
    if len(labels) == 1:
        return [[1.0]]

    documents = [label_lemma_text(label) or label.lower() for label in labels]
    if all(not document.strip() for document in documents):
        return np.eye(len(labels), dtype=float).tolist()

    word_vectorizer = TfidfVectorizer(
        analyzer=lambda document: document.split(),
        min_df=1,
        norm="l2",
    )
    char_vectorizer = TfidfVectorizer(
        analyzer="char_wb",
        ngram_range=(2, 5),
        min_df=1,
        norm="l2",
    )
    word_matrix = word_vectorizer.fit_transform(documents)
    char_matrix = char_vectorizer.fit_transform(documents)
    matrix = hstack([word_matrix, char_matrix])
    return matrix.toarray().tolist()
