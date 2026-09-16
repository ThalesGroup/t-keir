"""Title: Vespa adapter for the canonical ontology (not the ontology model).

Maps domain concepts/relations to chunk fields, ``ontology_concept`` /
``ontology_triple`` catalog documents, and ``corpus_doc`` YQL. Ontology
semantics live in :mod:`thot.ontology.model`.

Author: Eric Blaudez

Copyright (c) 2026 Thales
Licensed under the MIT License.
"""

from __future__ import annotations

import hashlib
import logging
import re
from typing import Any

from thot.ontology.identity import parse_relation_key, relation_key
from thot.ontology.model import Ontology, OntologyConcept, OntologyRelation

LOGGER = logging.getLogger(__name__)

# Cap OR clauses so YQL stays bounded (same order of magnitude as expander).
MAX_CONCEPT_OR = 32
MAX_RELATION_OR = 16

_YQL_ESC = re.compile(r'["\\]')


def escape_yql_literal(value: str) -> str:
    """Escape a string for a Vespa YQL double-quoted literal.

    Example:
        >>> from thot.ontology.vespa import escape_yql_literal
        >>> escape_yql_literal("hello")
        'hello'
    """
    return _YQL_ESC.sub(lambda m: "\\" + m.group(0), value or "")


def ontology_concept_docid(concept_id: str) -> str:
    """Stable Vespa docid for an ontology_concept document.

    Example:
        >>> from thot.ontology.vespa import ontology_concept_docid
        >>> len(ontology_concept_docid('C4ISR')) == 40
        True
        >>> ontology_concept_docid('C4ISR') == ontology_concept_docid('C4ISR')
        True
    """
    digest = hashlib.sha256((concept_id or "").encode("utf-8")).hexdigest()
    return digest[:40]


def ontology_triple_docid(
    subject_id: str, predicate_id_value: str, object_id: str
) -> str:
    """Stable Vespa docid for one corpus-level SPO triple.

    Example:
        >>> from thot.ontology.vespa import ontology_triple_docid
        >>> from thot.ontology.identity import PRED_HAS_VALUE
        >>> key = ontology_triple_docid('a', PRED_HAS_VALUE, 'b')
        >>> len(key) == 40
        True
        >>> key == ontology_triple_docid('a', PRED_HAS_VALUE, 'b')
        True
    """
    compact = relation_key(subject_id, predicate_id_value, object_id)
    digest = hashlib.sha256(compact.encode("utf-8")).hexdigest()
    return digest[:40]


def triple_to_vespa_fields(
    relation: OntologyRelation, *, first_source_ref: str = ""
) -> dict[str, Any]:
    """Fields for one ``ontology_triple`` catalog document.

    Example:
        >>> from thot.ontology.model import OntologyRelation
        >>> from thot.ontology.vespa import triple_to_vespa_fields
        >>> fields = triple_to_vespa_fields(
        ...     OntologyRelation('a', 'pred:has_value', 'b'),
        ...     first_source_ref='doc1',
        ... )
        >>> fields['triple_key']
        'a|pred:has_value|b'
        >>> fields['first_source_ref']
        'doc1'
    """
    source = first_source_ref or relation.provenance.source_ref or ""
    return {
        "triple_key": relation.key(),
        "subject_id": relation.subject_id,
        "predicate_id": relation.predicate_id,
        "object_id": relation.object_id,
        "confidence": float(relation.confidence),
        "provenance": relation.provenance.kind.value,
        "first_source_ref": source,
    }


def concept_to_vespa_fields(concept: OntologyConcept) -> dict[str, Any]:
    """Fields for one ``ontology_concept`` Vespa document (no embedding).

    Example:
        >>> from thot.ontology.model import OntologyConcept
        >>> from thot.ontology.vespa import concept_to_vespa_fields
        >>> concept_to_vespa_fields(OntologyConcept('C1', preferred_label='K8s'))['concept_id']
        'C1'
    """
    return {
        "concept_id": concept.concept_id,
        "concept_type": concept.concept_type or "concept",
        "preferred_label": concept.preferred_label or concept.concept_id,
        "aliases": list(concept.aliases),
        "definition": concept.definition or "",
        "parent_ids": list(concept.parent_ids or concept.broader_ids),
        "broader_ids": list(concept.broader_ids),
        "narrower_ids": list(concept.narrower_ids),
        "related_ids": list(concept.related_ids),
        "provenance": concept.provenance.kind.value,
        "source_ref": concept.provenance.source_ref or "",
    }


