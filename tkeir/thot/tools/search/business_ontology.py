"""Title: In-memory business ontology (SKOS-like) for query expansion and overlap.

Never indexed in Vespa — loaded once at startup.

Author: Eric Blaudez

Copyright (c) 2026 Thales
Licensed under the MIT License.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

import yaml

LOGGER = logging.getLogger(__name__)


@dataclass
class BusinessConcept:
    """One business-ontology concept with relational links."""

    concept_id: str
    preferred_label: str
    synonyms: list[str] = field(default_factory=list)
    surface_forms: list[str] = field(default_factory=list)
    broader: list[str] = field(default_factory=list)
    narrower: list[str] = field(default_factory=list)
    related: list[str] = field(default_factory=list)


class OntologyNormalizer(Protocol):
    """Minimal normalizer used to build the reverse label index."""

    def normalize(self, text: str) -> str:
        """Normalize a label / surface form."""


class BusinessOntology:
    """Graph + reverse index from normalized labels to concept ids."""

    def __init__(self, concepts: list[BusinessConcept]) -> None:
        self.concepts: dict[str, BusinessConcept] = {
            concept.concept_id: concept for concept in concepts
        }
        self._label_index: dict[str, str] = {}

    def build_label_index(self, normalizer: OntologyNormalizer) -> None:
        """Index every preferred label, synonym, surface form, and stems."""
        from thot.tools.search.lexical_signal import token_stems

        index: dict[str, str] = {}
        for concept in self.concepts.values():
            labels = (
                [concept.preferred_label]
                + list(concept.synonyms)
                + list(concept.surface_forms)
            )
            for label in labels:
                key = normalizer.normalize(label)
                if key:
                    index[key] = concept.concept_id
                for stem in token_stems(label):
                    stem_key = normalizer.normalize(stem)
                    if stem_key and stem_key not in index:
                        index[stem_key] = concept.concept_id
        self._label_index = index
        LOGGER.info(
            "BusinessOntology index concepts=%d labels=%d",
            len(self.concepts),
            len(self._label_index),
        )

    def resolve(self, text: str, normalizer: OntologyNormalizer) -> str | None:
        """Resolve raw text to a concept id via the reverse index."""
        key = normalizer.normalize(text)
        if not key:
            return None
        return self._label_index.get(key)

    def resolve_normalized(self, normalized: str) -> str | None:
        """Resolve an already-normalized string."""
        return self._label_index.get(normalized) if normalized else None

    def parents_within(
        self, concept_id: str, max_depth: int
    ) -> set[str]:
        """Collect ancestor concept ids up to ``max_depth``."""
        found: set[str] = set()
        frontier = [concept_id]
        for _ in range(max(0, max_depth)):
            nxt: list[str] = []
            for cid in frontier:
                concept = self.concepts.get(cid)
                if concept is None:
                    continue
                for parent in concept.broader:
                    if parent not in found:
                        found.add(parent)
                        nxt.append(parent)
            frontier = nxt
            if not frontier:
                break
        return found

    def is_descendant(
        self, candidate: str, ancestor: str, max_depth: int
    ) -> bool:
        """Return True if ``candidate`` is under ``ancestor`` within depth."""
        return ancestor in self.parents_within(candidate, max_depth)

    def relation(
        self,
        query_concept: str,
        doc_concept: str,
        max_depth: int,
    ) -> str | None:
        """Best relation type between two concept ids (or None)."""
        if query_concept == doc_concept:
            return "exact"
        q = self.concepts.get(query_concept)
        d = self.concepts.get(doc_concept)
        if q is None or d is None:
            return None
        if doc_concept in q.synonyms or query_concept in d.synonyms:
            return "synonym"
        # Synonym lists are labels, not ids — check sibling via shared parent.
        if self.is_descendant(doc_concept, query_concept, max_depth):
            return "narrower"
        if self.is_descendant(query_concept, doc_concept, max_depth):
            return "broader"
        q_parents = self.parents_within(query_concept, max_depth)
        d_parents = self.parents_within(doc_concept, max_depth)
        if q_parents & d_parents:
            return "shared_parent"
        return None


def _concept_from_mapping(raw: dict[str, Any]) -> BusinessConcept:
    return BusinessConcept(
        concept_id=str(raw["concept_id"]),
        preferred_label=str(raw.get("preferred_label") or raw["concept_id"]),
        synonyms=[str(x) for x in (raw.get("synonyms") or [])],
        surface_forms=[str(x) for x in (raw.get("surface_forms") or [])],
        broader=[str(x) for x in (raw.get("broader") or [])],
        narrower=[str(x) for x in (raw.get("narrower") or [])],
        related=[str(x) for x in (raw.get("related") or [])],
    )


def business_ontology_from_data(data: Any) -> BusinessOntology:
    """Build an ontology from a query payload (list or ``{concepts: [...]}``).

    The business ontology is **not** stored server-side; clients pass concepts
    on each search / RAG request for query expansion and overlap scoring.

    Args:
        data: ``None``, concept list, or mapping with a ``concepts`` key.

    Returns:
        Populated :class:`BusinessOntology` (label index not yet built).
    """
    if data is None:
        return BusinessOntology([])
    if isinstance(data, BusinessOntology):
        return data
    if isinstance(data, dict) and "concepts" in data:
        rows = data.get("concepts") or []
    elif isinstance(data, list):
        rows = data
    elif isinstance(data, dict) and data.get("concept_id"):
        rows = [data]
    else:
        LOGGER.warning("Unrecognized business ontology payload type=%s", type(data))
        return BusinessOntology([])
    concepts = [
        _concept_from_mapping(row)
        for row in rows
        if isinstance(row, dict) and row.get("concept_id")
    ]
    return BusinessOntology(concepts)


def load_business_ontology(path: Path | str) -> BusinessOntology:
    """Load concepts from JSON / YAML file (tests / offline tooling only).

    Prefer :func:`business_ontology_from_data` for live query expansion.

    Args:
        path: File path.

    Returns:
        Populated :class:`BusinessOntology` (label index not yet built).
    """
    file_path = Path(path)
    if not file_path.is_file():
        LOGGER.warning("Business ontology missing: %s", file_path)
        return BusinessOntology([])
    text = file_path.read_text(encoding="utf-8")
    if file_path.suffix.lower() in {".yaml", ".yml"}:
        data = yaml.safe_load(text)
    else:
        data = json.loads(text)
    return business_ontology_from_data(data)
