"""Title: Canonical ontology domain model.

Vespa-independent concepts, relations, properties, constraints, and
provenance. Expert (business) ontology is the authoritative seed; document
and JSON extractions extend it without overwriting expert rows.

Author: Eric Blaudez

Copyright (c) 2026 Thales
Licensed under the MIT License.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from thot.ontology.identity import (
    PRED_BROADER,
    PRED_NARROWER,
    PRED_RELATED,
    predicate_id,
    preserve_or_mint,
)


class ProvenanceKind(str, Enum):
    """Where a concept or relation came from.

    Example:
        >>> from thot.ontology.model import ProvenanceKind
        >>> ProvenanceKind.EXPERT_DEFINED.value
        'expert_defined'
    """

    EXPERT_DEFINED = "expert_defined"
    DOCUMENT_EXTRACTED = "document_extracted"
    JSON_EXTRACTED = "json_extracted"
    INFERRED = "inferred"


@dataclass
class Provenance:
    """Attribution for one concept or relation.

    Example:
        >>> from thot.ontology.model import Provenance, ProvenanceKind
        >>> Provenance(kind=ProvenanceKind.JSON_EXTRACTED).kind.value
        'json_extracted'
    """

    kind: ProvenanceKind
    source_ref: str = ""
    chunk_id: str = ""
    confidence: float = 1.0

    def to_dict(self) -> dict[str, Any]:
        """Serialize provenance.

        Example:
            >>> from thot.ontology.model import Provenance, ProvenanceKind
            >>> Provenance(kind=ProvenanceKind.EXPERT_DEFINED).to_dict()['kind']
            'expert_defined'
        """
        return {
            "kind": self.kind.value,
            "source_ref": self.source_ref,
            "chunk_id": self.chunk_id,
            "confidence": float(self.confidence),
        }


@dataclass
class OntologyProperty:
    """Named property on a concept (domain/range/cardinality for SHACL).

    Example:
        >>> from thot.ontology.model import OntologyProperty
        >>> OntologyProperty(name='country', value_type='string').name
        'country'
    """

    name: str
    value_type: str = "string"
    domain_ids: list[str] = field(default_factory=list)
    range_ids: list[str] = field(default_factory=list)
    min_count: int | None = None
    max_count: int | None = None

    def to_dict(self) -> dict[str, Any]:
        """Serialize the property.

        Example:
            >>> from thot.ontology.model import OntologyProperty
            >>> OntologyProperty(name='x').to_dict()['name']
            'x'
        """
        return {
            "name": self.name,
            "value_type": self.value_type,
            "domain_ids": list(self.domain_ids),
            "range_ids": list(self.range_ids),
            "min_count": self.min_count,
            "max_count": self.max_count,
        }


@dataclass
class OntologyConstraint:
    """Generic constraint later compiled to SHACL.

    Example:
        >>> from thot.ontology.model import OntologyConstraint
        >>> OntologyConstraint(name='required', target_id='c1').name
        'required'
    """

    name: str
    target_id: str
    constraint_type: str = "property"
    expression: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Serialize the constraint.

        Example:
            >>> from thot.ontology.model import OntologyConstraint
            >>> OntologyConstraint(name='n', target_id='c').to_dict()['target_id']
            'c'
        """
        return {
            "name": self.name,
            "target_id": self.target_id,
            "constraint_type": self.constraint_type,
            "expression": self.expression,
        }


@dataclass
class OntologyConcept:
    """First-class ontology entity. ``concept_id`` is the only identifier.

    Example:
        >>> from thot.ontology.model import OntologyConcept, Provenance, ProvenanceKind
        >>> OntologyConcept('C1', preferred_label='Kubernetes').concept_id
        'C1'
    """

    concept_id: str
    preferred_label: str = ""
    concept_type: str = "concept"
    aliases: list[str] = field(default_factory=list)
    definition: str = ""
    parent_ids: list[str] = field(default_factory=list)
    broader_ids: list[str] = field(default_factory=list)
    narrower_ids: list[str] = field(default_factory=list)
    related_ids: list[str] = field(default_factory=list)
    properties: list[OntologyProperty] = field(default_factory=list)
    provenance: Provenance = field(
        default_factory=lambda: Provenance(
            kind=ProvenanceKind.DOCUMENT_EXTRACTED
        )
    )

    def all_labels(self) -> list[str]:
        """Preferred label plus aliases (non-empty, de-duplicated).

        Example:
            >>> from thot.ontology.model import OntologyConcept
            >>> OntologyConcept('C1', preferred_label='K8s', aliases=['Kubernetes']).all_labels()
            ['K8s', 'Kubernetes']
        """
        out: list[str] = []
        seen: set[str] = set()
        for lab in [self.preferred_label, *self.aliases]:
            text = (lab or "").strip()
            if not text:
                continue
            key = text.casefold()
            if key in seen:
                continue
            seen.add(key)
            out.append(text)
        return out

    def to_dict(self) -> dict[str, Any]:
        """Serialize the concept (export / Vespa adapter).

        Example:
            >>> from thot.ontology.model import OntologyConcept
            >>> OntologyConcept('C1', preferred_label='K8s').to_dict()['id']
            'C1'
        """
        return {
            "id": self.concept_id,
            "type": self.concept_type,
            "label": self.preferred_label or self.concept_id,
            "aliases": list(self.aliases),
            "definition": self.definition,
            "parent_ids": list(self.parent_ids),
            "broader_ids": list(self.broader_ids),
            "narrower_ids": list(self.narrower_ids),
            "related_ids": list(self.related_ids),
            "properties": [prop.to_dict() for prop in self.properties],
            "provenance": self.provenance.to_dict(),
        }