def chunk_ontology_vespa_fields(
    concept_ids: list[str],
    relations: list[OntologyRelation],
    *,
    max_concepts: int = 64,
    max_relations: int = 32,
) -> dict[str, Any]:
    """Chunk fields: concept IDs (legacy + canonical) and relation structs/keys.

    ``ontology_concepts`` is kept for already-indexed corpora and existing YQL.

    Example:
        >>> from thot.ontology.model import OntologyRelation
        >>> from thot.ontology.vespa import chunk_ontology_vespa_fields
        >>> fields = chunk_ontology_vespa_fields(
        ...     ['C1'], [OntologyRelation('C1', 'pred:has_value', 'V1')],
        ... )
        >>> fields['ontology_concepts'] == fields['ontology_concept_ids']
        True
        >>> fields['ontology_relations'][0]['subject_id']
        'C1'
    """
    ids: list[str] = []
    seen: set[str] = set()
    for cid in concept_ids:
        key = str(cid).strip()
        if not key or key.casefold() in seen:
            continue
        seen.add(key.casefold())
        ids.append(key)
        if len(ids) >= max_concepts:
            break
    rels: list[dict[str, Any]] = []
    keys: list[str] = []
    seen_rel: set[str] = set()
    for rel in relations[: max(0, max_relations)]:
        compact = relation_key(rel.subject_id, rel.predicate_id, rel.object_id)
        if compact in seen_rel:
            continue
        seen_rel.add(compact)
        keys.append(compact)
        rels.append(
            {
                "subject_id": rel.subject_id,
                "predicate_id": rel.predicate_id,
                "object_id": rel.object_id,
                "confidence": float(rel.confidence),
            }
        )
    return {
        "ontology_concepts": list(ids),
        "ontology_concept_ids": list(ids),
        "ontology_relations": rels,
        "ontology_rel_keys": keys,
    }


def vespa_fields_to_ontology(documents: list[dict[str, Any]]) -> Ontology:
    """Rebuild an :class:`Ontology` from ``ontology_concept`` Vespa docs.

    Example:
        >>> from thot.ontology.vespa import vespa_fields_to_ontology
        >>> ont = vespa_fields_to_ontology([
        ...     {'concept_id': 'C1', 'preferred_label': 'K8s', 'narrower_ids': ['C2']},
        ... ])
        >>> ont.get('C1').preferred_label
        'K8s'
    """
    from thot.ontology.model import (
        OntologyConcept,
        Provenance,
        ProvenanceKind,
    )

    ont = Ontology()
    for row in documents:
        cid = str(row.get("concept_id") or "").strip()
        if not cid:
            continue
        kind_raw = str(row.get("provenance") or "document_extracted")
        try:
            kind = ProvenanceKind(kind_raw)
        except ValueError:
            kind = ProvenanceKind.DOCUMENT_EXTRACTED
        ont.add_concept(
            OntologyConcept(
                concept_id=cid,
                preferred_label=str(row.get("preferred_label") or cid),
                concept_type=str(row.get("concept_type") or "concept"),
                aliases=list(row.get("aliases") or []),
                definition=str(row.get("definition") or ""),
                parent_ids=list(row.get("parent_ids") or []),
                broader_ids=list(row.get("broader_ids") or []),
                narrower_ids=list(row.get("narrower_ids") or []),
                related_ids=list(row.get("related_ids") or []),
                provenance=Provenance(
                    kind=kind,
                    source_ref=str(row.get("source_ref") or ""),
                ),
            )
        )
        for child in row.get("narrower_ids") or []:
            ont.add_relation(
                OntologyRelation(cid, "pred:narrower", str(child))
            )
        for parent in row.get("broader_ids") or row.get("parent_ids") or []:
            ont.add_relation(
                OntologyRelation(cid, "pred:broader", str(parent))
            )
        for other in row.get("related_ids") or []:
            ont.add_relation(OntologyRelation(cid, "pred:related", str(other)))
    return ont


