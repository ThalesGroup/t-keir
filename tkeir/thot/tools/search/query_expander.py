"""Title: Query expansion via the in-memory business ontology.

Author: Eric Blaudez

Copyright (c) 2026 Thales
Licensed under the MIT License.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from thot.tools.search.business_ontology import BusinessOntology
from thot.tools.search.text_normalizer import TextNormalizer

LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class ExpansionWeights:
    """Per-relation term weights from config."""

    original: float = 1.0
    synonyms: float = 0.9
    narrower: float = 0.6
    broader: float = 0.3
    related: float = 0.2


@dataclass
class ExpandedTerm:
    """One weighted expansion term (raw + normalized for dual BM25 arms)."""

    text: str
    weight: float
    relation: str
    concept_id: str | None = None
    normalized_text: str = ""


@dataclass
class QueryExpansionResult:
    """Expanded query terms + resolved concept ids."""

    terms: list[ExpandedTerm]
    concept_ids: list[str]
    raw_query: str
    normalized_query: str


class QueryExpander:
    """Expand a query using business-ontology relations."""

    def __init__(
        self,
        ontology: BusinessOntology,
        normalizer: TextNormalizer,
        *,
        weights: ExpansionWeights,
        max_terms_per_relation: int = 5,
        enabled: bool = True,
    ) -> None:
        self.ontology = ontology
        self.normalizer = normalizer
        self.weights = weights
        self.max_terms_per_relation = max_terms_per_relation
        self.enabled = enabled

    def expand(self, query: str) -> QueryExpansionResult:
        """Return weighted terms for Vespa YQL construction.

        Args:
            query: Raw user query.

        Returns:
            Expansion result (always includes the original query term).
        """
        normalized = self.normalizer.normalize(query)
        terms = [
            ExpandedTerm(
                text=query.strip(),
                weight=self.weights.original,
                relation="original",
                normalized_text=normalized,
            )
        ]
        # Always add scientific / morphological stems so Vespa BM25 can
        # match aliases (FoxO3a → foxo, p150n → p150) even before ontology.
        from thot.tools.search.lexical_signal import tokenize, token_stems

        seen_lower = {query.strip().lower()}
        for tok in tokenize(query):
            for stem in token_stems(tok):
                if stem in seen_lower or len(stem) < 3:
                    continue
                seen_lower.add(stem)
                terms.append(
                    ExpandedTerm(
                        text=stem,
                        weight=0.75,
                        relation="stem",
                        normalized_text=self.normalizer.normalize(stem),
                    )
                )

        concept_ids: list[str] = []
        if not self.enabled or not self.ontology.concepts:
            return QueryExpansionResult(
                terms=terms,
                concept_ids=concept_ids,
                raw_query=query,
                normalized_query=normalized,
            )

        # Resolve concepts from normalized query tokens / stems / whole string.
        candidates = [normalized] + normalized.split()
        for tok in tokenize(query):
            for stem in token_stems(tok):
                candidates.append(self.normalizer.normalize(stem))
        resolved: list[str] = []
        for cand in candidates:
            if not cand:
                continue
            cid = self.ontology.resolve_normalized(cand)
            if cid and cid not in resolved:
                resolved.append(cid)
        concept_ids = resolved

        for cid in concept_ids:
            concept = self.ontology.concepts.get(cid)
            if concept is None:
                continue
            self._add_group(
                terms, concept.synonyms, self.weights.synonyms, "synonyms", cid
            )
            narrow_labels = self._labels_for_ids(concept.narrower)
            self._add_group(
                terms,
                narrow_labels,
                self.weights.narrower,
                "narrower",
                cid,
            )
            broad_labels = self._labels_for_ids(concept.broader)
            self._add_group(
                terms, broad_labels, self.weights.broader, "broader", cid
            )
            related_labels = self._labels_for_ids(concept.related)
            self._add_group(
                terms, related_labels, self.weights.related, "related", cid
            )

        LOGGER.debug(
            "query expansion concepts=%s terms=%d",
            concept_ids,
            len(terms),
        )
        return QueryExpansionResult(
            terms=terms,
            concept_ids=concept_ids,
            raw_query=query,
            normalized_query=normalized,
        )

    def _labels_for_ids(self, concept_ids: list[str]) -> list[str]:
        labels: list[str] = []
        for cid in concept_ids:
            concept = self.ontology.concepts.get(cid)
            if concept is None:
                continue
            labels.append(concept.preferred_label)
            labels.extend(concept.synonyms[:2])
        return labels

    def _add_group(
        self,
        terms: list[ExpandedTerm],
        labels: list[str],
        weight: float,
        relation: str,
        concept_id: str,
    ) -> None:
        seen = {term.text.lower() for term in terms}
        added = 0
        for label in labels:
            text = (label or "").strip()
            if not text or text.lower() in seen:
                continue
            terms.append(
                ExpandedTerm(
                    text=text,
                    weight=weight,
                    relation=relation,
                    concept_id=concept_id,
                    normalized_text=self.normalizer.normalize(text),
                )
            )
            seen.add(text.lower())
            added += 1
            if added >= self.max_terms_per_relation:
                break
