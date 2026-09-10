"""Title: Ontology graph expansion for retrieval.

Application-side expansion (parents / children / related / predicate walk)
before Vespa filtering. Avoids per-hit graph traversal inside YQL.

Author: Eric Blaudez

Copyright (c) 2026 Thales
Licensed under the MIT License.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from thot.ontology.identity import PRED_BROADER, PRED_NARROWER, PRED_RELATED
from thot.ontology.model import Ontology


@dataclass(frozen=True)
class ExpansionSpec:
    """Configurable neighborhood walk around seed concept IDs.

    Example:
        >>> from thot.ontology.expansion import ExpansionSpec
        >>> ExpansionSpec(include_children=True).include_children
        True
    """

    include_children: bool = False
    include_parents: bool = False
    include_related: bool = False
    predicates: tuple[str, ...] = ()
    max_depth: int = 1
    max_ids: int = 32


@dataclass
class ExpansionResult:
    """Seed IDs plus expanded neighbors (order preserved, seeds first).

    Example:
        >>> from thot.ontology.expansion import ExpansionResult
        >>> ExpansionResult(concept_ids=['a'], seed_ids=['a']).concept_ids
        ['a']
    """

    concept_ids: list[str]
    seed_ids: list[str] = field(default_factory=list)
    expanded_ids: list[str] = field(default_factory=list)


def expand_concept_ids(
    seed_ids: list[str],
    ontology: Ontology | None,
    spec: ExpansionSpec | None = None,
) -> ExpansionResult:
    """Expand ``seed_ids`` using concept links and optional predicates.

    When ``ontology`` is empty/None, returns the seeds unchanged (capped).

    Example:
        >>> from thot.ontology.expansion import ExpansionSpec, expand_concept_ids
        >>> from thot.ontology.model import Ontology, OntologyConcept
        >>> ont = Ontology()
        >>> ont.add_concept(OntologyConcept(
        ...     'k8s', preferred_label='Kubernetes', narrower_ids=['pod'],
        ... ))
        >>> ont.add_concept(OntologyConcept('pod', preferred_label='Pod'))
        >>> result = expand_concept_ids(
        ...     ['k8s'], ont, ExpansionSpec(include_children=True, max_depth=1),
        ... )
        >>> 'pod' in result.concept_ids
        True
    """
    spec = spec or ExpansionSpec()
    seeds = [cid.strip() for cid in seed_ids if cid and str(cid).strip()]
    cap = max(1, int(spec.max_ids))
    if not seeds:
        return ExpansionResult(concept_ids=[], seed_ids=[], expanded_ids=[])
    if ontology is None or not ontology.concepts:
        clipped = seeds[:cap]
        return ExpansionResult(
            concept_ids=clipped, seed_ids=clipped, expanded_ids=[]
        )

    seen: set[str] = set()
    ordered: list[str] = []

    def _add(cid: str) -> None:
        if not cid or cid in seen or len(ordered) >= cap:
            return
        seen.add(cid)
        ordered.append(cid)

    for cid in seeds:
        _add(cid)
    seed_set = set(ordered)

    depth = max(0, int(spec.max_depth))
    frontier = list(ordered)
    pred_set = {p.strip() for p in spec.predicates if p and str(p).strip()}

    for _ in range(depth):
        nxt: list[str] = []
        for cid in frontier:
            if len(ordered) >= cap:
                break
            concept = ontology.get(cid)
            neighbors: list[str] = []
            if concept is not None:
                if spec.include_parents:
                    neighbors.extend(concept.broader_ids or concept.parent_ids)
                if spec.include_children:
                    neighbors.extend(concept.narrower_ids)
                if spec.include_related:
                    neighbors.extend(concept.related_ids)
            if (
                pred_set
                or spec.include_parents
                or spec.include_children
                or spec.include_related
            ):
                for rel in ontology.relations:
                    follow = False
                    if rel.subject_id == cid:
                        if (
                            spec.include_children
                            and rel.predicate_id == PRED_NARROWER
                        ):
                            follow = True
                        if (
                            spec.include_parents
                            and rel.predicate_id == PRED_BROADER
                        ):
                            follow = True
                        if (
                            spec.include_related
                            and rel.predicate_id == PRED_RELATED
                        ):
                            follow = True
                        if rel.predicate_id in pred_set:
                            follow = True
                        if follow:
                            neighbors.append(rel.object_id)
                    if rel.object_id == cid:
                        if (
                            spec.include_parents
                            and rel.predicate_id == PRED_NARROWER
                        ):
                            neighbors.append(rel.subject_id)
                        if (
                            spec.include_children
                            and rel.predicate_id == PRED_BROADER
                        ):
                            neighbors.append(rel.subject_id)
                        if (
                            spec.include_related
                            and rel.predicate_id == PRED_RELATED
                        ):
                            neighbors.append(rel.subject_id)
                        if rel.predicate_id in pred_set:
                            neighbors.append(rel.subject_id)
            for nid in neighbors:
                before = len(ordered)
                _add(nid)
                if len(ordered) > before:
                    nxt.append(nid)
                if len(ordered) >= cap:
                    break
        frontier = nxt
        if not frontier:
            break

    expanded = [cid for cid in ordered if cid not in seed_set]
    return ExpansionResult(
        concept_ids=ordered,
        seed_ids=[cid for cid in ordered if cid in seed_set],
        expanded_ids=expanded,
    )


def overlap_score(
    *,
    hit_concept_ids: list[str],
    hit_relation_keys: list[str],
    query_concept_ids: list[str],
    query_relation_keys: list[str],
    concept_weight: float = 0.15,
    relation_weight: float = 0.10,
) -> float:
    """Configurable concept/relation overlap in ``[0, concept_w + relation_w]``.

    Example:
        >>> from thot.ontology.expansion import overlap_score
        >>> overlap_score(
        ...     hit_concept_ids=['a', 'b'],
        ...     hit_relation_keys=['a|pred:has_value|b'],
        ...     query_concept_ids=['a'],
        ...     query_relation_keys=['a|pred:has_value|b'],
        ...     concept_weight=1.0,
        ...     relation_weight=1.0,
        ... )
        2.0
    """
    q_ids = {str(x).casefold() for x in query_concept_ids if x}
    h_ids = {str(x).casefold() for x in hit_concept_ids if x}
    concept_s = 0.0
    if q_ids:
        concept_s = len(q_ids & h_ids) / max(len(q_ids), 1)
    q_rel = {str(x) for x in query_relation_keys if x}
    h_rel = {str(x) for x in hit_relation_keys if x}
    relation_s = 0.0
    if q_rel:
        relation_s = len(q_rel & h_rel) / max(len(q_rel), 1)
    return (concept_s * float(concept_weight)) + (
        relation_s * float(relation_weight)
    )