def grouping_hits_to_ontology(
    *,
    concept_counts: dict[str, int],
    relation_keys: list[str],
) -> Ontology:
    """Build a catalog from Vespa grouping (legacy indexes without concept docs).

    Example:
        >>> from thot.ontology.vespa import grouping_hits_to_ontology
        >>> ont = grouping_hits_to_ontology(
        ...     concept_counts={'C1': 3},
        ...     relation_keys=['C1|pred:has_value|V1'],
        ... )
        >>> ont.get('C1') is not None
        True
        >>> ont.relations[0].object_id
        'V1'
    """
    from thot.ontology.model import OntologyConcept, Provenance, ProvenanceKind

    ont = Ontology()
    inferred = Provenance(kind=ProvenanceKind.INFERRED)
    for cid in concept_counts:
        ont.add_concept(
            OntologyConcept(
                concept_id=cid,
                preferred_label=cid,
                provenance=inferred,
            )
        )
    for key in relation_keys:
        parsed = parse_relation_key(key)
        if parsed is None:
            continue
        subj, pred, obj = parsed
        for cid in (subj, obj):
            if cid not in ont.concepts:
                ont.add_concept(
                    OntologyConcept(
                        concept_id=cid,
                        preferred_label=cid,
                        provenance=inferred,
                    )
                )
        ont.add_relation(
            OntologyRelation(subj, pred, obj, provenance=inferred)
        )
    return ont


def concept_contains_clauses(
    concept_ids: list[str], *, limit: int = MAX_CONCEPT_OR
) -> list[str]:
    """YQL OR fragments matching both legacy and canonical concept fields.

    Example:
        >>> from thot.ontology.vespa import concept_contains_clauses
        >>> clauses = concept_contains_clauses(['C1'])
        >>> any('ontology_concepts contains' in c for c in clauses)
        True
        >>> any('ontology_concept_ids contains' in c for c in clauses)
        True
    """
    parts: list[str] = []
    for cid in concept_ids[: max(0, limit)]:
        lit = escape_yql_literal(str(cid).strip())
        if not lit:
            continue
        parts.append(f'ontology_concepts contains "{lit}"')
        parts.append(f'ontology_concept_ids contains "{lit}"')
    return parts


def relation_contains_clauses(
    relations: list[dict[str, str]],
    *,
    mode: str = "partial",
    limit: int = MAX_RELATION_OR,
) -> list[str]:
    """YQL fragments for relation filters.

    ``mode='exact'`` uses compact ``ontology_rel_keys``.
    ``mode='partial'`` ORs subject/predicate/object ``contains`` on struct fields.

    Example:
        >>> from thot.ontology.vespa import relation_contains_clauses
        >>> exact = relation_contains_clauses(
        ...     [{'subject_id': 'a', 'predicate_id': 'pred:has_value', 'object_id': 'b'}],
        ...     mode='exact',
        ... )
        >>> 'ontology_rel_keys contains' in exact[0]
        True
        >>> partial = relation_contains_clauses(
        ...     [{'predicate_id': 'pred:has_value'}], mode='partial',
        ... )
        >>> 'predicate_id' in partial[0]
        True
    """
    parts: list[str] = []
    for raw in relations[: max(0, limit)]:
        subj = str(raw.get("subject_id") or raw.get("subject") or "").strip()
        pred = str(
            raw.get("predicate_id") or raw.get("predicate") or ""
        ).strip()
        obj = str(raw.get("object_id") or raw.get("object") or "").strip()
        if mode == "exact" and subj and pred and obj:
            lit = escape_yql_literal(relation_key(subj, pred, obj))
            parts.append(f'ontology_rel_keys contains "{lit}"')
            continue
        slots: list[str] = []
        if subj:
            slots.append(
                f'ontology_relations.subject_id contains "{escape_yql_literal(subj)}"'
            )
        if pred:
            slots.append(
                f'ontology_relations.predicate_id contains "{escape_yql_literal(pred)}"'
            )
        if obj:
            slots.append(
                f'ontology_relations.object_id contains "{escape_yql_literal(obj)}"'
            )
        if not slots:
            continue
        if len(slots) == 1:
            parts.append(slots[0])
        else:
            # sameElement keeps subject/predicate/object on one struct.
            inner = ", ".join(
                s.split("ontology_relations.", 1)[-1] for s in slots
            )
            parts.append(f"ontology_relations contains sameElement({inner})")
    return parts


