"""Title: Query expansion via the in-memory business ontology.

Resolve the analyzed request (NER, keywords, kg/SVO) plus the raw query to
concept ids, then expand with synonyms, narrower, broader, related, and
paraphrase bridges. Expanded ids are OR-joined against Vespa
``ontology_concepts`` (see ``doc_base.sd``) together with NN + BM25 — this
**expands** recall and never AND-filters hits.

Author: Eric Blaudez

Copyright (c) 2026 Thales
Licensed under the MIT License.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from thot.tools.search.business_ontology import (
    BusinessConcept,
    BusinessOntology,
)
from thot.tools.search.text_normalizer import TextNormalizer

LOGGER = logging.getLogger(__name__)

# Cap concept ids sent to Vespa ``ontology_concepts contains`` OR clauses.
DEFAULT_MAX_CONCEPT_IDS = 16


@dataclass(frozen=True)
class ExpansionWeights:
    """Per-relation term weights from config.

    Example:
        >>> ExpansionWeights(synonyms=0.8).synonyms
        0.8
    """

    original: float = 1.0
    synonyms: float = 0.9
    narrower: float = 0.6
    broader: float = 0.3
    related: float = 0.2
    paraphrase: float = 0.85


@dataclass
class ExpandedTerm:
    """One weighted expansion term (raw + normalized for dual BM25 arms).

    Example:
        >>> ExpandedTerm(text="cloud", weight=1.0, relation="original", normalized_text="cloud")
        ExpandedTerm(text='cloud', weight=1.0, relation='original', concept_id=None, normalized_text='cloud')
    """

    text: str
    weight: float
    relation: str
    concept_id: str | None = None
    normalized_text: str = ""


@dataclass
class QueryExpansionResult:
    """Expanded query terms + resolved / graph-expanded concept ids.

    Example:
        >>> QueryExpansionResult(
        ...     terms=[],
        ...     concept_ids=["c1"],
        ...     raw_query="hello",
        ...     normalized_query="hello",
        ... ).concept_ids
        ['c1']
    """

    terms: list[ExpandedTerm]
    concept_ids: list[str]
    raw_query: str
    normalized_query: str


class QueryExpander:
    """Expand a query using business-ontology relations.

    Example:
        >>> from thot.tools.search.business_ontology import BusinessOntology
        >>> from thot.tools.search.text_normalizer import TextNormalizer
        >>> import spacy
        >>> nlp = spacy.blank("en")
        >>> QueryExpander(
        ...     BusinessOntology([]),
        ...     TextNormalizer("blank", nlp=nlp),
        ...     weights=ExpansionWeights(),
        ... ).enabled
        True
    """

    def __init__(
        self,
        ontology: BusinessOntology,
        normalizer: TextNormalizer,
        *,
        weights: ExpansionWeights,
        max_terms_per_relation: int = 5,
        enabled: bool = True,
        max_concept_ids: int = DEFAULT_MAX_CONCEPT_IDS,
    ) -> None:
        """Configure expander with ontology graph and normalizer.

        Example:
            >>> from thot.tools.search.business_ontology import BusinessOntology
            >>> import spacy
            >>> nlp = spacy.blank("en")
            >>> expander = QueryExpander(
            ...     BusinessOntology([]),
            ...     TextNormalizer("blank", nlp=nlp),
            ...     weights=ExpansionWeights(),
            ... )
            >>> expander.max_concept_ids >= 1
            True
        """
        self.ontology = ontology
        self.normalizer = normalizer
        self.weights = weights
        self.max_terms_per_relation = max_terms_per_relation
        self.enabled = enabled
        self.max_concept_ids = max(1, int(max_concept_ids))

    def expand(
        self,
        query: str,
        *,
        seed_labels: list[str] | None = None,
    ) -> QueryExpansionResult:
        """Resolve + expand query (and optional NLP seeds) for retrieval.

        Args:
            query: Raw user query.
            seed_labels: Extra labels from the NLP pipeline (NER, keywords,
                SVO subject/verb/object, lemmas). Each is resolved against the
                ontology; hits expand with synonyms / narrower / broader /
                related concept ids and labels.

        Returns:
            Expansion result: BM25 terms + concept ids for Vespa
            ``ontology_concepts``.

        Example:
            >>> from thot.tools.search.business_ontology import BusinessOntology
            >>> import spacy
            >>> nlp = spacy.blank("en")
            >>> expander = QueryExpander(
            ...     BusinessOntology([]),
            ...     TextNormalizer("blank", nlp=nlp),
            ...     weights=ExpansionWeights(),
            ...     enabled=False,
            ... )
            >>> expander.expand("hello").raw_query
            'hello'
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
        # Structural identifier stems only (FoxO3a → foxo). Language
        # morphology / synonyms come from TextNormalizer + ontology.
        from thot.tools.search.lexical_signal import token_stems, tokenize

        seen_lower = {query.strip().casefold()}
        stem_budget = 12
        for tok in tokenize(query):
            if stem_budget <= 0:
                break
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
                stem_budget -= 1
                if stem_budget <= 0:
                    break

        concept_ids: list[str] = []
        if not self.enabled or not self.ontology.concepts:
            return QueryExpansionResult(
                terms=terms,
                concept_ids=concept_ids,
                raw_query=query,
                normalized_query=normalized,
            )

        resolved = self._resolve_concepts(query, normalized, seed_labels)
        # Graph expansion: add semantically close concept ids (not only labels).
        concept_ids = self._expand_concept_neighborhood(resolved)

        for cid in list(concept_ids):
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
            self._add_paraphrase_bridges(terms, concept, normalized, cid)

        # Seed labels that did not resolve still help the BM25 probe.
        for label in seed_labels or []:
            text = (label or "").strip()
            if not text:
                continue
            if self.ontology.resolve(text, self.normalizer):
                continue
            self._add_group(terms, [text], 0.85, "nlp_seed", "")

        LOGGER.debug(
            "query expansion concepts=%s (seeds=%d) terms=%d",
            concept_ids,
            len(seed_labels or []),
            len(terms),
        )
        return QueryExpansionResult(
            terms=terms,
            concept_ids=concept_ids,
            raw_query=query,
            normalized_query=normalized,
        )

    def _resolve_concepts(
        self,
        query: str,
        normalized: str,
        seed_labels: list[str] | None,
    ) -> list[str]:
        """Resolve query tokens + NLP seed labels to ontology concept ids.

        Example:
            >>> from thot.tools.search.business_ontology import BusinessOntology
            >>> import spacy
            >>> nlp = spacy.blank("en")
            >>> expander = QueryExpander(
            ...     BusinessOntology([]),
            ...     TextNormalizer("blank", nlp=nlp),
            ...     weights=ExpansionWeights(),
            ... )
            >>> expander._resolve_concepts("hello", "hello", None)
            []
        """
        from thot.tools.search.lexical_signal import token_stems, tokenize

        candidates: list[str] = [normalized] + normalized.split()
        for tok in tokenize(query):
            for stem in token_stems(tok):
                candidates.append(self.normalizer.normalize(stem))
        for label in seed_labels or []:
            lab = (label or "").strip()
            if not lab:
                continue
            candidates.append(self.normalizer.normalize(lab))
            for tok in tokenize(lab):
                candidates.append(self.normalizer.normalize(tok))
                for stem in token_stems(tok):
                    candidates.append(self.normalizer.normalize(stem))

        resolved: list[str] = []
        for cand in candidates:
            if not cand:
                continue
            cid = self.ontology.resolve_normalized(cand)
            if cid and cid not in resolved:
                resolved.append(cid)

        # Multi-word labels and paraphrase bridges (substring in query / seeds).
        haystacks = [normalized]
        for label in seed_labels or []:
            n = self.normalizer.normalize(label)
            if n:
                haystacks.append(n)
        for concept in self.ontology.concepts.values():
            if concept.concept_id in resolved:
                continue
            phrases: list[str] = []
            for lab in (
                [concept.preferred_label]
                + list(concept.synonyms)
                + list(concept.surface_forms)
            ):
                if " " in (lab or "").strip():
                    phrases.append(lab)
            for bridge in concept.paraphrase_bridges:
                phrases.append(bridge.claim)
                phrases.append(bridge.document)
            for phrase in phrases:
                pn = self.normalizer.normalize(phrase)
                if len(pn) < 5:
                    continue
                if any(pn in hay or hay in pn for hay in haystacks if hay):
                    resolved.append(concept.concept_id)
                    break
        return resolved

    def _expand_concept_neighborhood(self, seed_ids: list[str]) -> list[str]:
        """Add narrower / broader / related concept ids around resolved seeds.

        Order: direct hits first, then narrower, related, broader (semantic
        closeness preference). Synonyms share the same concept id already.

        Example:
            >>> from thot.tools.search.business_ontology import BusinessOntology
            >>> import spacy
            >>> nlp = spacy.blank("en")
            >>> expander = QueryExpander(
            ...     BusinessOntology([]),
            ...     TextNormalizer("blank", nlp=nlp),
            ...     weights=ExpansionWeights(),
            ... )
            >>> expander._expand_concept_neighborhood([])
            []
        """
        out: list[str] = []
        seen: set[str] = set()

        def _add(cid: str) -> bool:
            """Add a concept id to the neighborhood list when under cap.

            Example:
                >>> True
                True
            """
            key = (cid or "").strip()
            if not key or key in seen:
                return False
            if key not in self.ontology.concepts:
                return False
            seen.add(key)
            out.append(key)
            return len(out) >= self.max_concept_ids

        for cid in seed_ids:
            if _add(cid):
                return out

        # Pass 1: narrower (more specific → usually better for retrieval).
        for cid in seed_ids:
            concept = self.ontology.concepts.get(cid)
            if concept is None:
                continue
            for other in concept.narrower:
                if _add(other):
                    return out

        # Pass 2: related.
        for cid in seed_ids:
            concept = self.ontology.concepts.get(cid)
            if concept is None:
                continue
            for other in concept.related:
                if _add(other):
                    return out

        # Pass 3: broader (more generic — keep last / capped).
        for cid in seed_ids:
            concept = self.ontology.concepts.get(cid)
            if concept is None:
                continue
            for other in concept.broader:
                if _add(other):
                    return out
        return out

    def _add_paraphrase_bridges(
        self,
        terms: list[ExpandedTerm],
        concept: BusinessConcept,
        normalized_query: str,
        concept_id: str,
    ) -> None:
        """Add document-side forms when the claim side matches the query.

        Example:
            >>> from thot.tools.search.business_ontology import BusinessConcept, BusinessOntology
            >>> import spacy
            >>> nlp = spacy.blank("en")
            >>> expander = QueryExpander(
            ...     BusinessOntology([]),
            ...     TextNormalizer("blank", nlp=nlp),
            ...     weights=ExpansionWeights(),
            ... )
            >>> terms = []
            >>> expander._add_paraphrase_bridges(
            ...     terms,
            ...     BusinessConcept(concept_id="c1", preferred_label="Test"),
            ...     "test",
            ...     "c1",
            ... )
            >>> isinstance(terms, list)
            True
        """
        bridges = concept.paraphrase_bridges or []
        if not bridges:
            return
        weight = float(self.weights.paraphrase)
        targets: list[str] = []
        for bridge in bridges:
            claim_n = self.normalizer.normalize(bridge.claim)
            doc_n = self.normalizer.normalize(bridge.document)
            if not claim_n or not doc_n:
                continue
            # Bidirectional: claim→document (SciFact) and document→claim.
            if claim_n in normalized_query or normalized_query in claim_n:
                targets.append(bridge.document)
            elif doc_n in normalized_query or normalized_query in doc_n:
                targets.append(bridge.claim)
        if targets:
            self._add_group(terms, targets, weight, "paraphrase", concept_id)

    def _labels_for_ids(self, concept_ids: list[str]) -> list[str]:
        """Resolve concept ids to preferred labels (+ limited synonyms).

        Example:
            >>> from thot.tools.search.business_ontology import BusinessOntology
            >>> import spacy
            >>> nlp = spacy.blank("en")
            >>> expander = QueryExpander(
            ...     BusinessOntology([]),
            ...     TextNormalizer("blank", nlp=nlp),
            ...     weights=ExpansionWeights(),
            ... )
            >>> expander._labels_for_ids([])
            []
        """
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
        """Append weighted labels to the expansion term list (deduplicated).

        Example:
            >>> from thot.tools.search.business_ontology import BusinessOntology
            >>> import spacy
            >>> nlp = spacy.blank("en")
            >>> expander = QueryExpander(
            ...     BusinessOntology([]),
            ...     TextNormalizer("blank", nlp=nlp),
            ...     weights=ExpansionWeights(),
            ... )
            >>> terms = []
            >>> expander._add_group(terms, ["cloud"], 1.0, "synonyms", "c1")
            >>> terms[0].text
            'cloud'
        """
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
                    concept_id=concept_id or None,
                    normalized_text=self.normalizer.normalize(text),
                )
            )
            seen.add(text.lower())
            added += 1
            if added >= self.max_terms_per_relation:
                break
