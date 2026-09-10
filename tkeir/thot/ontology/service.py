"""Title: Ontology enrichment service (extract, map, extend).

First-class indexing stage: chunk + optional expert ontology → concept IDs,
relations, and catalog concepts to persist. Independent of Vespa I/O.

Author: Eric Blaudez

Copyright (c) 2026 Thales
Licensed under the MIT License.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from thot.ontology.expansion import (
    ExpansionResult,
    ExpansionSpec,
    expand_concept_ids,
)
from thot.ontology.identity import predicate_id, preserve_or_mint
from thot.ontology.json_concepts import extract_json_concepts
from thot.ontology.model import (
    Ontology,
    OntologyConcept,
    OntologyRelation,
    Provenance,
    ProvenanceKind,
    label_index,
    map_label,
)

LOGGER = logging.getLogger(__name__)

_METRIC_KEYS = (
    "extracted",
    "mapped",
    "new",
    "relations",
    "json_concepts",
    "failures",
    "mapping_failures",
)


def _inc(metrics: dict[str, int], key: str, amount: int = 1) -> None:
    """Increment a metric bucket.

    Example:
        >>> from thot.ontology.service import _inc
        >>> m = {}
        >>> _inc(m, 'extracted', 2)
        >>> m['extracted']
        2
    """
    metrics[key] = int(metrics.get(key) or 0) + int(amount)


@dataclass
class ChunkOntologyEnrichment:
    """Per-chunk ontology attachments plus catalog delta.

    Example:
        >>> from thot.ontology.service import ChunkOntologyEnrichment
        >>> ChunkOntologyEnrichment().concept_ids
        []
    """

    concept_ids: list[str] = field(default_factory=list)
    relations: list[OntologyRelation] = field(default_factory=list)
    catalog: Ontology = field(default_factory=Ontology)
    metrics: dict[str, int] = field(default_factory=dict)
    expansion_labels: list[str] = field(default_factory=list)


class OntologyService:
    """Extract / map / extend ontology for one document or query.

    Works with no expert ontology, an expert seed, or an already-extended
    catalog. Does not call the network or Vespa.

    Example:
        >>> from thot.ontology.service import OntologyService
        >>> svc = OntologyService()
        >>> out = svc.enrich_chunk(
        ...     {'text_raw': 'K8S cluster'},
        ...     {'document_ontology': {'json_ld': '[{"identifier": "K8S"}]'}},
        ... )
        >>> 'K8S' in out.concept_ids
        True
    """

    def __init__(
        self,
        *,
        expert: Ontology | None = None,
        json_structural: bool = True,
        max_concepts: int = 64,
        max_relations: int = 32,
    ) -> None:
        """Configure optional expert seed and caps.

        Example:
            >>> from thot.ontology.service import OntologyService
            >>> OntologyService(max_concepts=8).max_concepts
            8
        """
        self.expert = expert or Ontology()
        self.json_structural = bool(json_structural)
        self.max_concepts = max(1, int(max_concepts))
        self.max_relations = max(1, int(max_relations))
        self._label_index = (
            label_index(self.expert) if self.expert.concepts else {}
        )

    @classmethod
    def from_business_payload(
        cls,
        payload: dict[str, Any] | None,
        **kwargs: Any,
    ) -> OntologyService:
        """Build a service from a business-ontology YAML/JSON payload.

        Example:
            >>> from thot.ontology.service import OntologyService
            >>> svc = OntologyService.from_business_payload(
            ...     {'concepts': [{'concept_id': 'C1', 'preferred_label': 'K8s'}]}
            ... )
            >>> svc.expert.get('C1').preferred_label
            'K8s'
        """
        return cls(expert=Ontology.from_business_payload(payload), **kwargs)

    def map_concepts(self, labels: list[str]) -> tuple[list[str], int]:
        """Map surface labels to expert IDs when possible.

        Returns ``(ids, mapped_count)``. Unmapped stable IDs are kept as-is;
        sentence-like labels are minted under ``doc:``.

        Example:
            >>> from thot.ontology.service import OntologyService
            >>> svc = OntologyService.from_business_payload(
            ...     {'concepts': [{'concept_id': 'C1', 'preferred_label': 'Kubernetes'}]}
            ... )
            >>> ids, mapped = svc.map_concepts(['Kubernetes', 'unknown-token'])
            >>> ids[0]
            'C1'
            >>> mapped
            1
        """
        ids: list[str] = []
        mapped = 0
        seen: set[str] = set()
        for raw in labels:
            text = str(raw or "").strip()
            if not text:
                continue
            hit = map_label(text, self.expert, index=self._label_index)
            if hit:
                mapped += 1
                cid = hit
            else:
                cid = preserve_or_mint(text)
            key = cid.casefold()
            if key in seen:
                continue
            seen.add(key)
            ids.append(cid)
        return ids, mapped

    def extract_svo_relations(
        self,
        document: dict[str, Any],
        chunk: dict[str, Any],
        *,
        source_ref: str = "",
    ) -> list[OntologyRelation]:
        """Build relations from pipeline ``kg`` / chunk ``svo_triplets``.

        Example:
            >>> from thot.ontology.service import OntologyService
            >>> rels = OntologyService().extract_svo_relations(
            ...     {'kg': [{
            ...         'subject': {'content': ['Kubernetes']},
            ...         'property': {'content': ['implements']},
            ...         'value': {'content': ['orchestration']},
            ...     }]},
            ...     {'text_raw': 'Kubernetes implements orchestration'},
            ... )
            >>> rels[0].predicate_id
            'pred:implements'
        """
        from thot.tools.search.chunk_ontology import (
            _chunk_match_text,
            _kg_node_text,
            _label_in_text,
        )

        hay = _chunk_match_text(chunk).casefold()
        provenance = Provenance(
            kind=ProvenanceKind.DOCUMENT_EXTRACTED,
            source_ref=source_ref,
            chunk_id=str(chunk.get("chunk_id") or ""),
            confidence=0.8,
        )
        triples: list[tuple[str, str, str]] = []

        def _add(subj: str, pred: str, obj: str) -> None:
            if not subj or not pred or not obj:
                return
            if hay and not (
                _label_in_text(subj, hay) or subj.casefold() in hay
            ):
                return
            triples.append((subj, pred, obj))

        for key in ("kg", "svo_triplets", "svo"):
            payload = document.get(key)
            if not payload:
                continue
            if isinstance(payload, dict):
                payload = (
                    payload.get("triplets") or payload.get("triples") or []
                )
            if not isinstance(payload, list):
                continue
            for row in payload:
                if isinstance(row, dict):
                    subj = _kg_node_text(row.get("subject") or row.get("s"))
                    pred = _kg_node_text(
                        row.get("property")
                        or row.get("predicate")
                        or row.get("verb")
                        or row.get("p")
                    )
                    obj = _kg_node_text(
                        row.get("value") or row.get("object") or row.get("o")
                    )
                    _add(subj, pred, obj)
                elif isinstance(row, (list, tuple)) and len(row) >= 3:
                    _add(
                        _kg_node_text(row[0]),
                        _kg_node_text(row[1]),
                        _kg_node_text(row[2]),
                    )

        metadata = chunk.get("metadata") or {}
        for row in metadata.get("svo_triplets") or []:
            if isinstance(row, (list, tuple)) and len(row) >= 3:
                _add(
                    _kg_node_text(row[0]),
                    _kg_node_text(row[1]),
                    _kg_node_text(row[2]),
                )

        out: list[OntologyRelation] = []
        seen: set[str] = set()
        for subj, pred, obj in triples:
            ids, _mapped = self.map_concepts([subj, obj])
            if len(ids) < 2:
                continue
            rel = OntologyRelation(
                subject_id=ids[0],
                predicate_id=predicate_id(pred),
                object_id=ids[1],
                confidence=0.8,
                provenance=provenance,
            )
            key = rel.key()
            if key in seen:
                continue
            seen.add(key)
            out.append(rel)
            if len(out) >= self.max_relations:
                break
        return out

    def enrich_chunk(
        self,
        chunk: dict[str, Any],
        document: dict[str, Any],
        *,
        ontology_payload: dict[str, Any] | None = None,
    ) -> ChunkOntologyEnrichment:
        """Run the ontology indexing stage for one golden chunk.

        Combines expert matches, document JSON-LD, JSON structural concepts,
        and SVO relations. Absence of an expert ontology is valid.

        Example:
            >>> from thot.ontology.service import OntologyService
            >>> out = OntologyService().enrich_chunk(
            ...     {'text_raw': 'x'},
            ...     {'record': {'customer': {'country': 'France'}}},
            ... )
            >>> any(i.startswith('json:attribute:') for i in out.concept_ids)
            True
        """
        metrics = {key: 0 for key in _METRIC_KEYS}
        catalog = Ontology()
        if self.expert.concepts:
            for concept in self.expert.concepts.values():
                catalog.add_concept(concept)

        try:
            from thot.tools.search.chunk_ontology import chunk_ontology_fields

            fields = chunk_ontology_fields(
                chunk, document, ontology_payload=ontology_payload
            )
        except Exception as exc:  # noqa: BLE001
            LOGGER.warning("Ontology field extract failed: %s", exc)
            _inc(metrics, "failures")
            fields = {}

        raw_ids = list(fields.get("concept_ids") or []) + list(
            fields.get("linked_concept_ids") or []
        )
        mapped_ids, mapped_n = self.map_concepts(raw_ids)
        _inc(metrics, "extracted", len(raw_ids))
        _inc(metrics, "mapped", mapped_n)
        expansion_labels = [
            str(lab).strip()
            for lab in fields.get("expansion_labels") or []
            if lab and str(lab).strip()
        ]

        json_ids: list[str] = []
        json_rels: list[OntologyRelation] = []
        if self.json_structural:
            record = document.get("record")
            if not isinstance(record, dict):
                record = None
            try:
                if isinstance(record, dict):
                    extracted = extract_json_concepts(
                        record,
                        source_ref=str(
                            document.get("source_doc_id")
                            or document.get("source")
                            or ""
                        ),
                        chunk_id=str(chunk.get("chunk_id") or ""),
                        max_concepts=self.max_concepts,
                    )
                    json_ids = extracted.chunk_ids()
                    json_rels = list(extracted.ontology.relations)
                    catalog = catalog.extend(extracted.ontology)
                    _inc(
                        metrics,
                        "json_concepts",
                        len(extracted.ontology.concepts),
                    )
                for cid in document.get("record_concept_ids") or []:
                    key = str(cid).strip()
                    if key:
                        json_ids.append(key)
            except Exception as exc:  # noqa: BLE001
                LOGGER.warning("JSON structural concepts failed: %s", exc)
                _inc(metrics, "failures")

        source_ref = str(
            document.get("source_doc_id") or document.get("source") or ""
        )
        try:
            svo_rels = self.extract_svo_relations(
                document, chunk, source_ref=source_ref
            )
        except Exception as exc:  # noqa: BLE001
            LOGGER.warning("SVO relation extract failed: %s", exc)
            _inc(metrics, "failures")
            svo_rels = []

        concept_ids: list[str] = []
        seen: set[str] = set()
        for cid in [*mapped_ids, *json_ids]:
            key = str(cid).strip()
            fold = key.casefold()
            if not key or fold in seen:
                continue
            seen.add(fold)
            concept_ids.append(key)
            if key not in catalog.concepts:
                catalog.add_concept(
                    OntologyConcept(
                        concept_id=key,
                        preferred_label=key,
                        provenance=Provenance(
                            kind=ProvenanceKind.DOCUMENT_EXTRACTED,
                            source_ref=source_ref,
                            chunk_id=str(chunk.get("chunk_id") or ""),
                        ),
                    )
                )
                _inc(metrics, "new")
            if len(concept_ids) >= self.max_concepts:
                break

        relations: list[OntologyRelation] = []
        seen_rel: set[str] = set()
        for rel in [*json_rels, *svo_rels]:
            key = rel.key()
            if key in seen_rel:
                continue
            seen_rel.add(key)
            relations.append(rel)
            catalog.add_relation(rel)
            if len(relations) >= self.max_relations:
                break
        _inc(metrics, "relations", len(relations))

        LOGGER.info(
            "ontology enrich concepts=%d mapped=%d new=%d relations=%d json=%d",
            len(concept_ids),
            metrics.get("mapped", 0),
            metrics.get("new", 0),
            len(relations),
            metrics.get("json_concepts", 0),
        )
        try:
            from thot.core.ThotMetrics import ThotMetrics

            ThotMetrics.create_counter(
                short_name="ontology_enrich",
                function_name="tkeir_ontology_enrich_total",
                counter_description="Ontology chunk enrichment runs",
            )
            ThotMetrics.increment_counter(
                short_name="ontology_enrich",
                method="index",
                path="ontology.enrich",
                status=0 if not metrics.get("failures") else 1,
            )
        except Exception:  # noqa: BLE001
            pass

        return ChunkOntologyEnrichment(
            concept_ids=concept_ids,
            relations=relations,
            catalog=catalog,
            metrics=metrics,
            expansion_labels=expansion_labels[:96],
        )

    def expand(
        self,
        seed_ids: list[str],
        spec: ExpansionSpec | None = None,
        *,
        catalog: Ontology | None = None,
    ) -> ExpansionResult:
        """Expand seed concept IDs using expert + optional extra catalog.

        Example:
            >>> from thot.ontology.service import OntologyService
            >>> from thot.ontology.expansion import ExpansionSpec
            >>> svc = OntologyService.from_business_payload({
            ...     'concepts': [
            ...         {'concept_id': 'k8s', 'preferred_label': 'K8s', 'narrower': ['pod']},
            ...         {'concept_id': 'pod', 'preferred_label': 'Pod'},
            ...     ]
            ... })
            >>> 'pod' in svc.expand(['k8s'], ExpansionSpec(include_children=True)).concept_ids
            True
        """
        graph = self.expert
        if catalog is not None and catalog.concepts:
            graph = self.expert.extend(catalog)
        return expand_concept_ids(seed_ids, graph, spec)
