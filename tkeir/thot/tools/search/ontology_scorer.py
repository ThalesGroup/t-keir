"""Title: Ontology overlap scoring (query concepts × document json_ld).

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
_WORD_RE = re.compile(r"[A-Za-z0-9_]{2,}")


@dataclass(frozen=True)
class OntologyMatchWeights:
    """Match-type weights from config."""

    exact: float = 1.0
    synonym: float = 0.9
    narrower: float = 0.6
    broader: float = 0.3
    shared_parent: float = 0.2


@dataclass
class OntologyScorerConfig:
    """Runtime knobs for overlap scoring."""

    enabled: bool = True
    match_weights: OntologyMatchWeights = OntologyMatchWeights()
    max_traversal_depth: int = 2
    normalize_by_query_concepts: bool = True
    neutral_score: float = 0.5


class OntologyScorer:
    """Score documents by concept overlap through the business ontology."""

    def __init__(
        self,
        ontology: BusinessOntology,
        normalizer: TextNormalizer,
        config: OntologyScorerConfig,
    ) -> None:
        self.ontology = ontology
        self.normalizer = normalizer
        self.config = config
        self._doc_cache: dict[str, list[str]] = {}

    def extract_document_concepts(self, json_ld: str | dict[str, Any]) -> list[str]:
        """Extract concept ids / normalized strings from document json_ld."""
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
        labels = _collect_labels(data)
        concepts: list[str] = []
        for label in labels:
            cid = self.ontology.resolve(label, self.normalizer)
            if cid:
                if cid not in concepts:
                    concepts.append(cid)
            else:
                normalized = self.normalizer.normalize(label)
                if normalized and normalized not in concepts:
                    concepts.append(normalized)
        return concepts

    def concepts_for_document(
        self, source_doc_id: str, json_ld: str
    ) -> list[str]:
        """Cached concept extraction keyed by document id."""
        cached = self._doc_cache.get(source_doc_id)
        if cached is not None:
            return cached
        concepts = self.extract_document_concepts(json_ld)
        self._doc_cache[source_doc_id] = concepts
        return concepts

    def score(
        self,
        query_concept_ids: list[str],
        document_concepts: list[str],
    ) -> float:
        """Best-match ontology overlap in ``[0, 1]`` (or neutral)."""
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
        total = 0.0
        for q_cid in query_concept_ids:
            best = 0.0
            for d_cid in document_concepts:
                if q_cid == d_cid:
                    best = max(best, weights.exact)
                    continue
                relation = self.ontology.relation(
                    q_cid, d_cid, self.config.max_traversal_depth
                )
                if relation:
                    best = max(best, weight_map.get(relation, 0.0))
                elif (
                    isinstance(d_cid, str)
                    and " " not in d_cid
                    and q_cid == d_cid
                ):
                    best = max(best, weights.exact)
            total += best

        if self.config.normalize_by_query_concepts:
            return total / max(len(query_concept_ids), 1)
        return min(1.0, total)


def _collect_labels(node: Any, out: list[str] | None = None) -> list[str]:
    """Walk JSON-LD-ish structures collecting string labels."""
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
