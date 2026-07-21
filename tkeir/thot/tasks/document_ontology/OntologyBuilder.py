"""Build document RDF graphs from T-KEIR SVO triples and NER spans."""

from __future__ import annotations

import hashlib
import os
import re
from collections.abc import Callable, Iterable, Iterator
from dataclasses import dataclass

from rdflib import Graph, Literal, Namespace, URIRef
from rdflib.namespace import RDF, RDFS, XSD

from thot.core.KeywordRules import is_valid_keyword_label
from thot.tasks.document_ontology.OntologyVocabulary import (
    FALLBACK_ENTITY_CLASS,
    METRIC_CLASS,
    OntologyVocabulary,
)

TKEIR = Namespace("http://tkeir.local/ontology/")
TKEIRDOC = Namespace("http://tkeir.local/doc/")

NUMERIC_RE = re.compile(r"^-?\d+(?:[.,]\d+)?%?$")


@dataclass(frozen=True)
class OntologyBuildSettings:
    include_title_triples: bool = True
    include_content_triples: bool = True
    min_keyword_length: int = 3


def _slug(value: str) -> str:
    """Slug helper.

    Example:
        >>> _slug('Hello World!')
        'hello_world'
    """
    slug = re.sub(r"[^a-zA-Z0-9]+", "_", str(value).lower()).strip("_")
    return slug or "entity"


def _entity_text(parts: Iterable[object]) -> str:
    """Entity text helper.

    Example:
        >>> _entity_text(['Alice', '', 'Smith'])
        'Alice Smith'
    """
    return " ".join(str(part).strip() for part in parts if str(part).strip())


def _class_for_label(
    label: str | None,
    vocabulary: OntologyVocabulary | None = None,
) -> str:
    """Class for label helper.

    Example:
        >>> _class_for_label('organization')
        'Organization'
    """
    vocab = vocabulary or OntologyVocabulary.empty()
    return vocab.class_for_ner_label(label)


def _build_entity_index(
    ner_spans: list[dict],
    vocabulary: OntologyVocabulary | None = None,
) -> dict[str, str]:
    """Build entity index helper.

    Example:
        >>> spans = [{'text': 'ACME', 'label': 'organization'}]
        >>> _build_entity_index(spans)['acme']
        'Organization'
    """
    index: dict[str, str] = {}
    for span in ner_spans or []:
        text = str(span.get("text", "")).strip()
        if text:
            index[text.lower()] = _class_for_label(
                span.get("label"),
                vocabulary,
            )
    return index


def _lookup_class(
    text: str,
    entity_index: dict[str, str],
    vocabulary: OntologyVocabulary | None = None,
    *,
    role: str = "subject",
) -> str:
    """Lookup class helper.

    Example:
        >>> _lookup_class('ACME', {'acme': 'Organization'})
        'Organization'
    """
    normalized = str(text).strip().lower()
    if not normalized:
        return FALLBACK_ENTITY_CLASS

    vocab = vocabulary or OntologyVocabulary.empty()
    context_class = vocab.class_for_entity(text, role=role)
    if context_class:
        return context_class

    if normalized in entity_index:
        return entity_index[normalized]

    for key, class_name in entity_index.items():
        if key in normalized or normalized in key:
            return class_name

    compact = normalized.replace(" ", "").replace(",", "")
    if NUMERIC_RE.match(compact):
        return METRIC_CLASS
    return FALLBACK_ENTITY_CLASS


def _node_uri(doc_key: str, text: str, class_name: str) -> URIRef:
    """Node uri helper.

    Example:
        >>> from thot.tasks.document_ontology.OntologyBuilder import _node_uri
        >>> callable(_node_uri)
        True
    """
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()[:12]
    return TKEIRDOC[f"{doc_key}/{class_name}/{_slug(text)}-{digest}"]


def _predicate_uri(
    verb: str,
    vocabulary: OntologyVocabulary | None = None,
) -> URIRef:
    """Predicate uri helper.

    Example:
        >>> str(_predicate_uri('launched')).endswith('launched')
        True
    """
    vocab = vocabulary or OntologyVocabulary.empty()
    return TKEIR[vocab.predicate_for_verb(verb)]


