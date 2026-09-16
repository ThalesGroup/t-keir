"""Title: Corpus-level ontology catalog sync (insert-if-absent).

Concepts and SPO triples live in Vespa ``ontology_concept`` /
``ontology_triple`` for the whole corpus. Chunks and parent documents
store ID pointers only. Existing catalog rows are never overwritten.

Author: Eric Blaudez

Copyright (c) 2026 Thales
Licensed under the MIT License.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from thot.ontology.model import Ontology, OntologyConcept, OntologyRelation
from thot.ontology.vespa import (
    concept_to_vespa_fields,
    ontology_concept_docid,
    ontology_triple_docid,
    triple_to_vespa_fields,
)

LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class CorpusCatalogSyncResult:
    """Counts for one insert-if-absent catalog pass.

    Example:
        >>> from thot.ontology.catalog_sync import CorpusCatalogSyncResult
        >>> CorpusCatalogSyncResult(concepts_inserted=1).concepts_skipped
        0
    """

    concepts_inserted: int = 0
    concepts_skipped: int = 0
    triples_inserted: int = 0
    triples_skipped: int = 0


async def catalog_document_exists(
    vespa: Any, document_type: str, document_key: str
) -> bool:
    """Return True when Vespa already stores ``document_type`` / ``document_key``.

    Example:
        >>> import asyncio
        >>> from thot.ontology.catalog_sync import catalog_document_exists
        >>> class _Fake:
        ...     async def get_index_document(self, document_type, document_key):
        ...         return {'concept_id': 'C1'} if document_key == 'abc' else None
        >>> asyncio.run(catalog_document_exists(_Fake(), 'ontology_concept', 'abc'))
        True
        >>> asyncio.run(catalog_document_exists(_Fake(), 'ontology_concept', 'zzz'))
        False
    """
    getter = getattr(vespa, "get_index_document", None)
    if getter is None:
        return False
    fields = await getter(document_type, document_key)
    return bool(fields)


async def insert_missing_concepts(
    vespa: Any,
    concepts: list[OntologyConcept] | dict[str, OntologyConcept],
    *,
    source_ref: str = "",
) -> tuple[int, int]:
    """PUT concepts that are not already in the corpus catalog.

    Returns:
        ``(inserted, skipped)``.

    Example:
        >>> import asyncio
        >>> from thot.ontology.catalog_sync import insert_missing_concepts
        >>> from thot.ontology.model import OntologyConcept
        >>> from thot.ontology.vespa import ontology_concept_docid
        >>> class _Fake:
        ...     def __init__(self):
        ...         self.store = {}
        ...     async def get_index_document(self, document_type, document_key):
        ...         return self.store.get((document_type, document_key))
        ...     async def upsert_ontology_concept(self, fields, document_key):
        ...         self.store[('ontology_concept', document_key)] = fields
        >>> fake = _Fake()
        >>> cid = ontology_concept_docid('C1')
        >>> fake.store[('ontology_concept', cid)] = {'concept_id': 'C1'}
        >>> inserted, skipped = asyncio.run(
        ...     insert_missing_concepts(
        ...         fake, [OntologyConcept('C1'), OntologyConcept('C2')]
        ...     )
        ... )
        >>> (inserted, skipped)
        (1, 1)
    """
    rows = (
        list(concepts.values())
        if isinstance(concepts, dict)
        else list(concepts)
    )
    inserted = 0
    skipped = 0
    seen: set[str] = set()
    for concept in rows:
        cid = str(concept.concept_id or "").strip()
        if not cid or cid.casefold() in seen:
            continue
        seen.add(cid.casefold())
        key = ontology_concept_docid(cid)
        try:
            if await catalog_document_exists(vespa, "ontology_concept", key):
                skipped += 1
                continue
            fields = concept_to_vespa_fields(concept)
            if source_ref and not fields.get("source_ref"):
                fields["source_ref"] = source_ref
            await vespa.upsert_ontology_concept(fields, key)
            inserted += 1
        except Exception as exc:  # noqa: BLE001
            LOGGER.warning(
                "ontology_concept catalog sync failed id=%s: %s", cid, exc
            )
    return inserted, skipped


async def insert_missing_triples(
    vespa: Any,
    relations: list[OntologyRelation],
    *,
    source_ref: str = "",
) -> tuple[int, int]:
    """PUT SPO triples that are not already in the corpus catalog.

    Example:
        >>> import asyncio
        >>> from thot.ontology.catalog_sync import insert_missing_triples
        >>> from thot.ontology.model import OntologyRelation
        >>> class _Fake:
        ...     def __init__(self):
        ...         self.store = {}
        ...     async def get_index_document(self, document_type, document_key):
        ...         return self.store.get((document_type, document_key))
        ...     async def upsert_ontology_triple(self, fields, document_key):
        ...         self.store[('ontology_triple', document_key)] = fields
        >>> fake = _Fake()
        >>> rel = OntologyRelation('a', 'pred:has_value', 'b')
        >>> inserted, skipped = asyncio.run(
        ...     insert_missing_triples(fake, [rel, rel], source_ref='doc1')
        ... )
        >>> (inserted, skipped)
        (1, 1)
    """
    inserted = 0
    skipped = 0
    seen: set[str] = set()
    for relation in relations:
        compact = relation.key()
        if not compact or compact in seen:
            if compact in seen:
                skipped += 1
            continue
        seen.add(compact)
        key = ontology_triple_docid(
            relation.subject_id, relation.predicate_id, relation.object_id
        )
        try:
            if await catalog_document_exists(vespa, "ontology_triple", key):
                skipped += 1
                continue
            fields = triple_to_vespa_fields(
                relation, first_source_ref=source_ref
            )
            await vespa.upsert_ontology_triple(fields, key)
            inserted += 1
        except Exception as exc:  # noqa: BLE001
            LOGGER.warning(
                "ontology_triple catalog sync failed key=%s: %s",
                compact,
                exc,
            )
    return inserted, skipped


async def sync_corpus_ontology(
    vespa: Any,
    catalog: Ontology,
    *,
    source_ref: str = "",
    index_concepts: bool = True,
    index_triples: bool = True,
) -> CorpusCatalogSyncResult:
    """Insert catalog concepts and triples that are not already stored.

    Query the corpus index (GET by stable docid) before PUT so every
    corpus shares one graph: a triple extracted from later chunks is
    skipped when an earlier document already stored it.

    Example:
        >>> import asyncio
        >>> from thot.ontology.catalog_sync import sync_corpus_ontology
        >>> from thot.ontology.model import Ontology, OntologyConcept
        >>> from thot.ontology.model import OntologyRelation
        >>> class _Fake:
        ...     def __init__(self):
        ...         self.store = {}
        ...     async def get_index_document(self, document_type, document_key):
        ...         return self.store.get((document_type, document_key))
        ...     async def upsert_ontology_concept(self, fields, document_key):
        ...         self.store[('ontology_concept', document_key)] = fields
        ...     async def upsert_ontology_triple(self, fields, document_key):
        ...         self.store[('ontology_triple', document_key)] = fields
        >>> ont = Ontology()
        >>> ont.add_concept(OntologyConcept('C1'))
        >>> ont.add_relation(OntologyRelation('C1', 'pred:related', 'C2'))
        >>> result = asyncio.run(sync_corpus_ontology(_Fake(), ont))
        >>> (result.concepts_inserted, result.triples_inserted)
        (1, 1)
    """
    concepts_inserted = concepts_skipped = 0
    triples_inserted = triples_skipped = 0
    if index_concepts:
        concepts_inserted, concepts_skipped = await insert_missing_concepts(
            vespa, catalog.concepts, source_ref=source_ref
        )
    if index_triples:
        triples_inserted, triples_skipped = await insert_missing_triples(
            vespa, catalog.relations, source_ref=source_ref
        )
    return CorpusCatalogSyncResult(
        concepts_inserted=concepts_inserted,
        concepts_skipped=concepts_skipped,
        triples_inserted=triples_inserted,
        triples_skipped=triples_skipped,
    )