@dataclass
class OntologyRelation:
    """Typed assertion between two concept IDs.

    Example:
        >>> from thot.ontology.model import OntologyRelation
        >>> OntologyRelation('a', 'pred:has_value', 'b').predicate_id
        'pred:has_value'
    """

    subject_id: str
    predicate_id: str
    object_id: str
    confidence: float = 1.0
    provenance: Provenance = field(
        default_factory=lambda: Provenance(
            kind=ProvenanceKind.DOCUMENT_EXTRACTED
        )
    )

    def key(self) -> str:
        """Compact identity for de-duplication.

        Example:
            >>> from thot.ontology.model import OntologyRelation
            >>> OntologyRelation('a', 'pred:has_value', 'b').key()
            'a|pred:has_value|b'
        """
        from thot.ontology.identity import relation_key

        return relation_key(self.subject_id, self.predicate_id, self.object_id)

    def to_dict(self) -> dict[str, Any]:
        """Serialize the relation.

        Example:
            >>> from thot.ontology.model import OntologyRelation
            >>> OntologyRelation('a', 'pred:has_value', 'b').to_dict()['subject']
            'a'
        """
        return {
            "subject": self.subject_id,
            "predicate": self.predicate_id,
            "object": self.object_id,
            "confidence": float(self.confidence),
            "provenance": self.provenance.to_dict(),
        }

    def matches(
        self,
        *,
        subject_id: str | None = None,
        predicate_id: str | None = None,
        object_id: str | None = None,
        mode: str = "partial",
    ) -> bool:
        """Exact (all provided slots) or partial (any provided slot) match.

        ``mode='exact'`` requires every non-None slot to match and at least
        one slot to be provided. ``mode='partial'`` is the same for the
        provided slots (callers decide how many slots to fill).

        Example:
            >>> from thot.ontology.model import OntologyRelation
            >>> rel = OntologyRelation('a', 'pred:has_value', 'b')
            >>> rel.matches(subject_id='a', mode='partial')
            True
            >>> rel.matches(subject_id='a', object_id='z', mode='exact')
            False
        """
        slots = (
            (subject_id, self.subject_id),
            (predicate_id, self.predicate_id),
            (object_id, self.object_id),
        )
        provided = [(want, have) for want, have in slots if want]
        if not provided:
            return False
        if mode == "exact":
            return all(want == have for want, have in provided) and len(
                provided
            ) == sum(1 for want, _ in slots if want)
        return all(want == have for want, have in provided)