def build_passage_yql(
    schema: str,
    *,
    hits: int,
    probe_terms_clause: str = "",
    concept_ids: list[str] | None = None,
    relations: list[dict[str, str]] | None = None,
    relation_match: str = "partial",
    include_nearest_neighbor: bool = True,
) -> str:
    """Hybrid YQL: NN + BM25 probe + optional concept/relation OR clauses.

    Ontology clauses are OR-joined (expand recall). Empty text still works
    when concept/relation filters are present.

    Example:
        >>> from thot.ontology.vespa import build_passage_yql
        >>> yql = build_passage_yql(
        ...     'global', hits=10, concept_ids=['C1'],
        ...     include_nearest_neighbor=False,
        ... )
        >>> 'ontology_concepts contains' in yql
        True
        >>> yql.startswith('select * from global where')
        True
    """
    parts: list[str] = []
    if include_nearest_neighbor:
        parts.append(
            f'({{"targetNumHits": {int(hits)}}}nearestNeighbor(dense_vector, q_dense))'
        )
    if probe_terms_clause:
        parts.append(probe_terms_clause)
    parts.extend(concept_contains_clauses(list(concept_ids or [])))
    parts.extend(
        relation_contains_clauses(
            list(relations or []), mode=relation_match or "partial"
        )
    )
    if not parts:
        parts.append("true")
    return f"select * from {schema} where " + " or ".join(parts)


def build_corpus_doc_yql(
    *,
    hits: int,
    probe_terms_clause: str = "",
    concept_ids: list[str] | None = None,
    include_nearest_neighbor: bool = True,
) -> str:
    """Hybrid YQL for the document-level ``corpus_doc`` schema.

    Example:
        >>> from thot.ontology.vespa import build_corpus_doc_yql
        >>> yql = build_corpus_doc_yql(
        ...     hits=8, concept_ids=['C1'], include_nearest_neighbor=False,
        ... )
        >>> yql.startswith('select * from corpus_doc where')
        True
        >>> 'ontology_concept_ids contains' in yql
        True
    """
    parts: list[str] = []
    if include_nearest_neighbor:
        parts.append(
            f'({{"targetNumHits": {int(hits)}}}nearestNeighbor(dense_vector, q_dense))'
        )
    if probe_terms_clause:
        parts.append(probe_terms_clause)
    for cid in list(concept_ids or [])[:MAX_CONCEPT_OR]:
        lit = escape_yql_literal(str(cid).strip())
        if lit:
            parts.append(f'ontology_concept_ids contains "{lit}"')
    if not parts:
        parts.append("true")
    return "select * from corpus_doc where " + " or ".join(parts)


def parse_grouping_counts(
    response: dict[str, Any], field_name: str
) -> dict[str, int]:
    """Extract ``{value: count}`` from a Vespa grouping response.

    Example:
        >>> from thot.ontology.vespa import parse_grouping_counts
        >>> parse_grouping_counts(
        ...     {'root': {'children': [{'children': [
        ...         {'value': 'C1', 'fields': {'count()': 3}},
        ...     ]}]}},
        ...     'ontology_concepts',
        ... )
        {'C1': 3}
    """
    counts: dict[str, int] = {}

    def _walk(node: Any) -> None:
        if isinstance(node, list):
            for item in node:
                _walk(item)
            return
        if not isinstance(node, dict):
            return
        value = node.get("value")
        fields = node.get("fields") or {}
        if value not in (None, "") and isinstance(fields, dict):
            n = fields.get("count()") or fields.get("count")
            if n is not None:
                counts[str(value)] = int(n)
        for key in ("children", "root"):
            if key in node:
                _walk(node[key])

    _walk(response)
    return counts


def concept_grouping_yql(
    schema: str = "global", max_groups: int = 5000
) -> str:
    """YQL grouping over chunk concept IDs (legacy indexes / catalog fallback).

    Example:
        >>> from thot.ontology.vespa import concept_grouping_yql
        >>> 'group(ontology_concepts)' in concept_grouping_yql()
        True
    """
    cap = max(1, int(max_groups))
    return (
        f"select ontology_concepts from {schema} where true limit 0 "
        f"| all(group(ontology_concepts) max({cap}) each(output(count())))"
    )


def relation_grouping_yql(
    schema: str = "global", max_groups: int = 5000
) -> str:
    """YQL grouping over compact relation keys.

    Example:
        >>> from thot.ontology.vespa import relation_grouping_yql
        >>> 'group(ontology_rel_keys)' in relation_grouping_yql()
        True
    """
    cap = max(1, int(max_groups))
    return (
        f"select ontology_rel_keys from {schema} where true limit 0 "
        f"| all(group(ontology_rel_keys) max({cap}) each(output(count())))"
    )