def _doc_key(document: dict) -> str:
    """Doc key helper.

    Example:
        >>> _doc_key({'source': 'file:///tmp/My Doc.pdf'})
        'my_doc_pdf'
    """
    source = str(
        document.get("source_doc_id") or document.get("source") or "document"
    )
    if source.startswith("file://"):
        source = source[len("file://") :]
    if "/" in source:
        source = os.path.basename(source)
    return _slug(source)


@dataclass(frozen=True)
class DocumentFieldSpec:
    field_type: str
    morph_key: str
    ner_key: str
    deps_key: str
    include: bool


def _field_specs(
    settings: OntologyBuildSettings,
) -> tuple[DocumentFieldSpec, ...]:
    """Field specs helper.

    Example:
        >>> from thot.tasks.document_ontology.OntologyBuilder import _field_specs
        >>> callable(_field_specs)
        True
    """
    return (
        DocumentFieldSpec(
            field_type="content",
            morph_key="content_morphosyntax",
            ner_key="content_ner",
            deps_key="content_deps",
            include=settings.include_content_triples,
        ),
        DocumentFieldSpec(
            field_type="title",
            morph_key="title_morphosyntax",
            ner_key="title_ner",
            deps_key="title_deps",
            include=settings.include_title_triples,
        ),
    )


def _positions_for_text_phrase(
    phrase: str, morphosyntax: list[dict]
) -> set[int]:
    """Positions for text phrase helper.

    Example:
        >>> from thot.tasks.document_ontology.OntologyBuilder import _positions_for_text_phrase
        >>> callable(_positions_for_text_phrase)
        True
    """
    words = [word for word in str(phrase).lower().split() if word]
    if not words or not morphosyntax:
        return set()

    token_texts = [
        str(token.get("text", "")).lower() for token in morphosyntax
    ]
    phrase_len = len(words)
    for start in range(0, len(token_texts) - phrase_len + 1):
        if token_texts[start : start + phrase_len] == words:
            return set(range(start, start + phrase_len))
    return set()


def _keyword_positions_in_morph(
    keywords: list[dict], morphosyntax: list[dict]
) -> set[int]:
    """Keyword positions in morph helper.

    Example:
        >>> from thot.tasks.document_ontology.OntologyBuilder import _keyword_positions_in_morph
        >>> callable(_keyword_positions_in_morph)
        True
    """
    covered: set[int] = set()
    token_count = len(morphosyntax)

    for keyword in keywords or []:
        span = keyword.get("span") or {}
        start = span.get("start")
        end = span.get("end")
        if start is None or end is None:
            continue

        start_idx = int(start)
        end_idx = int(end)
        if not (0 <= start_idx <= end_idx <= token_count):
            continue

        keyword_text = str(keyword.get("text", "")).strip().lower()
        if not keyword_text:
            continue

        candidate = " ".join(
            str(token.get("text", "")).strip()
            for token in morphosyntax[start_idx:end_idx]
        ).lower()
        if candidate and (
            keyword_text == candidate
            or keyword_text in candidate
            or candidate in keyword_text
        ):
            covered.update(range(start_idx, end_idx))

    return covered


def _ner_span_positions(ner_spans: list[dict]) -> set[int]:
    """Ner span positions helper.

    Example:
        >>> _ner_span_positions([{'start': 1, 'end': 3}])
        {1, 2}
    """
    covered: set[int] = set()
    for span in ner_spans or []:
        start = span.get("start")
        end = span.get("end")
        if start is None or end is None:
            continue
        covered.update(range(int(start), int(end)))
    return covered


def _golden_chunk_positions(chunks: list[dict]) -> set[int]:
    """Golden chunk positions helper.

    Example:
        >>> from thot.tasks.document_ontology.OntologyBuilder import _golden_chunk_positions
        >>> callable(_golden_chunk_positions)
        True
    """
    covered: set[int] = set()
    for chunk in chunks or []:
        metadata = chunk.get("metadata") or {}
        start = metadata.get("token_start")
        end = metadata.get("token_end")
        if start is None or end is None:
            continue
        covered.update(range(int(start), int(end)))
    return covered


def _dependency_token_positions(deps: list[dict]) -> set[int]:
    """Dependency token positions helper.

    Example:
        >>> _dependency_token_positions([{}, {}, {}])
        {0, 1, 2}
    """
    return set(range(len(deps or [])))


