"""Title: Ontology overlap scoring (query concepts × document / chunk concepts).

Prefers indexed chunk ``concept_ids`` / ``linked_concept_ids`` (Graph-RAG);
falls back to document ``json_ld`` extraction.

Author: Eric Blaudez

Copyright (c) 2026 Thales
Licensed under the MIT License.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from typing import Any

from thot.tools.search.business_ontology import BusinessOntology
from thot.tools.search.text_normalizer import TextNormalizer

LOGGER = logging.getLogger(__name__)
_WORD_RE = re.compile(r"[^\W\d_][\w]{1,}", re.UNICODE)


@dataclass(frozen=True)
class OntologyMatchWeights:
    """Match-type weights from config.

    Example:
        >>> from thot.tools.search.ontology_scorer import OntologyMatchWeights
        >>> OntologyMatchWeights().exact
        1.0
    """

    exact: float = 1.0
    synonym: float = 0.9
    narrower: float = 0.6
    broader: float = 0.3
    shared_parent: float = 0.2


@dataclass
class OntologyScorerConfig:
    """Runtime knobs for overlap scoring.

    Example:
        >>> from thot.tools.search.ontology_scorer import OntologyScorerConfig
        >>> OntologyScorerConfig().neutral_score
        0.5
    """

    enabled: bool = True
    match_weights: OntologyMatchWeights = OntologyMatchWeights()
    max_traversal_depth: int = 2
    normalize_by_query_concepts: bool = True
    neutral_score: float = 0.5


class OntologyScorer:
    """Score documents by concept overlap through the business ontology.

    Example:
        >>> from thot.tools.search.business_ontology import BusinessConcept, BusinessOntology
        >>> from thot.tools.search.ontology_scorer import OntologyScorer, OntologyScorerConfig
        >>> class _Norm:
        ...     def normalize(self, text): return str(text).lower().strip()
        >>> bo = BusinessOntology([BusinessConcept("C1", "Maritime")])
        >>> scorer = OntologyScorer(bo, _Norm(), OntologyScorerConfig())
        >>> scorer.score(["C1"], ["C1"])
        1.0
    """

    def __init__(
        self,
        ontology: BusinessOntology,
        normalizer: TextNormalizer,
        config: OntologyScorerConfig,
    ) -> None:
        """Wire ontology, normalizer, and scoring config.

        Example:
            >>> from thot.tools.search.business_ontology import BusinessOntology
            >>> from thot.tools.search.ontology_scorer import OntologyScorer, OntologyScorerConfig
            >>> class _Norm:
            ...     def normalize(self, text): return str(text).lower().strip()
            >>> OntologyScorer(BusinessOntology([]), _Norm(), OntologyScorerConfig()).config.enabled
            True
        """
        self.ontology = ontology
        self.normalizer = normalizer
        self.config = config
        self._doc_cache: dict[str, list[str]] = {}

    def extract_document_concepts(
        self, json_ld: str | dict[str, Any]
    ) -> list[str]:
        """Extract concept ids / normalized strings from document json_ld.

        Example:
            >>> from thot.tools.search.business_ontology import BusinessOntology
            >>> from thot.tools.search.ontology_scorer import OntologyScorer, OntologyScorerConfig
            >>> class _Norm:
            ...     def normalize(self, text): return str(text).lower().strip()
            >>> scorer = OntologyScorer(BusinessOntology([]), _Norm(), OntologyScorerConfig())
            >>> scorer.extract_document_concepts('[{"identifier": "C1"}]')
            ['c1', 'C1']
        """
        if isinstance(json_ld, str):
            if not json_ld.strip():
                return []
            try:
                data = json.loads(json_ld)
            except json.JSONDecodeError:
                return [
                    self.normalizer.normalize(tok)
                    for tok in _WORD_RE.findall(json_ld)
                    if self.normalizer.normalize(tok)
                ]
        else:
            data = json_ld
        concepts: list[str] = []
        seen: set[str] = set()
        for label in _collect_labels(data):
            cid = self.ontology.resolve(label, self.normalizer)
            if cid:
                if cid not in seen:
                    seen.add(cid)
                    concepts.append(cid)
                continue
            normalized = self.normalizer.normalize(label)
            if normalized and normalized not in seen:
                seen.add(normalized)
                concepts.append(normalized)
        for cid in _collect_identifiers(data):
            if cid not in seen:
                seen.add(cid)
                concepts.append(cid)
        return concepts

    def concepts_for_document(
        self, source_doc_id: str, json_ld: str
    ) -> list[str]:
        """Cached concept extraction keyed by document id.

        Example:
            >>> from thot.tools.search.business_ontology import BusinessOntology
            >>> from thot.tools.search.ontology_scorer import OntologyScorer, OntologyScorerConfig
            >>> class _Norm:
            ...     def normalize(self, text): return str(text).lower().strip()
            >>> scorer = OntologyScorer(BusinessOntology([]), _Norm(), OntologyScorerConfig())
            >>> scorer.concepts_for_document("doc1", '[{"identifier": "C1"}]')
            ['c1', 'C1']
        """
        cached = self._doc_cache.get(source_doc_id)
        if cached is not None:
            return cached
        concepts = self.extract_document_concepts(json_ld)
        self._doc_cache[source_doc_id] = concepts
        return concepts

    def concepts_for_hit(
        self,
        source_doc_id: str,
        *,
        json_ld: str = "",
        concept_ids: list[str] | None = None,
        linked_concept_ids: list[str] | None = None,
    ) -> list[str]:
        """Prefer indexed chunk concept fields; else document json_ld.

        Example:
            >>> from thot.tools.search.business_ontology import BusinessOntology
            >>> from thot.tools.search.ontology_scorer import OntologyScorer, OntologyScorerConfig
            >>> class _Norm:
            ...     def normalize(self, text): return str(text).lower().strip()
            >>> scorer = OntologyScorer(BusinessOntology([]), _Norm(), OntologyScorerConfig())
            >>> scorer.concepts_for_hit("doc1", concept_ids=["C1", "C2"])
            ['C1', 'C2']
        """
        indexed: list[str] = []
        seen: set[str] = set()
        for raw in list(concept_ids or []) + list(linked_concept_ids or []):
            cid = str(raw or "").strip()
            if not cid:
                continue
            key = cid.casefold()
            if key in seen:
                continue
            seen.add(key)
            indexed.append(cid)
            # Also resolve labels through the external ontology when present.
            resolved = self.ontology.resolve(cid, self.normalizer)
            if resolved and resolved.casefold() not in seen:
                seen.add(resolved.casefold())
                indexed.append(resolved)
        if indexed:
            self._doc_cache[source_doc_id] = indexed
            return indexed
        return self.concepts_for_document(source_doc_id, json_ld)

    def score(
        self,
        query_concept_ids: list[str],
        document_concepts: list[str],
    ) -> float:
        """Best-match ontology overlap in ``[0, 1]`` (or neutral).

        Example:
            >>> from thot.tools.search.business_ontology import BusinessConcept, BusinessOntology
            >>> from thot.tools.search.ontology_scorer import OntologyScorer, OntologyScorerConfig
            >>> class _Norm:
            ...     def normalize(self, text): return str(text).lower().strip()
            >>> bo = BusinessOntology([BusinessConcept("C1", "Maritime")])
            >>> scorer = OntologyScorer(bo, _Norm(), OntologyScorerConfig())
            >>> scorer.score(["C1"], ["C1"])
            1.0
        """
        if not self.config.enabled:
            return self.config.neutral_score
        if not query_concept_ids:
            return self.config.neutral_score
        if not document_concepts:
            return self.config.neutral_score

        weights = self.config.match_weights
        weight_map = {
            "exact": weights.exact,
            "synonym": weights.synonym,
            "narrower": weights.narrower,
            "broader": weights.broader,
            "shared_parent": weights.shared_parent,
        }
        # Casefold map for document-native exact matches without external graph.
        doc_fold = {str(d).casefold(): str(d) for d in document_concepts}
        total = 0.0
        for q_cid in query_concept_ids:
            best = 0.0
            q_fold = str(q_cid).casefold()
            if q_fold in doc_fold:
                best = max(best, weights.exact)
            for d_cid in document_concepts:
                if q_cid == d_cid:
                    best = max(best, weights.exact)
                    continue
                relation = self.ontology.relation(
                    q_cid, d_cid, self.config.max_traversal_depth
                )
                if relation:
                    best = max(best, weight_map.get(relation, 0.0))
            total += best

        if self.config.normalize_by_query_concepts:
            return total / max(len(query_concept_ids), 1)
        return min(1.0, total)


class OntologyRescorer:
    """Blend first-stage ranks with ontology overlap (optional Graph-RAG stage).

    Controlled by ``dual_hybrid.ontology_scoring.enabled`` (default false).

    Example:
        >>> from thot.tools.search.business_ontology import BusinessConcept, BusinessOntology
        >>> from thot.tools.search.ontology_scorer import (
        ...     OntologyRescorer,
        ...     OntologyScorer,
        ...     OntologyScorerConfig,
        ... )
        >>> class _Norm:
        ...     def normalize(self, text): return str(text).lower().strip()
        >>> bo = BusinessOntology([BusinessConcept("C1", "Maritime")])
        >>> rescorer = OntologyRescorer(
        ...     OntologyScorer(bo, _Norm(), OntologyScorerConfig()),
        ...     weight=0.0,
        ... )
        >>> rescorer.rescore(["C1"], [("doc1", 0.9, ["C1"])])
        [('doc1', 0.9)]
    """

    def __init__(
        self,
        scorer: OntologyScorer,
        *,
        weight: float = 0.13,
    ) -> None:
        """Store scorer and blend weight for ontology rescoring.

        Example:
            >>> from thot.tools.search.business_ontology import BusinessOntology
            >>> from thot.tools.search.ontology_scorer import (
            ...     OntologyRescorer,
            ...     OntologyScorer,
            ...     OntologyScorerConfig,
            ... )
            >>> class _Norm:
            ...     def normalize(self, text): return str(text).lower().strip()
            >>> rescorer = OntologyRescorer(
            ...     OntologyScorer(BusinessOntology([]), _Norm(), OntologyScorerConfig())
            ... )
            >>> rescorer.weight
            0.13
        """
        self.scorer = scorer
        self.weight = max(0.0, min(1.0, float(weight)))

    def rescore(
        self,
        query_concept_ids: list[str],
        hits: list[tuple[str, float, list[str]]],
    ) -> list[tuple[str, float]]:
        """Rescore ``(doc_id, first_stage_score, ontology_concepts)`` rows.

        Returns:
            ``(doc_id, blended_score)`` best first. When disabled / no query
            concepts / weight=0, returns first-stage order unchanged.

        Example:
            >>> from thot.tools.search.business_ontology import BusinessConcept, BusinessOntology
            >>> from thot.tools.search.ontology_scorer import (
            ...     OntologyRescorer,
            ...     OntologyScorer,
            ...     OntologyScorerConfig,
            ... )
            >>> class _Norm:
            ...     def normalize(self, text): return str(text).lower().strip()
            >>> bo = BusinessOntology([BusinessConcept("C1", "Maritime")])
            >>> rescorer = OntologyRescorer(
            ...     OntologyScorer(bo, _Norm(), OntologyScorerConfig()),
            ...     weight=0.0,
            ... )
            >>> rescorer.rescore(["C1"], [("doc1", 0.9, ["C1"])])
            [('doc1', 0.9)]
        """
        if (
            not self.scorer.config.enabled
            or self.weight <= 0.0
            or not query_concept_ids
            or not hits
        ):
            ranked = sorted(hits, key=lambda row: row[1], reverse=True)
            return [(doc_id, float(score)) for doc_id, score, _ in ranked]

        first = {doc_id: float(score) for doc_id, score, _ in hits}
        lo = min(first.values()) if first else 0.0
        hi = max(first.values()) if first else 0.0
        span = hi - lo
        blended: dict[str, float] = {}
        for doc_id, score, doc_concepts in hits:
            first_n = ((score - lo) / span) if span > 0 else 0.0
            ont = self.scorer.score(
                query_concept_ids,
                list(doc_concepts or []),
            )
            blended[doc_id] = (
                1.0 - self.weight
            ) * first_n + self.weight * float(ont)
        return sorted(blended.items(), key=lambda item: item[1], reverse=True)


def _collect_identifiers(node: Any, out: list[str] | None = None) -> list[str]:
    """Collect identifier / @id / concept_id strings from JSON-LD.

    Example:
        >>> from thot.tools.search.ontology_scorer import _collect_identifiers
        >>> _collect_identifiers({"identifier": "C1", "name": "Maritime"})
        ['C1']
    """
    if out is None:
        out = []
    if isinstance(node, dict):
        for key in ("identifier", "@id", "concept_id", "id"):
            val = node.get(key)
            if isinstance(val, str) and val.strip():
                cid = val.strip()
                if "://" in cid:
                    cid = cid.rstrip("/").rsplit("/", 1)[-1]
                if cid and len(cid) < 120:
                    out.append(cid)
        for value in node.values():
            _collect_identifiers(value, out)
    elif isinstance(node, list):
        for item in node:
            _collect_identifiers(item, out)
    return out


def _collect_labels(node: Any, out: list[str] | None = None) -> list[str]:
    """Walk JSON-LD-ish structures collecting string labels.

    Example:
        >>> from thot.tools.search.ontology_scorer import _collect_labels
        >>> _collect_labels({"name": "Maritime", "nested": {"label": "Naval"}})
        ['Maritime', 'Naval']
    """
    if out is None:
        out = []
    if isinstance(node, dict):
        for key, value in node.items():
            if key in {
                "name",
                "label",
                "prefLabel",
                "preferred_label",
                "@value",
                "keyword",
                "text",
            } and isinstance(value, str):
                out.append(value)
            else:
                _collect_labels(value, out)
    elif isinstance(node, list):
        for item in node:
            _collect_labels(item, out)
    elif isinstance(node, str) and len(node) < 120:
        out.append(node)
    return out
