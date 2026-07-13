# -*- coding: utf-8 -*-
"""TF-IDF clustering of subjects, objects, and predicates from SVO context."""

from __future__ import annotations

from collections import Counter, defaultdict
from typing import Callable, Literal

import numpy as np
from scipy.sparse import hstack
from sklearn.cluster import AgglomerativeClustering
from sklearn.feature_extraction.text import TfidfVectorizer

from thot.tasks.document_ontology.label_vectorizer import label_lemma_text
from thot.tasks.document_ontology.OntologyBuilder import (
    OntologyBuildSettings,
    _dependency_relations,
    _iter_included_kg_triples,
    _triple_parts,
)
from thot.tasks.document_ontology.OntologyVocabulary import (
    slug_to_predicate_name,
    slugify_verb,
    title_case_label,
)

EntityRole = Literal["subject", "object", "predicate"]


def collect_document_svo_triples(
    document: dict,
    settings: OntologyBuildSettings | None = None,
) -> list[tuple[str, str, str]]:
    """Collect subject/predicate/object text tuples from KG, deps, and chunks.

    Example:
        >>> collect_document_svo_triples({'kg': []})
        []
    """
    settings = settings or OntologyBuildSettings()
    triples: list[tuple[str, str, str]] = []
    seen: set[tuple[str, str, str]] = set()

    def _add(subject: str, predicate: str, obj: str) -> None:
        subject_text = str(subject).strip()
        predicate_text = str(predicate).strip()
        object_text = str(obj).strip()
        if not subject_text or not predicate_text:
            return
        key = (
            subject_text.lower(),
            slugify_verb(predicate_text),
            object_text.lower(),
        )
        if key in seen:
            return
        seen.add(key)
        triples.append((subject_text, predicate_text, object_text))

    for triple in _iter_included_kg_triples(document, settings):
        subject_text, verb_text, object_text = _triple_parts(triple)
        _add(subject_text, verb_text, object_text)

    for key in ("content_deps", "title_deps"):
        for subject_text, verb_text, object_text in _dependency_relations(
            document.get(key) or []
        ):
            _add(subject_text, verb_text, object_text)

    for chunk in document.get("golden_chunks") or []:
        metadata = chunk.get("metadata") or {}
        for triplet in metadata.get("svo_triplets") or []:
            if len(triplet) < 3:
                continue
            _add(str(triplet[0]), str(triplet[1]), str(triplet[2]))

    return triples


def _predicate_object_context(predicate: str, obj: str) -> str:
    """Predicate object context helper.

    Example:
        >>> _predicate_object_context('works for', 'ACME')
        'work for a c m e'
    """
    parts = [label_lemma_text(predicate)]
    if obj:
        parts.append(label_lemma_text(obj))
    return " ".join(part for part in parts if part)


def _subject_predicate_context(subject: str, predicate: str) -> str:
    """Subject predicate context helper.

    Example:
        >>> _subject_predicate_context('Alice', 'works for')
        'alice work for'
    """
    return " ".join(
        part
        for part in (label_lemma_text(subject), label_lemma_text(predicate))
        if part
    )


def _subject_object_context(subject: str, obj: str) -> str:
    """Subject object context helper.

    Example:
        >>> _subject_object_context('Alice', 'ACME')
        'alice a c m e'
    """
    parts = [label_lemma_text(subject)]
    if obj:
        parts.append(label_lemma_text(obj))
    return " ".join(part for part in parts if part)


def build_context_bags(
    triples: list[tuple[str, str, str]],
    role: EntityRole,
) -> dict[str, list[str]]:
    """Build per-entity context bags for the requested SVO role.

    Example:
        >>> build_context_bags([('Alice', 'works for', 'ACME')], 'subject')
        {'alice': ['work for a c m e']}
    """
    bags: dict[str, list[str]] = defaultdict(list)

    for subject, predicate, obj in triples:
        if role == "subject":
            key = subject.strip().lower()
            if key:
                bags[key].append(_predicate_object_context(predicate, obj))
        elif role == "object":
            if not obj.strip():
                continue
            key = obj.strip().lower()
            bags[key].append(_subject_predicate_context(subject, predicate))
        else:
            key = slugify_verb(predicate)
            if key:
                bags[key].append(_subject_object_context(subject, obj))

    return dict(bags)