def _dependency_relations(deps: list[dict]) -> list[tuple[str, str, str]]:
    """Dependency relations helper.

    Example:
        >>> from thot.tasks.document_ontology.OntologyBuilder import _dependency_relations
        >>> callable(_dependency_relations)
        True
    """
    if not deps:
        return []

    relations: list[tuple[str, str, str]] = []
    seen: set[tuple[str, str, str]] = set()
    verb_positions = {
        idx
        for idx, token in enumerate(deps)
        if token.get("pos") in {"VERB", "AUX"}
    }

    for token in deps:
        head_idx = token.get("head")
        if head_idx is None or head_idx not in verb_positions:
            continue
        if token.get("dep") != "nsubj":
            continue

        subject_text = str(token.get("text", "")).strip()
        if not subject_text:
            continue

        head = deps[head_idx]
        verb_text = str(head.get("lemma") or head.get("text") or "").strip()
        if not verb_text:
            continue

        object_text = ""
        for obj_token in deps:
            if obj_token.get("head") != head_idx:
                continue
            if obj_token.get("dep") not in {
                "dobj",
                "obj",
                "attr",
                "oprd",
                "pobj",
            }:
                continue
            object_text = str(obj_token.get("text", "")).strip()
            break

        key = (subject_text.lower(), verb_text.lower(), object_text.lower())
        if key not in seen:
            seen.add(key)
            relations.append((subject_text, verb_text, object_text))

    return relations


def _iter_tag_kg_entries(document: dict) -> list[str]:
    """Iter tag kg entries helper.

    Example:
        >>> from thot.tasks.document_ontology.OntologyBuilder import _iter_tag_kg_entries
        >>> callable(_iter_tag_kg_entries)
        True
    """
    tags: list[str] = []
    seen: set[str] = set()
    for triple in document.get("kg") or []:
        if triple.get("field_type") != "keywords":
            continue
        tag = _entity_text((triple.get("subject") or {}).get("content", []))
        normalized = tag.lower()
        if tag and normalized not in seen:
            seen.add(normalized)
            tags.append(tag)
    return tags


def collect_ontology_covered_positions(
    document: dict,
    settings: OntologyBuildSettings | None = None,
) -> dict[str, set[int]]:
    """Collect token positions represented by all analyzed document signals.

    Example:
        >>> from thot.tasks.document_ontology.OntologyBuilder import collect_ontology_covered_positions
        >>> callable(collect_ontology_covered_positions)
        True
    """
    settings = settings or OntologyBuildSettings()
    covered_by_field: dict[str, set[int]] = {}

    triples = list(_iter_included_kg_triples(document, settings))
    keywords = document.get("keywords") or []
    tags = _iter_tag_kg_entries(document)

    for spec in _field_specs(settings):
        if not spec.include:
            continue

        morphosyntax = document.get(spec.morph_key) or []
        covered: set[int] = set()

        for triple in triples:
            if triple.get("field_type") == spec.field_type:
                covered.update(_triple_positions(triple))

        covered.update(_ner_span_positions(document.get(spec.ner_key) or []))
        covered.update(_keyword_positions_in_morph(keywords, morphosyntax))
        covered.update(
            _dependency_token_positions(document.get(spec.deps_key) or [])
        )

        if spec.field_type == "content":
            covered.update(
                _golden_chunk_positions(document.get("golden_chunks") or [])
            )

        for tag in tags:
            covered.update(_positions_for_text_phrase(tag, morphosyntax))

        covered_by_field[spec.field_type] = covered

    return covered_by_field


def _coverage_stats(document: dict, settings: OntologyBuildSettings) -> dict:
    """Coverage stats helper.

    Example:
        >>> from thot.tasks.document_ontology.OntologyBuilder import _coverage_stats
        >>> callable(_coverage_stats)
        True
    """
    covered_by_field = collect_ontology_covered_positions(document, settings)
    covered_tokens = 0
    total_tokens = 0
    covered_characters = 0
    total_characters = 0

    for spec in _field_specs(settings):
        if not spec.include:
            continue

        morphosyntax = document.get(spec.morph_key) or []
        covered_positions = covered_by_field.get(spec.field_type, set())

        total_tokens += len(morphosyntax)
        total_characters += sum(
            len(str(token.get("text", ""))) for token in morphosyntax
        )

        for position in covered_positions:
            if 0 <= position < len(morphosyntax):
                covered_tokens += 1
                covered_characters += len(
                    str(morphosyntax[position].get("text", ""))
                )

    text_coverage_percent = (
        round(100.0 * covered_characters / total_characters, 2)
        if total_characters
        else 0.0
    )

    return {
        "text_coverage_percent": text_coverage_percent,
        "covered_tokens": covered_tokens,
        "total_tokens": total_tokens,
        "covered_characters": covered_characters,
        "total_characters": total_characters,
    }