@dataclass
class Ontology:
    """Concept graph: nodes = concepts, edges = relations.

    Example:
        >>> from thot.ontology.model import Ontology, OntologyConcept
        >>> Ontology(concepts={'C1': OntologyConcept('C1')}).get('C1').concept_id
        'C1'
    """

    concepts: dict[str, OntologyConcept] = field(default_factory=dict)
    relations: list[OntologyRelation] = field(default_factory=list)
    constraints: list[OntologyConstraint] = field(default_factory=list)

    def get(self, concept_id: str) -> OntologyConcept | None:
        """Lookup by stable ID.

        Example:
            >>> from thot.ontology.model import Ontology
            >>> Ontology().get('missing') is None
            True
        """
        return self.concepts.get(concept_id)

    def add_concept(
        self, concept: OntologyConcept, *, overwrite_expert: bool = False
    ) -> None:
        """Insert or merge a concept. Expert rows are not overwritten.

        Example:
            >>> from thot.ontology.model import (
            ...     Ontology, OntologyConcept, Provenance, ProvenanceKind,
            ... )
            >>> ont = Ontology()
            >>> ont.add_concept(OntologyConcept(
            ...     'C1', preferred_label='K8s',
            ...     provenance=Provenance(kind=ProvenanceKind.EXPERT_DEFINED),
            ... ))
            >>> ont.add_concept(OntologyConcept('C1', preferred_label='Other'))
            >>> ont.get('C1').preferred_label
            'K8s'
        """
        existing = self.concepts.get(concept.concept_id)
        if existing is None:
            self.concepts[concept.concept_id] = concept
            return
        if (
            existing.provenance.kind is ProvenanceKind.EXPERT_DEFINED
            and not overwrite_expert
        ):
            _merge_labels(existing, concept)
            _merge_links(existing, concept)
            return
        _merge_labels(existing, concept)
        _merge_links(existing, concept)
        if not existing.definition and concept.definition:
            existing.definition = concept.definition
        if not existing.concept_type or existing.concept_type == "concept":
            existing.concept_type = concept.concept_type

    def add_relation(self, relation: OntologyRelation) -> None:
        """Append a relation when the compact key is new.

        Example:
            >>> from thot.ontology.model import Ontology, OntologyRelation
            >>> ont = Ontology()
            >>> ont.add_relation(OntologyRelation('a', 'pred:has_value', 'b'))
            >>> ont.add_relation(OntologyRelation('a', 'pred:has_value', 'b'))
            >>> len(ont.relations)
            1
        """
        key = relation.key()
        if any(existing.key() == key for existing in self.relations):
            return
        self.relations.append(relation)

    def extend(self, other: Ontology) -> Ontology:
        """Return a new ontology: ``self`` (expert seed) plus ``other``.

        Example:
            >>> from thot.ontology.model import (
            ...     Ontology, OntologyConcept, Provenance, ProvenanceKind,
            ... )
            >>> expert = Ontology()
            >>> expert.add_concept(OntologyConcept(
            ...     'C1', preferred_label='K8s',
            ...     provenance=Provenance(kind=ProvenanceKind.EXPERT_DEFINED),
            ... ))
            >>> extra = Ontology()
            >>> extra.add_concept(OntologyConcept('C2', preferred_label='Pod'))
            >>> merged = expert.extend(extra)
            >>> sorted(merged.concepts)
            ['C1', 'C2']
        """
        merged = Ontology()
        for concept in self.concepts.values():
            merged.add_concept(concept)
        for relation in self.relations:
            merged.add_relation(relation)
        merged.constraints.extend(self.constraints)
        for concept in other.concepts.values():
            merged.add_concept(concept)
        for relation in other.relations:
            merged.add_relation(relation)
        merged.constraints.extend(other.constraints)
        return merged

    def to_export_dict(self) -> dict[str, Any]:
        """Complete ontology as concepts + relations (corpus export shape).

        Example:
            >>> from thot.ontology.model import Ontology, OntologyConcept
            >>> payload = Ontology(concepts={'C1': OntologyConcept('C1')}).to_export_dict()
            >>> payload['concepts'][0]['id']
            'C1'
        """
        return {
            "concepts": [c.to_dict() for c in self.concepts.values()],
            "relations": [r.to_dict() for r in self.relations],
            "constraints": [c.to_dict() for c in self.constraints],
        }

    @classmethod
    def from_business_payload(cls, payload: dict[str, Any] | None) -> Ontology:
        """Build from ``business_ontology.yaml`` / request concepts list.

        Example:
            >>> from thot.ontology.model import Ontology, ProvenanceKind
            >>> ont = Ontology.from_business_payload(
            ...     {'concepts': [{'concept_id': 'C1', 'preferred_label': 'K8s'}]}
            ... )
            >>> ont.get('C1').provenance.kind is ProvenanceKind.EXPERT_DEFINED
            True
        """
        ont = cls()
        if not payload:
            return ont
        rows = (
            payload.get("concepts") if isinstance(payload, dict) else payload
        )
        if not isinstance(rows, list):
            return ont
        for raw in rows:
            if not isinstance(raw, dict):
                continue
            cid = str(raw.get("concept_id") or "").strip()
            if not cid:
                continue
            cid = preserve_or_mint(cid)
            broader = [str(x).strip() for x in raw.get("broader") or [] if x]
            narrower = [str(x).strip() for x in raw.get("narrower") or [] if x]
            related = [str(x).strip() for x in raw.get("related") or [] if x]
            aliases = [
                str(x).strip()
                for x in list(raw.get("synonyms") or []) + list(
                    raw.get("surface_forms") or []
                )
                if x
            ]
            concept = OntologyConcept(
                concept_id=cid,
                preferred_label=str(raw.get("preferred_label") or cid).strip(),
                concept_type=str(raw.get("concept_type") or "concept"),
                aliases=aliases,
                definition=str(raw.get("definition") or "").strip(),
                parent_ids=list(broader),
                broader_ids=broader,
                narrower_ids=narrower,
                related_ids=related,
                provenance=Provenance(kind=ProvenanceKind.EXPERT_DEFINED),
            )
            ont.add_concept(concept)
            for parent in broader:
                ont.add_relation(
                    OntologyRelation(
                        cid,
                        PRED_BROADER,
                        parent,
                        provenance=Provenance(
                            kind=ProvenanceKind.EXPERT_DEFINED
                        ),
                    )
                )
            for child in narrower:
                ont.add_relation(
                    OntologyRelation(
                        cid,
                        PRED_NARROWER,
                        child,
                        provenance=Provenance(
                            kind=ProvenanceKind.EXPERT_DEFINED
                        ),
                    )
                )
            for other in related:
                ont.add_relation(
                    OntologyRelation(
                        cid,
                        PRED_RELATED,
                        other,
                        provenance=Provenance(
                            kind=ProvenanceKind.EXPERT_DEFINED
                        ),
                    )
                )
        return ont


