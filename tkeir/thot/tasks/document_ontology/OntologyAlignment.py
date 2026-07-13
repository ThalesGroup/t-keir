# -*- coding: utf-8 -*-
"""Cluster and align synonymous RDF classes and properties in document graphs."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from typing import Callable

import numpy as np
from rdflib import Graph, Literal, URIRef
from rdflib.namespace import RDF, RDFS
from sklearn.cluster import AgglomerativeClustering

from thot.core.ThotLogger import ThotLogger
from thot.tasks.document_ontology.label_vectorizer import (
    LabelVectorFn,
    vectorize_labels_tfidf,
)
from thot.tasks.document_ontology.OntologyBuilder import (
    OntologyBuildSettings,
    TKEIR,
)
from thot.tasks.document_ontology.triple_context_vectorizer import (
    cluster_entities_by_triple_context,
    collect_document_svo_triples,
)
from thot.tasks.document_ontology.OntologyVocabulary import (
    FALLBACK_ENTITY_CLASS,
    METRIC_CLASS,
    OntologyVocabulary,
    slug_to_predicate_name,
    slugify_verb,
    title_case_label,
)

DEFAULT_SIMILARITY_THRESHOLD = 0.85

_STRUCTURAL_CLASSES = frozenset(
    {
        "Document",
        "DocumentChunk",
        "Keyword",
        "Tag",
        "Entity",
    }
)

_STRUCTURAL_PREDICATES = frozenset(
    {
        "hasStatement",
        "hasMention",
        "hasKeyword",
        "hasTag",
        "isTagOf",
        "hasNumericValue",
        "has-concept",
    }
)


@dataclass(frozen=True)
class AlignmentSettings:
    """Configuration for ontology class/property clustering."""

    enabled: bool = True
    similarity_threshold: float = DEFAULT_SIMILARITY_THRESHOLD
    min_cluster_size: int = 2


def _local_name(uri: URIRef) -> str:
    text = str(uri)
    if "#" in text:
        return text.rsplit("#", 1)[-1]
    return text.rsplit("/", 1)[-1]


def _is_tkeir_uri(uri: URIRef) -> bool:
    return str(uri).startswith(str(TKEIR))


def extract_class_labels(graph: Graph) -> list[str]:
    """Return distinct TKEIR class local names used as ``rdf:type`` objects.

    Example:
        >>> from rdflib import Graph, Literal, URIRef
        >>> from rdflib.namespace import RDF, RDFS
        >>> from thot.tasks.document_ontology.OntologyAlignment import extract_class_labels
        >>> from thot.tasks.document_ontology.OntologyBuilder import TKEIR
        >>> graph = Graph()
        >>> node = URIRef("http://example.org/person/1")
        >>> graph.add((node, RDF.type, TKEIR.Person))
        >>> graph.add((node, RDFS.label, Literal("Alice")))
        >>> extract_class_labels(graph)
        ['Person']
    """
    labels: set[str] = set()
    for class_uri in graph.objects(None, RDF.type):
        if not isinstance(class_uri, URIRef) or not _is_tkeir_uri(class_uri):
            continue
        name = _local_name(class_uri)
        if name in _STRUCTURAL_CLASSES:
            continue
        labels.add(name)
    return sorted(labels)


def extract_predicate_labels(graph: Graph) -> list[str]:
    """Return distinct TKEIR property local names used in the graph.

    Example:
        >>> from rdflib import Graph, URIRef
        >>> from thot.tasks.document_ontology.OntologyAlignment import extract_predicate_labels
        >>> from thot.tasks.document_ontology.OntologyBuilder import TKEIR
        >>> graph = Graph()
        >>> s, o = URIRef("http://example.org/s"), URIRef("http://example.org/o")
        >>> graph.add((s, TKEIR.createdBy, o))
        >>> "createdBy" in extract_predicate_labels(graph)
        True
    """
    labels: set[str] = set()
    for _subject, predicate, _obj in graph:
        if not isinstance(predicate, URIRef) or not _is_tkeir_uri(predicate):
            continue
        name = _local_name(predicate)
        if name in _STRUCTURAL_PREDICATES:
            continue
        labels.add(name)
    return sorted(labels)


def _normalize_rows(vectors: np.ndarray) -> np.ndarray:
    norms = np.linalg.norm(vectors, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    return vectors / norms


def _cluster_labels(
    labels: list[str],
    vectors: list[list[float]],
    *,
    similarity_threshold: float,
    min_cluster_size: int,
    canonical_picker: Callable[[list[str], np.ndarray], str],
) -> dict[str, str]:
    """Cluster labels and map each member to a canonical label."""
    if not labels:
        return {}
    if len(labels) == 1:
        return {labels[0]: labels[0]}

    matrix = _normalize_rows(np.asarray(vectors, dtype=float))
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
        member_labels = [labels[index] for index in members]
        if len(members) < min_cluster_size:
            for label in member_labels:
                mapping[label] = label
            continue
        canonical = canonical_picker(member_labels, matrix[members])
        for label in member_labels:
            mapping[label] = canonical

    return mapping


def _canonical_class_label(labels: list[str], vectors: np.ndarray) -> str:
    """Pick the class label closest to the cluster centroid."""
    centroid = vectors.mean(axis=0)
    centroid_norm = np.linalg.norm(centroid)
    if centroid_norm == 0:
        return sorted(labels, key=len)[0]
    centroid = centroid / centroid_norm
    similarities = vectors @ centroid
    return labels[int(np.argmax(similarities))]


def _canonical_property_label(
    labels: list[str],
    frequencies: Counter[str],
) -> str:
    """Pick the most frequent property label, then the shortest."""
    return sorted(
        labels,
        key=lambda label: (-frequencies[label], len(label), label.lower()),
    )[0]


def _build_class_map(
    graph: Graph,
    settings: AlignmentSettings,
    vector_fn: LabelVectorFn,
) -> dict[str, str]:
    class_names = extract_class_labels(graph)
    if len(class_names) < settings.min_cluster_size:
        return {label: label for label in class_names}

    cluster_labels, alias_to_class = _class_cluster_candidates(graph)
    if len(cluster_labels) < settings.min_cluster_size:
        return {label: label for label in class_names}

    vectors = vector_fn(cluster_labels)
    alias_map = _cluster_labels(
        cluster_labels,
        vectors,
        similarity_threshold=settings.similarity_threshold,
        min_cluster_size=settings.min_cluster_size,
        canonical_picker=_canonical_class_label,
    )
    return _class_map_from_alias_clusters(class_names, alias_to_class, alias_map)


def _build_property_map(
    graph: Graph,
    settings: AlignmentSettings,
    vector_fn: LabelVectorFn,
) -> dict[str, str]:
    labels = extract_predicate_labels(graph)
    if len(labels) < settings.min_cluster_size:
        return {label: label for label in labels}

    frequencies: Counter[str] = Counter()
    for _subject, predicate, _obj in graph:
        if not isinstance(predicate, URIRef) or not _is_tkeir_uri(predicate):
            continue
        name = _local_name(predicate)
        if name in _STRUCTURAL_PREDICATES:
            continue
        frequencies[name] += 1

    vectors = vector_fn(labels)

    def _picker(member_labels: list[str], matrix: np.ndarray) -> str:
        return _canonical_property_label(member_labels, frequencies)

    return _cluster_labels(
        labels,
        vectors,
        similarity_threshold=settings.similarity_threshold,
        min_cluster_size=settings.min_cluster_size,
        canonical_picker=_picker,
    )


def _rewrite_classes(graph: Graph, class_map: dict[str, str]) -> int:
    replacements = 0
    for old_label, new_label in class_map.items():
        if old_label == new_label:
            continue
        old_uri = TKEIR[old_label]
        new_uri = TKEIR[new_label]
        for subject in list(graph.subjects(RDF.type, old_uri)):
            graph.remove((subject, RDF.type, old_uri))
            graph.add((subject, RDF.type, new_uri))
            replacements += 1
    return replacements


def _rewrite_properties(graph: Graph, property_map: dict[str, str]) -> int:
    replacements = 0
    for old_label, new_label in property_map.items():
        if old_label == new_label:
            continue
        old_uri = TKEIR[old_label]
        new_uri = TKEIR[new_label]
        for subject, _predicate, obj in list(
            graph.triples((None, old_uri, None))
        ):
            graph.remove((subject, old_uri, obj))
            graph.add((subject, new_uri, obj))
            replacements += 1
    return replacements


def _alignment_clusters(mapping: dict[str, str]) -> list[dict[str, object]]:
    grouped: dict[str, list[str]] = {}
    for label, canonical in mapping.items():
        grouped.setdefault(canonical, []).append(label)
    clusters = []
    for canonical, members in sorted(grouped.items()):
        synonyms = sorted(
            {member for member in members if member != canonical}
        )
        if len(members) > 1:
            clusters.append(
                {
                    "canonical": canonical,
                    "members": sorted(set(members)),
                    "synonyms": synonyms,
                }
            )
    return clusters


def _compose_label_maps(
    base_map: dict[str, str],
    overlay_map: dict[str, str],
) -> dict[str, str]:
    """Chain two label maps so overlay refinements apply to base mappings."""
    keys = set(base_map) | set(overlay_map)
    composed: dict[str, str] = {}
    for label in keys:
        mapped = base_map.get(label, label)
        composed[label] = overlay_map.get(mapped, mapped)
    return composed


def merge_alignment_reports(
    vocabulary_report: dict[str, object],
    graph_report: dict[str, object],
) -> dict[str, object]:
    """Merge pre-build vocabulary alignment with post-build graph alignment."""
    if not graph_report.get("enabled"):
        return {
            **vocabulary_report,
            "graph_alignment": graph_report,
        }

    vocab_class_map = dict(vocabulary_report.get("class_map") or {})
    vocab_property_map = dict(vocabulary_report.get("property_map") or {})
    graph_class_map = dict(graph_report.get("class_map") or {})
    graph_property_map = dict(graph_report.get("property_map") or {})

    merged: dict[str, object] = {
        "enabled": True,
        "vocabulary": vocabulary_report,
        "graph_alignment": graph_report,
        "class_map": _compose_label_maps(vocab_class_map, graph_class_map),
        "property_map": _compose_label_maps(
            vocab_property_map, graph_property_map
        ),
        "node_classes": vocabulary_report.get("vocabulary", {}).get(
            "node_classes"
        ),
        "class_clusters": list(vocabulary_report.get("class_clusters") or [])
        + list(graph_report.get("class_clusters") or []),
        "property_clusters": list(
            vocabulary_report.get("property_clusters") or []
        )
        + list(graph_report.get("property_clusters") or []),
    }

    if graph_report.get("status") == "SKIPPED":
        merged["status"] = "SKIPPED"
        merged["reason"] = graph_report.get("reason")
    elif vocabulary_report.get("status") == "SKIPPED":
        merged["status"] = "PARTIAL"
        merged["reason"] = vocabulary_report.get("reason")
    else:
        merged["status"] = graph_report.get(
            "status", vocabulary_report.get("status", "APPLIED")
        )

    if "similarity_threshold" in graph_report:
        merged["similarity_threshold"] = graph_report["similarity_threshold"]
    if "class_rewrites" in graph_report:
        merged["class_rewrites"] = graph_report["class_rewrites"]
    if "property_rewrites" in graph_report:
        merged["property_rewrites"] = graph_report["property_rewrites"]

    return merged


def _collect_document_ner_labels(document: dict) -> list[str]:
    labels: set[str] = set()
    for key in ("title_ner", "content_ner"):
        for span in document.get(key) or []:
            label = span.get("label")
            if label:
                labels.add(str(label).lower())
    return sorted(labels)


def _collect_dynamic_class_labels(document: dict) -> list[str]:
    """Collect class label candidates from NER, chunks, KG, and entity text."""
    candidates: set[str] = set()

    for label in _collect_document_ner_labels(document):
        candidates.add(label)
        candidates.add(title_case_label(label))

    for key in ("title_ner", "content_ner"):
        for span in document.get(key) or []:
            text = str(span.get("text", "")).strip()
            if text:
                head = text.split()[0]
                if len(head) > 2:
                    candidates.add(title_case_label(head))

    for chunk in document.get("golden_chunks") or []:
        metadata = chunk.get("metadata") or {}
        for entity_key in (metadata.get("primary_entities") or {}):
            key_text = str(entity_key).strip()
            if key_text:
                candidates.add(key_text.lower())
                candidates.add(title_case_label(key_text))

    for triple in document.get("kg") or []:
        for part in ("subject", "value"):
            content = (triple.get(part) or {}).get("content", [])
            phrase = " ".join(
                str(token).strip() for token in content if str(token).strip()
            )
            if not phrase:
                continue
            head = phrase.split()[0]
            if len(head) > 2:
                candidates.add(title_case_label(head))

    return sorted(
        candidate
        for candidate in candidates
        if candidate
        and candidate not in _STRUCTURAL_CLASSES
        and candidate not in {FALLBACK_ENTITY_CLASS, METRIC_CLASS}
    )


def _uri_class_segment(node: URIRef) -> str | None:
    """Return the URI path segment immediately before the instance id."""
    parts = str(node).rstrip("/").split("/")
    if len(parts) < 2:
        return None
    segment = parts[-2].strip()
    if not segment or segment in {"doc", "demo", "ontology"}:
        return None
    return title_case_label(segment.replace("_", " "))


def _class_cluster_candidates(
    graph: Graph,
) -> tuple[list[str], dict[str, str]]:
    """Build clustering aliases for RDF class names and URI class segments."""
    cluster_labels: list[str] = []
    alias_to_class: dict[str, str] = {}

    for class_name in extract_class_labels(graph):
        cluster_labels.append(class_name)
        alias_to_class[class_name] = class_name
        lowered = class_name.lower()
        cluster_labels.append(lowered)
        alias_to_class[lowered] = class_name

        class_uri = TKEIR[class_name]
        for node in graph.subjects(RDF.type, class_uri):
            uri_segment = _uri_class_segment(node)
            if uri_segment and uri_segment not in _STRUCTURAL_CLASSES:
                cluster_labels.append(uri_segment)
                alias_to_class[uri_segment] = class_name
                cluster_labels.append(uri_segment.lower())
                alias_to_class[uri_segment.lower()] = class_name

    deduped_labels: list[str] = []
    seen: set[str] = set()
    for label in cluster_labels:
        if label not in seen:
            seen.add(label)
            deduped_labels.append(label)
    return deduped_labels, alias_to_class


def _class_map_from_alias_clusters(
    class_names: list[str],
    alias_to_class: dict[str, str],
    alias_map: dict[str, str],
) -> dict[str, str]:
    class_map: dict[str, str] = {}
    class_name_set = set(class_names)
    for class_name in class_names:
        aliases = [
            alias for alias, mapped in alias_to_class.items() if mapped == class_name
        ]
        canonical_aliases = {alias_map.get(alias, alias) for alias in aliases}
        canonical_aliases.add(class_name)
        class_options = sorted(
            (
                candidate
                for candidate in canonical_aliases
                if candidate in class_name_set
                or candidate.lower() == class_name.lower()
            ),
            key=lambda label: (len(label), label.lower()),
        )
        if class_options:
            canonical_class = class_options[0]
        else:
            canonical_class = sorted(
                canonical_aliases,
                key=lambda label: (len(label), label.lower()),
            )[0]
        class_map[class_name] = title_case_label(canonical_class)
    return class_map


def _collect_document_verb_slugs(document: dict) -> list[str]:
    slugs: set[str] = set()
    for triple in document.get("kg") or []:
        content = (triple.get("property") or {}).get("content", [])
        verb = " ".join(str(part).strip() for part in content if str(part).strip())
        if verb:
            slugs.add(slugify_verb(verb))
    return sorted(slugs)


def _build_vocabulary_class_map(
    class_labels: list[str],
    settings: AlignmentSettings,
    vector_fn: LabelVectorFn,
) -> dict[str, str]:
    if len(class_labels) < settings.min_cluster_size:
        return {label: label for label in class_labels}

    cluster_labels: list[str] = []
    alias_to_class: dict[str, str] = {}
    for class_name in class_labels:
        cluster_labels.append(class_name)
        alias_to_class[class_name] = class_name
        lowered = class_name.lower()
        cluster_labels.append(lowered)
        alias_to_class[lowered] = class_name

    deduped_labels: list[str] = []
    seen: set[str] = set()
    for label in cluster_labels:
        if label not in seen:
            seen.add(label)
            deduped_labels.append(label)

    if len(deduped_labels) < settings.min_cluster_size:
        return {label: label for label in class_labels}

    vectors = vector_fn(deduped_labels)
    alias_map = _cluster_labels(
        deduped_labels,
        vectors,
        similarity_threshold=settings.similarity_threshold,
        min_cluster_size=settings.min_cluster_size,
        canonical_picker=_canonical_class_label,
    )
    return _class_map_from_alias_clusters(class_labels, alias_to_class, alias_map)


def _collect_ner_entity_classes(document: dict) -> dict[str, str]:
    """Map normalized entity surface forms to NER-derived class names."""
    entity_classes: dict[str, str] = {}
    for key in ("title_ner", "content_ner"):
        for span in document.get(key) or []:
            text = str(span.get("text", "")).strip().lower()
            label = span.get("label")
            if text and label:
                entity_classes[text] = title_case_label(str(label))
    return entity_classes


def _apply_canonical_class_map(
    mapping: dict[str, str],
    class_map: dict[str, str],
) -> dict[str, str]:
    return {
        key: class_map.get(class_name, class_name)
        for key, class_name in mapping.items()
    }


def _build_triple_context_maps(
    document: dict,
    settings: AlignmentSettings,
    ner_entity_classes: dict[str, str],
) -> tuple[dict[str, str], dict[str, str], dict[str, str], int]:
    """Cluster subjects, objects, and predicates from complementary SVO context."""
    triples = collect_document_svo_triples(document, OntologyBuildSettings())
    subject_map = cluster_entities_by_triple_context(
        triples,
        "subject",
        similarity_threshold=settings.similarity_threshold,
        min_cluster_size=settings.min_cluster_size,
        ner_entity_classes=ner_entity_classes,
    )
    object_map = cluster_entities_by_triple_context(
        triples,
        "object",
        similarity_threshold=settings.similarity_threshold,
        min_cluster_size=settings.min_cluster_size,
        ner_entity_classes=ner_entity_classes,
    )
    predicate_map = cluster_entities_by_triple_context(
        triples,
        "predicate",
        similarity_threshold=settings.similarity_threshold,
        min_cluster_size=settings.min_cluster_size,
    )
    for text, ner_class in ner_entity_classes.items():
        subject_map.setdefault(text, ner_class)
        object_map.setdefault(text, ner_class)
    return subject_map, object_map, predicate_map, len(triples)


def _build_heuristic_vocabulary(document: dict) -> OntologyVocabulary:
    """Label NER spans and verbs from document text without clustering."""
    ner_labels = _collect_document_ner_labels(document)
    verb_slugs = _collect_document_verb_slugs(document)
    class_candidates = _collect_dynamic_class_labels(document)

    ner_class_map = {
        label: title_case_label(label) for label in ner_labels
    }
    class_map = {class_name: class_name for class_name in class_candidates}
    for label, class_name in ner_class_map.items():
        class_map[class_name] = class_name
    property_map = {
        slug: slug_to_predicate_name(slug) for slug in verb_slugs
    }
    node_classes = frozenset(
        class_name
        for class_name in class_map.values()
        if class_name not in _STRUCTURAL_CLASSES
        and class_name not in {FALLBACK_ENTITY_CLASS, METRIC_CLASS}
    )
    ner_entity_classes = _collect_ner_entity_classes(document)
    subject_class_map = dict(ner_entity_classes)
    object_class_map = dict(ner_entity_classes)

    return OntologyVocabulary(
        ner_class_map=ner_class_map,
        node_classes=node_classes,
        predicate_aliases=property_map,
        class_map=class_map,
        subject_class_map=subject_class_map,
        object_class_map=object_class_map,
    )


def _build_vocabulary_property_map(
    verb_slugs: list[str],
    settings: AlignmentSettings,
    vector_fn: LabelVectorFn,
) -> dict[str, str]:
    labels = sorted(set(verb_slugs))
    if not labels:
        return {}
    if len(labels) < settings.min_cluster_size:
        return {
            label: slug_to_predicate_name(label) for label in labels
        }

    frequencies: Counter[str] = Counter(verb_slugs)
    vectors = vector_fn(labels)

    def _picker(member_labels: list[str], matrix: np.ndarray) -> str:
        canonical = _canonical_property_label(member_labels, frequencies)
        return slug_to_predicate_name(canonical)

    clustered = _cluster_labels(
        labels,
        vectors,
        similarity_threshold=settings.similarity_threshold,
        min_cluster_size=settings.min_cluster_size,
        canonical_picker=_picker,
    )
    return {
        slug: slug_to_predicate_name(canonical)
        for slug, canonical in clustered.items()
    }


def build_document_vocabulary(
    document: dict,
    settings: AlignmentSettings | None = None,
    *,
    embed_fn: LabelVectorFn | None = None,
    vector_fn: LabelVectorFn | None = None,
    call_context=None,
) -> tuple[OntologyVocabulary, dict[str, object]]:
    """Cluster entities and predicates from SVO triple context before graph build.

    Subject classes use TF-IDF on (predicate, object) contexts, object classes
    on (subject, predicate), and predicate aliases on (subject, object).

    Example:
        >>> from thot.tasks.document_ontology.OntologyAlignment import build_document_vocabulary
        >>> callable(build_document_vocabulary)
        True
    """
    settings = settings or AlignmentSettings()
    if not settings.enabled:
        vocabulary = _build_heuristic_vocabulary(document)
        return vocabulary, {
            "enabled": False,
            "status": "HEURISTIC",
            "vocabulary": vocabulary.to_report(),
        }

    vectorize = vector_fn or embed_fn or vectorize_labels_tfidf
    ner_labels = _collect_document_ner_labels(document)
    verb_slugs = _collect_document_verb_slugs(document)

    initial_classes = {
        label: title_case_label(label) for label in ner_labels
    }
    class_candidates = sorted(
        set(_collect_dynamic_class_labels(document))
        | set(initial_classes.values())
    )

    ner_entity_classes = _collect_ner_entity_classes(document)

    try:
        subject_class_map, object_class_map, predicate_context_map, triple_count = (
            _build_triple_context_maps(document, settings, ner_entity_classes)
        )
        class_map = _build_vocabulary_class_map(
            class_candidates,
            settings,
            vectorize,
        )
        property_label_map = _build_vocabulary_property_map(
            verb_slugs,
            settings,
            vectorize,
        )
        subject_class_map = _apply_canonical_class_map(subject_class_map, class_map)
        object_class_map = _apply_canonical_class_map(object_class_map, class_map)
        property_map = dict(property_label_map)
        property_map.update(predicate_context_map)
    except Exception as error:
        ThotLogger.warning(
            "Document vocabulary alignment skipped: clustering failed",
            trace=str(error),
            context=call_context,
        )
        vocabulary = _build_heuristic_vocabulary(document)
        return vocabulary, {
            "enabled": True,
            "status": "SKIPPED",
            "reason": str(error),
            "vocabulary": vocabulary.to_report(),
        }

    ner_class_map = {
        label: class_map.get(
            initial_classes[label],
            initial_classes[label],
        )
        for label in ner_labels
    }
    predicate_aliases = {
        slug: property_map.get(
            slug,
            slug_to_predicate_name(slug),
        )
        for slug in verb_slugs
    }
    node_classes = frozenset(
        class_name
        for class_name in (
            list(ner_class_map.values())
            + list(subject_class_map.values())
            + list(object_class_map.values())
        )
        if class_name not in _STRUCTURAL_CLASSES
        and class_name not in {FALLBACK_ENTITY_CLASS, METRIC_CLASS}
    )

    vocabulary = OntologyVocabulary(
        ner_class_map=ner_class_map,
        node_classes=node_classes,
        predicate_aliases=predicate_aliases,
        class_map=class_map,
        subject_class_map=subject_class_map,
        object_class_map=object_class_map,
    )

    report: dict[str, object] = {
        "enabled": True,
        "status": "APPLIED",
        "phase": "vocabulary",
        "similarity_threshold": settings.similarity_threshold,
        "class_map": class_map,
        "property_map": property_map,
        "subject_class_map": subject_class_map,
        "object_class_map": object_class_map,
        "context_clustering": {
            "triple_count": triple_count,
            "subject_entities": len(subject_class_map),
            "object_entities": len(object_class_map),
            "predicate_aliases": len(predicate_context_map),
        },
        "class_clusters": _alignment_clusters(class_map),
        "property_clusters": _alignment_clusters(property_map),
        "vocabulary": vocabulary.to_report(),
    }
    ThotLogger.info(
        "Document vocabulary alignment applied: "
        + str(len(report["class_clusters"]))
        + " class cluster(s), "
        + str(len(report["property_clusters"]))
        + " property cluster(s)",
        context=call_context,
    )
    return vocabulary, report


def align_document_graph(
    graph: Graph,
    settings: AlignmentSettings | None = None,
    *,
    embed_fn: LabelVectorFn | None = None,
    vector_fn: LabelVectorFn | None = None,
    call_context=None,
) -> tuple[Graph, dict[str, object]]:
    """Cluster synonymous classes/properties and rewrite the RDF graph.

    Args:
        graph: Document RDF graph built from SVO extraction.
        settings: Alignment configuration.
        vector_fn: Optional label vector function for tests.
        embed_fn: Deprecated alias for ``vector_fn``.
        call_context: Optional logger context.

    Returns:
        Tuple of ``(aligned_graph, alignment_report)``.

    Example:
        >>> from rdflib import Graph
        >>> from thot.tasks.document_ontology.OntologyAlignment import align_document_graph
        >>> callable(align_document_graph)
        True
    """
    settings = settings or AlignmentSettings()
    if not settings.enabled:
        return graph, {"enabled": False}

    vectorize = vector_fn or embed_fn or vectorize_labels_tfidf
    try:
        class_map = _build_class_map(graph, settings, vectorize)
        property_map = _build_property_map(graph, settings, vectorize)
    except Exception as error:
        ThotLogger.warning(
            "Ontology alignment skipped: clustering failed",
            trace=str(error),
            context=call_context,
        )
        return graph, {
            "enabled": True,
            "status": "SKIPPED",
            "reason": str(error),
        }

    class_rewrites = _rewrite_classes(graph, class_map)
    property_rewrites = _rewrite_properties(graph, property_map)

    report: dict[str, object] = {
        "enabled": True,
        "status": "APPLIED",
        "phase": "graph",
        "similarity_threshold": settings.similarity_threshold,
        "class_map": class_map,
        "property_map": property_map,
        "class_clusters": _alignment_clusters(class_map),
        "property_clusters": _alignment_clusters(property_map),
        "class_rewrites": class_rewrites,
        "property_rewrites": property_rewrites,
    }
    ThotLogger.info(
        "Ontology alignment applied: "
        + str(len(report["class_clusters"]))
        + " class cluster(s), "
        + str(len(report["property_clusters"]))
        + " property cluster(s)",
        context=call_context,
    )
    return graph, report