def _add_svo_to_graph(
    graph: Graph,
    doc_uri: URIRef,
    entity_node: Callable[..., URIRef],
    entity_index: dict[str, str],
    subject_text: str,
    verb_text: str,
    object_text: str,
    vocabulary: OntologyVocabulary | None = None,
) -> None:
    """Add svo to graph helper.

    Example:
        >>> from thot.tasks.document_ontology.OntologyBuilder import _add_svo_to_graph
        >>> callable(_add_svo_to_graph)
        True
    """
    subject_text = str(subject_text).strip()
    verb_text = str(verb_text).strip()
    object_text = str(object_text).strip()
    if not subject_text or not verb_text:
        return

    vocab = vocabulary or OntologyVocabulary.empty()
    subject_uri = entity_node(subject_text, role="subject")
    predicate_uri = _predicate_uri(verb_text, vocab)
    graph.add((doc_uri, TKEIR.hasStatement, subject_uri))

    if object_text:
        object_class = _lookup_class(
            object_text,
            entity_index,
            vocabulary,
            role="object",
        )
        if vocab.is_node_class(object_class):
            object_uri = entity_node(object_text, role="object")
            graph.add((subject_uri, predicate_uri, object_uri))
        else:
            graph.add((subject_uri, predicate_uri, Literal(object_text)))
            if object_class == METRIC_CLASS:
                numeric = object_text.replace(",", "").replace("%", "").strip()
                if NUMERIC_RE.match(numeric):
                    graph.add(
                        (
                            subject_uri,
                            TKEIR.hasNumericValue,
                            Literal(numeric, datatype=XSD.decimal),
                        )
                    )
    else:
        graph.add((subject_uri, predicate_uri, Literal("")))


def _add_keyword_to_graph(
    graph: Graph,
    doc_uri: URIRef,
    doc_key: str,
    keyword: dict,
    morphosyntax: list[dict],
    settings: OntologyBuildSettings,
    seen_keywords: set[str],
) -> None:
    text = str(keyword.get("text", "")).strip()
    normalized = text.lower()
    if (
        not text
        or normalized in seen_keywords
        or not is_valid_keyword_label(
            text,
            min_length=settings.min_keyword_length,
        )
    ):
        return

    span = keyword.get("span") or {}
    start = span.get("start")
    end = span.get("end")
    if start is None or end is None:
        return

    start_idx = int(start)
    end_idx = int(end)
    if not (0 <= start_idx <= end_idx <= len(morphosyntax)):
        return

    candidate = " ".join(
        str(token.get("text", "")).strip()
        for token in morphosyntax[start_idx:end_idx]
    )
    if text.lower() not in candidate.lower():
        return

    seen_keywords.add(normalized)
    keyword_uri = TKEIRDOC[f"{doc_key}/Keyword/{_slug(text)}"]
    graph.add((keyword_uri, RDF.type, TKEIR.Keyword))
    graph.add((keyword_uri, RDFS.label, Literal(text)))
    graph.add((doc_uri, TKEIR.hasKeyword, keyword_uri))


def _enrich_field_analysis(
    graph: Graph,
    document: dict,
    doc_uri: URIRef,
    doc_key: str,
    spec: DocumentFieldSpec,
    entity_node: Callable[..., URIRef],
    entity_index: dict[str, str],
    keywords: list[dict],
    settings: OntologyBuildSettings,
    seen_keywords: set[str],
    vocabulary: OntologyVocabulary | None = None,
) -> None:
    morphosyntax = document.get(spec.morph_key) or []

    for span in document.get(spec.ner_key) or []:
        text = str(span.get("text", "")).strip()
        if text:
            graph.add((doc_uri, TKEIR.hasMention, entity_node(text)))

    for subject_text, verb_text, object_text in _dependency_relations(
        document.get(spec.deps_key) or []
    ):
        _add_svo_to_graph(
            graph=graph,
            doc_uri=doc_uri,
            entity_node=entity_node,
            entity_index=entity_index,
            subject_text=subject_text,
            verb_text=verb_text,
            object_text=object_text,
            vocabulary=vocabulary,
        )

    for keyword in keywords:
        _add_keyword_to_graph(
            graph,
            doc_uri,
            doc_key,
            keyword,
            morphosyntax,
            settings,
            seen_keywords,
        )


