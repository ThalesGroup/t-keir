"""Title: Ontology Alignment

Cluster and align synonymous RDF classes and properties in document graphs.

Author: Eric Blaudez

Copyright (c) 2026 Thales
Licensed under the MIT License.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass
from typing import cast

import numpy as np
from rdflib import Graph, URIRef
from rdflib.namespace import RDF
from rdflib.term import Node
from sklearn.cluster import AgglomerativeClustering

from thot.core.ThotLogger import ThotLogger
from thot.tasks.document_ontology.label_vectorizer import (
    LabelVectorFn,
    vectorize_labels_tfidf,
)
from thot.tasks.document_ontology.OntologyBuilder import (
    TKEIR,
    OntologyBuildSettings,
)
from thot.tasks.document_ontology.OntologyVocabulary import (
    FALLBACK_ENTITY_CLASS,
    METRIC_CLASS,
    OntologyVocabulary,
    slug_to_predicate_name,
    slugify_verb,
    title_case_label,
)
from thot.tasks.document_ontology.triple_context_vectorizer import (
    cluster_entities_by_triple_context,
    collect_document_svo_triples,
)

DEFAULT_SIMILARITY_THRESHOLD = 0.85

_STRUCTURAL_CLASSES = frozenset(
    {
        "Document",
        "DocumentChunk",
        "SubOntology",
        "Statement",
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
        "hasChunk",
        "mentionedIn",
        "inChunk",
        "hasSubOntology",
        "subject",
        "predicate",
        "object",
        "chunkSupport",
        "sharedConceptCount",
        "intersectionWeight",
    }
)


@dataclass(frozen=True)
class AlignmentSettings:
    """Configuration for ontology class/property clustering.
    
        Example:
            >>> from thot.tasks.document_ontology.OntologyAlignment import AlignmentSettings
            >>> callable(AlignmentSettings)
            True
    """

    enabled: bool = True
    similarity_threshold: float = DEFAULT_SIMILARITY_THRESHOLD
    min_cluster_size: int = 2


def _local_name(uri: URIRef) -> str:
    """Return the local name segment of a URI.

    Example:
        >>> from rdflib import URIRef
        >>> from thot.tasks.document_ontology.OntologyAlignment import _local_name
        >>> from thot.tasks.document_ontology.OntologyBuilder import TKEIR
        >>> _local_name(TKEIR.Person)
        'Person'
        >>> _local_name(URIRef("http://example.org/foo/Bar"))
        'Bar'
    """
    text = str(uri)
    if "#" in text:
        return text.rsplit("#", 1)[-1]
    return text.rsplit("/", 1)[-1]


def _is_tkeir_uri(uri: URIRef) -> bool:
    """Return whether ``uri`` belongs to the TKEIR ontology namespace.

    Example:
        >>> from rdflib import URIRef
        >>> from thot.tasks.document_ontology.OntologyAlignment import _is_tkeir_uri
        >>> from thot.tasks.document_ontology.OntologyBuilder import TKEIR
        >>> _is_tkeir_uri(TKEIR.Person)
        True
        >>> _is_tkeir_uri(URIRef("http://example.org/foo"))
        False
    """
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
        >>> _ = graph.add((node, RDF.type, TKEIR.Person))
        >>> _ = graph.add((node, RDFS.label, Literal("Alice")))
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
        >>> _ = graph.add((s, TKEIR.createdBy, o))
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
    """L2-normalize each row of a vector matrix.

    Example:
        >>> import numpy as np
        >>> from thot.tasks.document_ontology.OntologyAlignment import _normalize_rows
        >>> normalized = _normalize_rows(np.array([[3.0, 4.0]]))
        >>> round(float(normalized[0, 0]), 1)
        0.6
    """
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
    """Cluster labels and map each member to a canonical label.

    Example:
        >>> from thot.tasks.document_ontology.OntologyAlignment import (
        ...     _canonical_class_label,
        ...     _cluster_labels,
        ... )
        >>> mapping = _cluster_labels(
        ...     ["Alpha", "Beta"],
        ...     [[1.0, 0.0], [1.0, 0.0]],
        ...     similarity_threshold=0.9,
        ...     min_cluster_size=2,
        ...     canonical_picker=_canonical_class_label,
        ... )
        >>> mapping["Alpha"] == mapping["Beta"]
        True
    """
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
    """Pick the class label closest to the cluster centroid.

    Example:
        >>> import numpy as np
        >>> from thot.tasks.document_ontology.OntologyAlignment import _canonical_class_label
        >>> vectors = np.array([[1.0, 0.0], [0.9, 0.1]])
        >>> _canonical_class_label(["Alice", "Alicia"], vectors) in ["Alice", "Alicia"]
        True
    """
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
    """Pick the most frequent property label, then the shortest.

    Example:
        >>> from collections import Counter
        >>> from thot.tasks.document_ontology.OntologyAlignment import _canonical_property_label
        >>> frequencies = Counter({"writtenBy": 3, "createdBy": 1})
        >>> _canonical_property_label(["writtenBy", "createdBy"], frequencies)
        'writtenBy'
    """
    return sorted(
        labels,
        key=lambda label: (-frequencies[label], len(label), label.lower()),
    )[0]


def _build_class_map(
    graph: Graph,
    settings: AlignmentSettings,
    vector_fn: LabelVectorFn,
) -> dict[str, str]:
    """Build a class synonym map from graph labels and URI segments.

    Example:
        >>> from thot.tasks.document_ontology.OntologyAlignment import _build_class_map
        >>> callable(_build_class_map)
        True
    """
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
    return _class_map_from_alias_clusters(
        class_names, alias_to_class, alias_map
    )


def _build_property_map(
    graph: Graph,
    settings: AlignmentSettings,
    vector_fn: LabelVectorFn,
) -> dict[str, str]:
    """Build a property synonym map from graph predicate labels.

    Example:
        >>> from thot.tasks.document_ontology.OntologyAlignment import _build_property_map
        >>> callable(_build_property_map)
        True
    """
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
    """Rewrite ``rdf:type`` edges using a class synonym map.

    Example:
        >>> from rdflib import Graph, URIRef
        >>> from rdflib.namespace import RDF
        >>> from thot.tasks.document_ontology.OntologyAlignment import _rewrite_classes
        >>> from thot.tasks.document_ontology.OntologyBuilder import TKEIR
        >>> graph = Graph()
        >>> node = URIRef("http://example.org/person/1")
        >>> _ = graph.add((node, RDF.type, TKEIR.Writers))
        >>> _rewrite_classes(graph, {"Writers": "Writer"})
        1
        >>> list(graph.objects(node, RDF.type)) == [TKEIR.Writer]
        True
    """
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
    """Rewrite graph predicates using a property synonym map.

    Example:
        >>> from rdflib import Graph, URIRef
        >>> from thot.tasks.document_ontology.OntologyAlignment import _rewrite_properties
        >>> from thot.tasks.document_ontology.OntologyBuilder import TKEIR
        >>> graph = Graph()
        >>> s, o = URIRef("http://example.org/s"), URIRef("http://example.org/o")
        >>> _ = graph.add((s, TKEIR.createdBy, o))
        >>> _rewrite_properties(graph, {"createdBy": "writtenBy"})
        1
        >>> list(graph.predicates(s, o)) == [TKEIR.writtenBy]
        True
    """
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
    """Group synonym mappings into canonical cluster reports.

    Example:
        >>> from thot.tasks.document_ontology.OntologyAlignment import _alignment_clusters
        >>> clusters = _alignment_clusters(
        ...     {"Writer": "Writer", "Writers": "Writer"}
        ... )
        >>> clusters[0]["canonical"]
        'Writer'
        >>> sorted(clusters[0]["members"])
        ['Writer', 'Writers']
    """
    grouped: dict[str, list[str]] = {}
    for label, canonical in mapping.items():
        grouped.setdefault(canonical, []).append(label)
    clusters: list[dict[str, object]] = []
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
    """Chain two label maps so overlay refinements apply to base mappings.

    Example:
        >>> from thot.tasks.document_ontology.OntologyAlignment import _compose_label_maps
        >>> _compose_label_maps({"A": "B", "C": "C"}, {"B": "D"})["A"]
        'D'
    """
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
    """Merge pre-build vocabulary alignment with post-build graph alignment.

    Example:
        >>> from thot.tasks.document_ontology.OntologyAlignment import merge_alignment_reports
        >>> vocab = {
        ...     "enabled": True,
        ...     "status": "APPLIED",
        ...     "class_map": {"Writer": "Writer"},
        ...     "property_map": {},
        ... }
        >>> graph = {
        ...     "enabled": True,
        ...     "status": "APPLIED",
        ...     "class_map": {"Writers": "Writer"},
        ...     "property_map": {},
        ...     "class_rewrites": 1,
        ... }
        >>> merged = merge_alignment_reports(vocab, graph)
        >>> merged["class_map"]["Writers"]
        'Writer'
    """
    if not graph_report.get("enabled"):
        return {
            **vocabulary_report,
            "graph_alignment": graph_report,
        }

    vocab_class_map = cast(
        dict[str, str], vocabulary_report.get("class_map") or {}
    )
    vocab_property_map = cast(
        dict[str, str], vocabulary_report.get("property_map") or {}
    )
    graph_class_map = cast(dict[str, str], graph_report.get("class_map") or {})
    graph_property_map = cast(
        dict[str, str], graph_report.get("property_map") or {}
    )

    merged: dict[str, object] = {
        "enabled": True,
        "vocabulary": vocabulary_report,
        "graph_alignment": graph_report,
        "class_map": _compose_label_maps(vocab_class_map, graph_class_map),
        "property_map": _compose_label_maps(
            vocab_property_map, graph_property_map
        ),
        "node_classes": _nested_report_value(
            vocabulary_report, "vocabulary", "node_classes"
        ),
        "class_clusters": (
            list(
                cast(
                    list[object], vocabulary_report.get("class_clusters") or []
                )
            )
            + list(
                cast(list[object], graph_report.get("class_clusters") or [])
            )
        ),
        "property_clusters": (
            list(
                cast(
                    list[object],
                    vocabulary_report.get("property_clusters") or [],
                )
            )
            + list(
                cast(list[object], graph_report.get("property_clusters") or [])
            )
        ),
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
    """Collect normalized NER labels from title and content spans.

    Example:
        >>> from thot.tasks.document_ontology.OntologyAlignment import _collect_document_ner_labels
        >>> _collect_document_ner_labels(
        ...     {"content_ner": [{"label": "Person", "text": "Alice"}]}
        ... )
        ['person']
    """
    labels: set[str] = set()
    for key in ("title_ner", "content_ner"):
        for span in document.get(key) or []:
            label = span.get("label")
            if label:
                labels.add(str(label).lower())
    return sorted(labels)


def _add_ner_label_candidates(candidates: set[str], document: dict) -> None:
    """_add_ner_label_candidates helper.
    
        Example:
            >>> from thot.tasks.document_ontology.OntologyAlignment import _add_ner_label_candidates
            >>> callable(_add_ner_label_candidates)
            True
    """
    for label in _collect_document_ner_labels(document):
        candidates.add(label)
        candidates.add(title_case_label(label))


def _add_ner_head_candidates(candidates: set[str], document: dict) -> None:
    """_add_ner_head_candidates helper.
    
        Example:
            >>> from thot.tasks.document_ontology.OntologyAlignment import _add_ner_head_candidates
            >>> callable(_add_ner_head_candidates)
            True
    """
    for key in ("title_ner", "content_ner"):
        for span in document.get(key) or []:
            text = str(span.get("text", "")).strip()
            if not text:
                continue
            head = text.split()[0]
            if len(head) > 2:
                candidates.add(title_case_label(head))


def _add_chunk_entity_candidates(candidates: set[str], document: dict) -> None:
    """_add_chunk_entity_candidates helper.
    
        Example:
            >>> from thot.tasks.document_ontology.OntologyAlignment import _add_chunk_entity_candidates
            >>> callable(_add_chunk_entity_candidates)
            True
    """
    for chunk in document.get("golden_chunks") or []:
        metadata = chunk.get("metadata") or {}
        for entity_key in metadata.get("primary_entities") or {}:
            key_text = str(entity_key).strip()
            if not key_text:
                continue
            candidates.add(key_text.lower())
            candidates.add(title_case_label(key_text))


def _add_kg_head_candidates(candidates: set[str], document: dict) -> None:
    """_add_kg_head_candidates helper.
    
        Example:
            >>> from thot.tasks.document_ontology.OntologyAlignment import _add_kg_head_candidates
            >>> callable(_add_kg_head_candidates)
            True
    """
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


def _filter_class_candidates(candidates: set[str]) -> list[str]:
    """_filter_class_candidates helper.
    
        Example:
            >>> from thot.tasks.document_ontology.OntologyAlignment import _filter_class_candidates
            >>> _filter_class_candidates({"Person", "Entity"})
            ['Person']
    """
    return sorted(
        candidate
        for candidate in candidates
        if candidate
        and candidate not in _STRUCTURAL_CLASSES
        and candidate not in {FALLBACK_ENTITY_CLASS, METRIC_CLASS}
    )


def _collect_dynamic_class_labels(document: dict) -> list[str]:
    """Collect class label candidates from NER, chunks, KG, and entity text.

    Example:
        >>> from thot.tasks.document_ontology.OntologyAlignment import _collect_dynamic_class_labels
        >>> labels = _collect_dynamic_class_labels(
        ...     {"content_ner": [{"label": "organization", "text": "Acme Corp"}]}
        ... )
        >>> "Organization" in labels
        True
    """
    candidates: set[str] = set()
    _add_ner_label_candidates(candidates, document)
    _add_ner_head_candidates(candidates, document)
    _add_chunk_entity_candidates(candidates, document)
    _add_kg_head_candidates(candidates, document)
    return _filter_class_candidates(candidates)


def _nested_report_value(
    report: dict[str, object],
    section_key: str,
    value_key: str,
) -> object:
    """Read a nested value from an alignment report section.

    Example:
        >>> from thot.tasks.document_ontology.OntologyAlignment import _nested_report_value
        >>> _nested_report_value(
        ...     {"vocabulary": {"node_classes": ["Person"]}},
        ...     "vocabulary",
        ...     "node_classes",
        ... )
        ['Person']
    """
    section = report.get(section_key)
    if isinstance(section, dict):
        return section.get(value_key)
    return None


def _uri_class_segment(node: Node) -> str | None:
    """Return the URI path segment immediately before the instance id.

    Example:
        >>> from rdflib import URIRef
        >>> from thot.tasks.document_ontology.OntologyAlignment import _uri_class_segment
        >>> _uri_class_segment(URIRef("http://tkeir.local/doc/demo/Writer/alice-1"))
        'Writer'
    """
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
    """Build clustering aliases for RDF class names and URI class segments.

    Example:
        >>> from rdflib import Graph, URIRef
        >>> from rdflib.namespace import RDF
        >>> from thot.tasks.document_ontology.OntologyAlignment import _class_cluster_candidates
        >>> from thot.tasks.document_ontology.OntologyBuilder import TKEIR
        >>> graph = Graph()
        >>> node = URIRef("http://tkeir.local/doc/demo/Writer/alice-1")
        >>> _ = graph.add((node, RDF.type, TKEIR.Writer))
        >>> labels, aliases = _class_cluster_candidates(graph)
        >>> "writer" in labels
        True
        >>> aliases["writer"]
        'Writer'
    """
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
    """Collapse alias clusters back to canonical RDF class names.

    Example:
        >>> from thot.tasks.document_ontology.OntologyAlignment import _class_map_from_alias_clusters
        >>> class_map = _class_map_from_alias_clusters(
        ...     ["Writer", "Writers"],
        ...     {
        ...         "Writer": "Writer",
        ...         "writer": "Writer",
        ...         "Writers": "Writers",
        ...         "writers": "Writers",
        ...     },
        ...     {
        ...         "Writer": "Writer",
        ...         "writer": "Writer",
        ...         "Writers": "Writer",
        ...         "writers": "Writer",
        ...     },
        ... )
        >>> class_map["Writers"]
        'Writer'
    """
    class_map: dict[str, str] = {}
    class_name_set = set(class_names)
    for class_name in class_names:
        aliases = [
            alias
            for alias, mapped in alias_to_class.items()
            if mapped == class_name
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
    """Collect slugified verb phrases from document KG triples.

    Example:
        >>> from thot.tasks.document_ontology.OntologyAlignment import _collect_document_verb_slugs
        >>> _collect_document_verb_slugs(
        ...     {"kg": [{"property": {"content": ["written by"]}}]}
        ... )
        ['written_by']
    """
    slugs: set[str] = set()
    for triple in document.get("kg") or []:
        content = (triple.get("property") or {}).get("content", [])
        verb = " ".join(
            str(part).strip() for part in content if str(part).strip()
        )
        if verb:
            slugs.add(slugify_verb(verb))
    return sorted(slugs)


def _build_vocabulary_class_map(
    class_labels: list[str],
    settings: AlignmentSettings,
    vector_fn: LabelVectorFn,
) -> dict[str, str]:
    """Build a class synonym map from vocabulary label candidates.

    Example:
        >>> from thot.tasks.document_ontology.OntologyAlignment import (
        ...     AlignmentSettings,
        ...     _build_vocabulary_class_map,
        ... )
        >>> from thot.tasks.document_ontology.label_vectorizer import vectorize_labels_tfidf
        >>> _build_vocabulary_class_map(
        ...     ["Person"],
        ...     AlignmentSettings(min_cluster_size=2),
        ...     vectorize_labels_tfidf,
        ... )
        {'Person': 'Person'}
    """
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
    return _class_map_from_alias_clusters(
        class_labels, alias_to_class, alias_map
    )


def _collect_ner_entity_classes(document: dict) -> dict[str, str]:
    """Map normalized entity surface forms to NER-derived class names.

    Example:
        >>> from thot.tasks.document_ontology.OntologyAlignment import _collect_ner_entity_classes
        >>> _collect_ner_entity_classes(
        ...     {"content_ner": [{"label": "person", "text": "Alice"}]}
        ... )
        {'alice': 'Person'}
    """
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
    """Apply a canonical class map to entity-to-class mappings.

    Example:
        >>> from thot.tasks.document_ontology.OntologyAlignment import _apply_canonical_class_map
        >>> _apply_canonical_class_map(
        ...     {"alice": "Writers"},
        ...     {"Writers": "Writer"},
        ... )
        {'alice': 'Writer'}
    """
    return {
        key: class_map.get(class_name, class_name)
        for key, class_name in mapping.items()
    }


def _build_triple_context_maps(
    document: dict,
    settings: AlignmentSettings,
    ner_entity_classes: dict[str, str],
) -> tuple[dict[str, str], dict[str, str], dict[str, str], int]:
    """Cluster subjects, objects, and predicates from complementary SVO context.

    Example:
        >>> from thot.tasks.document_ontology.OntologyAlignment import (
        ...     AlignmentSettings,
        ...     _build_triple_context_maps,
        ... )
        >>> callable(
        ...     _build_triple_context_maps(
        ...         {"kg": []},
        ...         AlignmentSettings(),
        ...         {},
        ...     )
        ... )
        False
    """
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
    """Label NER spans and verbs from document text without clustering.

    Example:
        >>> from thot.tasks.document_ontology.OntologyAlignment import _build_heuristic_vocabulary
        >>> vocabulary = _build_heuristic_vocabulary(
        ...     {"content_ner": [{"label": "person", "text": "Alice"}]}
        ... )
        >>> vocabulary.class_for_ner_label("person")
        'Person'
    """
    ner_labels = _collect_document_ner_labels(document)
    verb_slugs = _collect_document_verb_slugs(document)
    class_candidates = _collect_dynamic_class_labels(document)

    ner_class_map = {label: title_case_label(label) for label in ner_labels}
    class_map = {class_name: class_name for class_name in class_candidates}
    for label, class_name in ner_class_map.items():
        class_map[class_name] = class_name
    property_map = {slug: slug_to_predicate_name(slug) for slug in verb_slugs}
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
    """Build a property synonym map from verb slug candidates.

    Example:
        >>> from thot.tasks.document_ontology.OntologyAlignment import (
        ...     AlignmentSettings,
        ...     _build_vocabulary_property_map,
        ... )
        >>> from thot.tasks.document_ontology.label_vectorizer import vectorize_labels_tfidf
        >>> _build_vocabulary_property_map(
        ...     ["launched"],
        ...     AlignmentSettings(min_cluster_size=2),
        ...     vectorize_labels_tfidf,
        ... )
        {'launched': 'launched'}
    """
    labels = sorted(set(verb_slugs))
    if not labels:
        return {}
    if len(labels) < settings.min_cluster_size:
        return {label: slug_to_predicate_name(label) for label in labels}

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

    initial_classes = {label: title_case_label(label) for label in ner_labels}
    class_candidates = sorted(
        set(_collect_dynamic_class_labels(document))
        | set(initial_classes.values())
    )

    ner_entity_classes = _collect_ner_entity_classes(document)

    try:
        (
            subject_class_map,
            object_class_map,
            predicate_context_map,
            triple_count,
        ) = _build_triple_context_maps(document, settings, ner_entity_classes)
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
        subject_class_map = _apply_canonical_class_map(
            subject_class_map, class_map
        )
        object_class_map = _apply_canonical_class_map(
            object_class_map, class_map
        )
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

    class_clusters = _alignment_clusters(class_map)
    property_clusters = _alignment_clusters(property_map)

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
        "class_clusters": class_clusters,
        "property_clusters": property_clusters,
        "vocabulary": vocabulary.to_report(),
    }
    ThotLogger.info(
        "Document vocabulary alignment applied: "
        + str(len(class_clusters))
        + " class cluster(s), "
        + str(len(property_clusters))
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

    class_clusters = _alignment_clusters(class_map)
    property_clusters = _alignment_clusters(property_map)

    report: dict[str, object] = {
        "enabled": True,
        "status": "APPLIED",
        "phase": "graph",
        "similarity_threshold": settings.similarity_threshold,
        "class_map": class_map,
        "property_map": property_map,
        "class_clusters": class_clusters,
        "property_clusters": property_clusters,
        "class_rewrites": class_rewrites,
        "property_rewrites": property_rewrites,
    }
    ThotLogger.info(
        "Ontology alignment applied: "
        + str(len(class_clusters))
        + " class cluster(s), "
        + str(len(property_clusters))
        + " property cluster(s)",
        context=call_context,
    )
    return graph, report
