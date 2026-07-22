"""Title: Embedding service

Backward-compatible shim for ontology label vectorization.

Author: Eric Blaudez

Copyright (c) 2026 Thales
Licensed under the MIT License.
"""

from __future__ import annotations

from thot.tasks.document_ontology.label_vectorizer import (
    LabelVectorFn,
    vectorize_labels_tfidf,
)

EmbedBatchFn = LabelVectorFn


def embed_labels_sync(labels: list[str]) -> list[list[float]]:
    """Deprecated: use :func:`vectorize_labels_tfidf` instead.

    Example:
        >>> len(embed_labels_sync(['Writer']))
        1
    """
    return vectorize_labels_tfidf(labels)