def _merge_labels(
    existing: OntologyConcept, incoming: OntologyConcept
) -> None:
    """Union aliases; keep expert preferred label.

    Example:
        >>> from thot.ontology.model import OntologyConcept
        >>> a = OntologyConcept('C1', preferred_label='K8s')
        >>> _merge_labels(a, OntologyConcept('C1', aliases=['Kubernetes']))
        >>> 'Kubernetes' in a.aliases
        True
    """
    seen = {lab.casefold() for lab in existing.all_labels()}
    for lab in incoming.all_labels():
        if lab.casefold() in seen:
            continue
        seen.add(lab.casefold())
        if lab != existing.preferred_label:
            existing.aliases.append(lab)


def _merge_links(existing: OntologyConcept, incoming: OntologyConcept) -> None:
    """Union hierarchical / related ids.

    Example:
        >>> from thot.ontology.model import OntologyConcept
        >>> a = OntologyConcept('C1', broader_ids=['P'])
        >>> _merge_links(a, OntologyConcept('C1', related_ids=['R']))
        >>> a.related_ids
        ['R']
    """

    def _extend(dst: list[str], src: list[str]) -> None:
        have = {x.casefold() for x in dst}
        for item in src:
            key = item.casefold()
            if not item or key in have:
                continue
            have.add(key)
            dst.append(item)

    _extend(existing.parent_ids, incoming.parent_ids)
    _extend(existing.broader_ids, incoming.broader_ids)
    _extend(existing.narrower_ids, incoming.narrower_ids)
    _extend(existing.related_ids, incoming.related_ids)


def label_index(ontology: Ontology) -> dict[str, str]:
    """Normalized label / alias → concept_id (first wins, expert preferred).

    Example:
        >>> from thot.ontology.model import Ontology, OntologyConcept, label_index
        >>> idx = label_index(Ontology(concepts={
        ...     'C1': OntologyConcept('C1', preferred_label='Kubernetes'),
        ... }))
        >>> idx['kubernetes']
        'C1'
    """
    index: dict[str, str] = {}
    for concept in ontology.concepts.values():
        for lab in concept.all_labels():
            key = lab.casefold().strip()
            if key and key not in index:
                index[key] = concept.concept_id
        cid_key = concept.concept_id.casefold()
        index.setdefault(cid_key, concept.concept_id)
    return index


def map_label(
    label: str,
    ontology: Ontology | None,
    *,
    index: dict[str, str] | None = None,
) -> str | None:
    """Resolve a surface string to an expert/extended concept ID.

    Example:
        >>> from thot.ontology.model import Ontology, OntologyConcept, map_label
        >>> ont = Ontology(concepts={'C1': OntologyConcept('C1', preferred_label='Kubernetes')})
        >>> map_label('kubernetes', ont)
        'C1'
        >>> map_label('unknown-xyz', ont) is None
        True
    """
    text = (label or "").strip()
    if not text or ontology is None or not ontology.concepts:
        return None
    table = index if index is not None else label_index(ontology)
    hit = table.get(text.casefold())
    if hit:
        return hit
    minted = preserve_or_mint(text)
    if minted in ontology.concepts:
        return minted
    return None


def relation_predicate(raw: str) -> str:
    """Public wrapper around :func:`thot.ontology.identity.predicate_id`.

    Example:
        >>> from thot.ontology.model import relation_predicate
        >>> relation_predicate('implements')
        'pred:implements'
    """
    return predicate_id(raw)
