"""Title: Canonical ontology layer.

Vespa-independent concepts, relations, JSON structural IDs, SHACL export,
and retrieval expansion. See ``docs/architecture/ontology.md``.

Author: Eric Blaudez

Copyright (c) 2026 Thales
Licensed under the MIT License.
"""

from thot.ontology.expansion import ExpansionSpec, expand_concept_ids
from thot.ontology.identity import (
    PRED_HAS_VALUE,
    json_attribute_id,
    json_value_id,
    predicate_id,
    preserve_or_mint,
)
from thot.ontology.json_concepts import extract_json_concepts
from thot.ontology.model import (
    Ontology,
    OntologyConcept,
    OntologyRelation,
    ProvenanceKind,
)
from thot.ontology.service import ChunkOntologyEnrichment, OntologyService

__all__ = [
    "ChunkOntologyEnrichment",
    "ExpansionSpec",
    "Ontology",
    "OntologyConcept",
    "OntologyRelation",
    "OntologyService",
    "PRED_HAS_VALUE",
    "ProvenanceKind",
    "expand_concept_ids",
    "extract_json_concepts",
    "json_attribute_id",
    "json_value_id",
    "predicate_id",
    "preserve_or_mint",
]