def _enrich_tags(
    graph: Graph,
    doc_uri: URIRef,
    doc_key: str,
    document: dict,
) -> None:
    seen_tags: set[str] = set()
    for tag in _iter_tag_kg_entries(document):
        normalized = tag.lower()
        if normalized in seen_tags:
            continue
        seen_tags.add(normalized)

        tag_uri = TKEIRDOC[f"{doc_key}/Tag/{_slug(tag)}"]
        graph.add((tag_uri, RDF.type, TKEIR.Tag))
        graph.add((tag_uri, RDFS.label, Literal(tag)))
        graph.add((doc_uri, TKEIR.hasTag, tag_uri))
        graph.add((tag_uri, TKEIR.isTagOf, doc_uri))


def _enrich_golden_chunks(
    graph: Graph,
    document: dict,
    doc_uri: URIRef,
    doc_key: str,
    entity_node: Callable[..., URIRef],
    entity_index: dict[str, str],
    vocabulary: OntologyVocabulary | None = None,
) -> None:
    for index, chunk in enumerate(document.get("golden_chunks") or []):
        chunk_id = str(chunk.get("chunk_id") or f"chunk-{index}")
        chunk_uri = TKEIRDOC[f"{doc_key}/Chunk/{_slug(chunk_id)}"]

        graph.add((chunk_uri, RDF.type, TKEIR.DocumentChunk))
        graph.add((chunk_uri, RDFS.label, Literal(chunk_id)))
        graph.add((doc_uri, TKEIR.hasChunk, chunk_uri))

        metadata = chunk.get("metadata") or {}
        for entities in (metadata.get("primary_entities") or {}).values():
            for entity_text in entities:
                text = str(entity_text).strip()
                if text:
                    graph.add((chunk_uri, TKEIR.hasMention, entity_node(text)))

        for triplet in metadata.get("svo_triplets") or []:
            if len(triplet) < 3:
                continue
            _add_svo_to_graph(
                graph=graph,
                doc_uri=chunk_uri,
                entity_node=entity_node,
                entity_index=entity_index,
                subject_text=str(triplet[0]).strip(),
                verb_text=str(triplet[1]).strip(),
                object_text=str(triplet[2]).strip(),
                vocabulary=vocabulary,
            )


def _enrich_graph_from_analysis(
    graph: Graph,
    document: dict,
    doc_uri: URIRef,
    doc_key: str,
    entity_node: Callable[..., URIRef],
    entity_index: dict[str, str],
    settings: OntologyBuildSettings,
    vocabulary: OntologyVocabulary | None = None,
) -> None:
    """Enrich graph from analysis helper.

    Example:
        >>> from thot.tasks.document_ontology.OntologyBuilder import _enrich_graph_from_analysis
        >>> callable(_enrich_graph_from_analysis)
        True
    """
    keywords = document.get("keywords") or []
    seen_keywords: set[str] = set()

    for spec in _field_specs(settings):
        if not spec.include:
            continue
        _enrich_field_analysis(
            graph=graph,
            document=document,
            doc_uri=doc_uri,
            doc_key=doc_key,
            spec=spec,
            entity_node=entity_node,
            entity_index=entity_index,
            keywords=keywords,
            settings=settings,
            seen_keywords=seen_keywords,
            vocabulary=vocabulary,
        )

    _enrich_tags(graph, doc_uri, doc_key, document)

    if settings.include_content_triples:
        _enrich_golden_chunks(
            graph,
            document,
            doc_uri,
            doc_key,
            entity_node,
            entity_index,
            vocabulary,
        )


def _triple_parts(triple: dict) -> tuple[str, str, str]:
    """Triple parts helper.

    Example:
        >>> triple = {'subject': {'content': ['A']}, 'property': {'content': ['did']}, 'value': {'content': ['B']}}
        >>> _triple_parts(triple)
        ('A', 'did', 'B')
    """
    subject = _entity_text((triple.get("subject") or {}).get("content", []))
    verb = _entity_text((triple.get("property") or {}).get("content", []))
    obj = _entity_text((triple.get("value") or {}).get("content", []))
    return subject, verb, obj


