# -*- coding: utf-8 -*-
"""Backward-compatible shim for ontology label vectorization."""

from __future__ import annotations

from thot.tasks.document_ontology.label_vectorizer import (
    LabelVectorFn,
    label_lemma_text,
    label_lemmas,
    label_tokens,
    vectorize_labels_tfidf,
)

EmbedBatchFn = LabelVectorFn


def embed_labels_sync(labels: list[str]) -> list[list[float]]:
    """Deprecated: use :func:`vectorize_labels_tfidf` instead."""
    return vectorize_labels_tfidf(labels)