def _normalize_rows(vectors: np.ndarray) -> np.ndarray:
    """Normalize rows helper.

    Example:
        >>> import numpy as np
        >>> _normalize_rows(np.array([[3.0, 4.0]])).tolist()
        [[0.6, 0.8]]
    """
    norms = np.linalg.norm(vectors, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    return vectors / norms


def _vectorize_context_documents(documents: list[str]) -> list[list[float]]:
    """Vectorize context documents helper.

    Example:
        >>> _vectorize_context_documents(['alice works acme'])
        [[1.0]]
    """
    if not documents:
        return []
    if len(documents) == 1:
        return [[1.0]]

    if all(not document.strip() for document in documents):
        return np.eye(len(documents), dtype=float).tolist()

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


def _cluster_context_keys(
    keys: list[str],
    documents: list[str],
    *,
    similarity_threshold: float,
    min_cluster_size: int,
    canonical_picker: Callable[[list[str], np.ndarray], str],
) -> dict[str, str]:
    """Cluster context keys helper.

    Example:
        >>> from thot.tasks.document_ontology.triple_context_vectorizer import _cluster_context_keys
        >>> callable(_cluster_context_keys)
        True
    """
    if not keys:
        return {}
    if len(keys) == 1:
        return {keys[0]: keys[0]}

    matrix = _normalize_rows(
        np.asarray(_vectorize_context_documents(documents), dtype=float)
    )
    distance_threshold = max(0.0, 1.0 - similarity_threshold)
    clustering = AgglomerativeClustering(
        n_clusters=None,
        metric="cosine",
        linkage="average",
        distance_threshold=distance_threshold,
    )
    cluster_ids = clustering.fit_predict(matrix)

    mapping: dict[str, str] = {}
    grouped: dict[int, list[int]] = {}
    for index, cluster_id in enumerate(cluster_ids):
        grouped.setdefault(int(cluster_id), []).append(index)

    for members in grouped.values():
        member_keys = [keys[index] for index in members]
        if len(members) < min_cluster_size:
            for key in member_keys:
                mapping[key] = key
            continue
        canonical = canonical_picker(member_keys, matrix[members])
        for key in member_keys:
            mapping[key] = canonical

    return mapping


def _top_context_lemma(context_documents: list[str]) -> str:
    """Top context lemma helper.

    Example:
        >>> _top_context_lemma(['alice works', 'alice acme'])
        'alice'
    """
    counts: Counter[str] = Counter()
    for document in context_documents:
        counts.update(token for token in document.split() if token)
    if not counts:
        return ""
    return counts.most_common(1)[0][0]


def _canonical_subject_or_object_class(
    member_keys: list[str],
    matrix: np.ndarray,
    context_bags: dict[str, list[str]],
    ner_entity_classes: dict[str, str],
) -> str:
    """Canonical subject or object class helper.

    Example:
        >>> import numpy as np
        >>> _canonical_subject_or_object_class(
        ...     ['alice'], np.array([[1.0, 0.0]]), {'alice': ['alice works']}, {}
        ... )
        'Alice'
    """
    for key in sorted(member_keys, key=len):
        ner_class = ner_entity_classes.get(key)
        if ner_class:
            return title_case_label(ner_class)

    merged_context = " ".join(
        context for key in member_keys for context in context_bags.get(key, [])
    )
    top_lemma = _top_context_lemma([merged_context])
    if top_lemma:
        return title_case_label(top_lemma)

    centroid = matrix.mean(axis=0)
    centroid_norm = np.linalg.norm(centroid)
    if centroid_norm == 0:
        return title_case_label(member_keys[0])
    centroid = centroid / centroid_norm
    similarities = matrix @ centroid
    return title_case_label(member_keys[int(np.argmax(similarities))])


def _canonical_predicate_class(
    member_keys: list[str],
    matrix: np.ndarray,
    predicate_frequencies: Counter[str],
) -> str:
    """Canonical predicate class helper.

    Example:
        >>> from collections import Counter
        >>> import numpy as np
        >>> _canonical_predicate_class(['work'], np.array([[1.0]]), Counter({'work': 2}))
        'work'
    """
    canonical_slug = sorted(
        member_keys,
        key=lambda key: (-predicate_frequencies[key], len(key), key),
    )[0]
    return slug_to_predicate_name(canonical_slug)


def cluster_entities_by_triple_context(
    triples: list[tuple[str, str, str]],
    role: EntityRole,
    *,
    similarity_threshold: float,
    min_cluster_size: int,
    ner_entity_classes: dict[str, str] | None = None,
) -> dict[str, str]:
    """Cluster entities using TF-IDF vectors built from complementary SVO context.

    Example:
        >>> from thot.tasks.document_ontology.triple_context_vectorizer import cluster_entities_by_triple_context
        >>> callable(cluster_entities_by_triple_context)
        True
    """
    context_bags = build_context_bags(triples, role)
    keys = sorted(context_bags)
    if not keys:
        return {}

    documents = [" ".join(context_bags[key]) for key in keys]
    predicate_frequencies = Counter(
        slugify_verb(predicate) for _, predicate, _ in triples
    )

    if role == "predicate":
        slug_map = _cluster_context_keys(
            keys,
            documents,
            similarity_threshold=similarity_threshold,
            min_cluster_size=min_cluster_size,
            canonical_picker=lambda members, matrix: _canonical_predicate_class(
                members,
                matrix,
                predicate_frequencies,
            ),
        )
        return {
            slug: slug_to_predicate_name(canonical_slug)
            for slug, canonical_slug in slug_map.items()
        }

    ner_hints = ner_entity_classes or {}
    slug_map = _cluster_context_keys(
        keys,
        documents,
        similarity_threshold=similarity_threshold,
        min_cluster_size=min_cluster_size,
        canonical_picker=lambda members, matrix: _canonical_subject_or_object_class(
            members,
            matrix,
            context_bags,
            ner_hints,
        ),
    )
    return {
        key: title_case_label(canonical_key)
        for key, canonical_key in slug_map.items()
    }