def _triple_positions(triple: dict) -> set[int]:
    """Triple positions helper.

    Example:
        >>> triple = {'subject': {'positions': [0, 1]}, 'property': {'positions': [2]}, 'value': {'positions': [3]}}
        >>> sorted(_triple_positions(triple))
        [0, 1, 2, 3]
    """
    positions: set[int] = set()
    for role in ("subject", "property", "value"):
        part = triple.get(role) or {}
        for position in part.get("positions") or []:
            positions.add(int(position))
    return positions


def _iter_included_kg_triples(
    document: dict,
    settings: OntologyBuildSettings,
) -> Iterator[dict]:
    """Iter included kg triples helper.

    Example:
        >>> from thot.tasks.document_ontology.OntologyBuilder import _iter_included_kg_triples
        >>> callable(_iter_included_kg_triples)
        True
    """
    for triple in document.get("kg") or []:
        field_type = triple.get("field_type")
        if field_type == "keywords":
            continue
        if field_type == "title" and not settings.include_title_triples:
            continue
        if field_type == "content" and not settings.include_content_triples:
            continue

        subject_text, verb_text, _ = _triple_parts(triple)
        if not subject_text or not verb_text:
            continue
        yield triple


def compute_ontology_text_coverage(
    document: dict,
    settings: OntologyBuildSettings | None = None,
) -> dict:
    """Return how much document text is represented in the ontology graph.

    Example:
        >>> from thot.tasks.document_ontology.OntologyBuilder import compute_ontology_text_coverage
        >>> callable(compute_ontology_text_coverage)
        True
    """
    settings = settings or OntologyBuildSettings()
    return _coverage_stats(document, settings)


def build_document_graph(
    document: dict,
    settings: OntologyBuildSettings | None = None,
    vocabulary: OntologyVocabulary | None = None,
) -> Graph:
    """Build an RDF graph for the document from kg triples and NER spans.

    Example:
        >>> from thot.tasks.document_ontology.OntologyBuilder import build_document_graph
        >>> callable(build_document_graph)
        True
    """
    settings = settings or OntologyBuildSettings()
    vocabulary = vocabulary or OntologyVocabulary.empty()
    graph = Graph()
    graph.bind("tkeir", TKEIR)
    graph.bind("tkeirdoc", TKEIRDOC)

    entity_index = _build_entity_index(
        (document.get("title_ner") or [])
        + (document.get("content_ner") or []),
        vocabulary,
    )
    doc_key = _doc_key(document)
    doc_uri = TKEIRDOC[doc_key]
    graph.add((doc_uri, RDF.type, TKEIR.Document))
    graph.add((doc_uri, RDFS.label, Literal(doc_key)))

    seen_nodes: dict[tuple[str, str], URIRef] = {}

    def entity_node(text: str, role: str = "subject") -> URIRef:
        """entity_node API.

        Example:
            >>> from thot.tasks.document_ontology.OntologyBuilder import entity_node
            >>> callable(entity_node)
            True
        """
        clean_text = str(text).strip()
        class_name = _lookup_class(
            clean_text,
            entity_index,
            vocabulary,
            role=role,
        )
        cache_key = (class_name, clean_text.lower())
        if cache_key not in seen_nodes:
            node = _node_uri(doc_key, clean_text, class_name)
            seen_nodes[cache_key] = node
            graph.add((node, RDF.type, TKEIR[class_name]))
            graph.add((node, RDFS.label, Literal(clean_text)))
        return seen_nodes[cache_key]

    for triple in _iter_included_kg_triples(document, settings):
        subject_text, verb_text, object_text = _triple_parts(triple)
        _add_svo_to_graph(
            graph=graph,
            doc_uri=doc_uri,
            entity_node=entity_node,
            entity_index=entity_index,
            subject_text=subject_text,
            verb_text=verb_text,
            object_text=object_text,
            vocabulary=vocabulary,
        )

    _enrich_graph_from_analysis(
        graph=graph,
        document=document,
        doc_uri=doc_uri,
        doc_key=doc_key,
        entity_node=entity_node,
        entity_index=entity_index,
        settings=settings,
        vocabulary=vocabulary,
    )

    return graph
