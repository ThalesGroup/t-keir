"""Title: Label Vectorizer

Tests for TF-IDF lemma vectorization used in ontology clustering.

Author: Eric Blaudez

Copyright (c) 2026 Thales
Licensed under the MIT License.
"""

import numpy as np

from thot.tasks.document_ontology.label_vectorizer import (
    label_lemma_text,
    label_lemmas,
    vectorize_labels_tfidf,
)


def _cosine_similarity(left: list[float], right: list[float]) -> float:
    matrix = np.asarray([left, right], dtype=float)
    matrix = matrix / np.linalg.norm(matrix, axis=1, keepdims=True)
    return float(matrix[0] @ matrix[1])


def test_label_lemmas_split_camel_case_and_plural():
    assert label_lemmas("writtenBy") == ["written", "by"]
    assert label_lemmas("Writers") == ["writer"]


def test_vectorize_labels_tfidf_clusters_plural_lemmas():
    vectors = vectorize_labels_tfidf(["Writer", "Writers"])
    assert len(vectors) == 2
    assert label_lemma_text("Writer") == label_lemma_text("Writers")
    assert _cosine_similarity(vectors[0], vectors[1]) >= 0.99


def test_vectorize_labels_tfidf_clusters_slug_variants():
    vectors = vectorize_labels_tfidf(["writtenBy", "written_by"])
    assert label_lemma_text("writtenBy") == label_lemma_text("written_by")
    assert _cosine_similarity(vectors[0], vectors[1]) >= 0.99