async def export_corpus_ontology(
    vespa: Any,
    *,
    max_docs: int = 5000,
    schema: str = "global",
) -> dict[str, Any]:
    """Export the corpus concept graph without loading every chunk.

    Prefers visiting ``ontology_concept`` documents; falls back to grouping
    on chunk ``ontology_concepts`` / ``ontology_rel_keys``.

    Example:
        >>> import inspect
        >>> from thot.ontology.vespa import export_corpus_ontology
        >>> inspect.iscoroutinefunction(export_corpus_ontology)
        True
    """
    documents: list[dict[str, Any]] = []
    continuation: str | None = None
    remaining = max(1, int(max_docs))
    try:
        while remaining > 0:
            wanted = min(400, remaining)
            payload = await vespa.visit_documents(
                "ontology_concept",
                cluster="global",
                wanted=wanted,
                continuation=continuation,
            )
            batch = payload.get("documents") or []
            for doc in batch:
                fields = doc.get("fields") or doc
                if isinstance(fields, dict) and fields.get("concept_id"):
                    documents.append(fields)
            remaining -= len(batch)
            continuation = payload.get("continuation")
            if not continuation or not batch:
                break
    except Exception as exc:  # noqa: BLE001
        LOGGER.warning("ontology_concept visit failed: %s", exc)

    triple_rows: list[dict[str, Any]] = []
    continuation = None
    remaining = max(1, int(max_docs))
    try:
        while remaining > 0:
            wanted = min(400, remaining)
            payload = await vespa.visit_documents(
                "ontology_triple",
                cluster="global",
                wanted=wanted,
                continuation=continuation,
            )
            batch = payload.get("documents") or []
            for doc in batch:
                fields = doc.get("fields") or doc
                if isinstance(fields, dict) and fields.get("triple_key"):
                    triple_rows.append(fields)
            remaining -= len(batch)
            continuation = payload.get("continuation")
            if not continuation or not batch:
                break
    except Exception as exc:  # noqa: BLE001
        LOGGER.warning("ontology_triple visit failed: %s", exc)

    if documents or triple_rows:
        ont = vespa_fields_to_ontology(documents)
        for row in triple_rows:
            subj = str(row.get("subject_id") or "").strip()
            pred = str(row.get("predicate_id") or "").strip()
            obj = str(row.get("object_id") or "").strip()
            if not (subj and pred and obj):
                parsed = parse_relation_key(str(row.get("triple_key") or ""))
                if parsed is None:
                    continue
                subj, pred, obj = parsed
            for cid in (subj, obj):
                if cid not in ont.concepts:
                    from thot.ontology.model import (
                        OntologyConcept,
                        Provenance,
                        ProvenanceKind,
                    )

                    ont.add_concept(
                        OntologyConcept(
                            concept_id=cid,
                            preferred_label=cid,
                            provenance=Provenance(
                                kind=ProvenanceKind.INFERRED
                            ),
                        )
                    )
            ont.add_relation(
                OntologyRelation(
                    subj,
                    pred,
                    obj,
                    confidence=float(row.get("confidence") or 1.0),
                )
            )
        exported = ont.to_export_dict()
        if documents and triple_rows:
            exported["source"] = "ontology_catalog"
        elif documents:
            exported["source"] = "ontology_concept"
        else:
            exported["source"] = "ontology_triple"
        return exported

    concept_counts: dict[str, int] = {}
    rel_keys: list[str] = []
    try:
        grouped = await vespa.search(
            {
                "yql": concept_grouping_yql(schema),
                "hits": 0,
                "timeout": "60s",
            }
        )
        concept_counts = parse_grouping_counts(grouped, "ontology_concepts")
    except Exception as exc:  # noqa: BLE001
        LOGGER.warning("concept grouping export failed: %s", exc)
    try:
        grouped_rel = await vespa.search(
            {
                "yql": relation_grouping_yql(schema),
                "hits": 0,
                "timeout": "60s",
            }
        )
        rel_keys = list(
            parse_grouping_counts(grouped_rel, "ontology_rel_keys").keys()
        )
    except Exception as exc:  # noqa: BLE001
        LOGGER.warning("relation grouping export failed: %s", exc)
    ont = grouping_hits_to_ontology(
        concept_counts=concept_counts, relation_keys=rel_keys
    )
    exported = ont.to_export_dict()
    exported["source"] = "chunk_grouping"
    return exported
