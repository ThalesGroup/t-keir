"""Title: JSON structural ontology concepts.

Turn JSON attribute paths and primitive values into stable concept IDs
and ``has_value`` relations. Narrative fields and long free-text blobs
are skipped. Nested objects, arrays, and primitives are supported.

Author: Eric Blaudez

Copyright (c) 2026 Thales
Licensed under the MIT License.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from thot.ontology.identity import (
    PRED_HAS_VALUE,
    json_attribute_id,
    json_value_id,
    legacy_json_value_id,
)
from thot.ontology.model import (
    Ontology,
    OntologyConcept,
    OntologyRelation,
    Provenance,
    ProvenanceKind,
)

# Same skip-set as ingest JSON records (narrative, not structure).
NARRATIVE_KEYS = frozenset(
    {
        "title",
        "text",
        "body",
        "content",
        "summary",
        "abstract",
        "description",
    }
)
_ID_KEYS = frozenset({"doc_id", "id", "document_id", "uid", "_id"})
_MAX_PATH_DEPTH = 8
_MAX_VALUE_LEN = 64
_MAX_FREE_TEXT = 64


def _scalar_to_str(value: Any) -> str:
    """Convert a JSON scalar to a compact display string.

    Example:
        >>> from thot.ontology.json_concepts import _scalar_to_str
        >>> _scalar_to_str(True)
        'true'
        >>> _scalar_to_str(1.5)
        '1.5'
    """
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, float):
        return f"{value:g}"
    return str(value).strip()


def _skip_value(text: str) -> bool:
    """True when a scalar should not become a concept.

    Example:
        >>> from thot.ontology.json_concepts import _skip_value
        >>> _skip_value("")
        True
        >>> _skip_value("France")
        False
        >>> _skip_value("a very long free text blob that should not be a concept value at all")
        True
    """
    if not text:
        return True
    if len(text) > 120:
        return True
    if len(text) > _MAX_FREE_TEXT and " " in text:
        return True
    return False


def _is_narrative_or_id(key: str) -> bool:
    """Skip title/text/id keys.

    Example:
        >>> from thot.ontology.json_concepts import _is_narrative_or_id
        >>> _is_narrative_or_id("title")
        True
        >>> _is_narrative_or_id("country")
        False
    """
    folded = (key or "").casefold()
    return folded in NARRATIVE_KEYS or folded in _ID_KEYS


@dataclass
class JsonConceptExtraction:
    """Attribute concepts, value concepts, relations, and legacy aliases.

    Example:
        >>> from thot.ontology.json_concepts import JsonConceptExtraction
        >>> JsonConceptExtraction().chunk_ids()
        []
    """

    ontology: Ontology = field(default_factory=Ontology)
    legacy_ids: list[str] = field(default_factory=list)

    def chunk_ids(self) -> list[str]:
        """IDs to attach to a chunk (canonical + legacy, de-duplicated).

        Example:
            >>> from thot.ontology.json_concepts import extract_json_concepts
            >>> ids = extract_json_concepts({'country': 'France'}).chunk_ids()
            >>> any(i.startswith('json:attribute:') for i in ids)
            True
        """
        out: list[str] = []
        seen: set[str] = set()
        for cid in list(self.ontology.concepts) + list(self.legacy_ids):
            key = cid.casefold()
            if not cid or key in seen:
                continue
            seen.add(key)
            out.append(cid)
        return out


def extract_json_concepts(
    record: dict[str, Any],
    *,
    source_ref: str = "",
    chunk_id: str = "",
    max_concepts: int = 64,
    prefix: str = "",
) -> JsonConceptExtraction:
    """Walk a JSON object and mint attribute / value concepts + has_value edges.

    Example:
        >>> from thot.ontology.json_concepts import extract_json_concepts
        >>> ext = extract_json_concepts({'customer': {'country': 'France'}})
        >>> 'json:attribute:customer.country' in ext.ontology.concepts
        True
        >>> any(c.startswith('json:value:customer.country=') for c in ext.ontology.concepts)
        True
        >>> ext.ontology.relations[0].predicate_id
        'pred:has_value'
        >>> any('COUNTRY:France' in x or 'FRANCE' in x.upper() for x in ext.legacy_ids)
        True
    """
    result = JsonConceptExtraction()
    provenance = Provenance(
        kind=ProvenanceKind.JSON_EXTRACTED,
        source_ref=source_ref,
        chunk_id=chunk_id,
    )

    def _add_pair(path: str, value: Any) -> None:
        if len(result.ontology.concepts) >= max_concepts:
            return
        text = _scalar_to_str(value)
        if _skip_value(text) or len(text) > _MAX_VALUE_LEN:
            return
        attr_id = json_attribute_id(path)
        val_id = json_value_id(path, text)
        result.ontology.add_concept(
            OntologyConcept(
                concept_id=attr_id,
                preferred_label=path,
                concept_type="json_attribute",
                provenance=provenance,
            )
        )
        result.ontology.add_concept(
            OntologyConcept(
                concept_id=val_id,
                preferred_label=text,
                concept_type="json_value",
                aliases=[f"{path}={text}"],
                provenance=provenance,
            )
        )
        result.ontology.add_relation(
            OntologyRelation(
                subject_id=attr_id,
                predicate_id=PRED_HAS_VALUE,
                object_id=val_id,
                provenance=provenance,
            )
        )
        legacy = legacy_json_value_id(path, text)
        if legacy:
            result.legacy_ids.append(legacy)

    def _walk(node: Any, path: str, depth: int) -> None:
        if len(result.ontology.concepts) >= max_concepts:
            return
        if depth > _MAX_PATH_DEPTH:
            return
        if isinstance(node, dict):
            for key, child in node.items():
                key_s = str(key)
                if _is_narrative_or_id(key_s):
                    continue
                leaf = f"{path}.{key_s}" if path else key_s
                _walk(child, leaf, depth + 1)
            return
        if isinstance(node, list):
            for child in node:
                if isinstance(child, (dict, list)):
                    _walk(child, path, depth + 1)
                else:
                    _add_pair(path, child)
            return
        _add_pair(path, node)

    _walk(record, prefix, 0)
    return result
