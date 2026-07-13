# -*- coding: utf-8 -*-
"""Per-document ontology vocabulary derived from clustering and auto-labeling."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

FALLBACK_ENTITY_CLASS = "Entity"
METRIC_CLASS = "Metric"

_ALNUM_PARTS = re.compile(r"[A-Za-z0-9]+")
_CLASS_NAME = re.compile(r"^[A-Z][A-Za-z0-9]*$")
_PROPERTY_NAME = re.compile(r"^[a-z][A-Za-z0-9]*$")


def sanitize_rdf_class_name(label: str, *, fallback: str = "Entity") -> str:
    """Convert arbitrary text to a valid PascalCase Turtle class local name."""
    text = str(label).strip()
    if _CLASS_NAME.fullmatch(text):
        return text
    parts = _ALNUM_PARTS.findall(text)
    if not parts:
        return fallback
    name = "".join(part.capitalize() for part in parts)
    if name[0].isdigit():
        name = f"N{name}"
    return name


def sanitize_rdf_property_name(label: str, *, fallback: str = "relatedTo") -> str:
    """Convert arbitrary text to a valid camelCase Turtle property local name."""
    text = str(label).strip()
    if _PROPERTY_NAME.fullmatch(text):
        return text
    if _CLASS_NAME.fullmatch(text):
        return text[0].lower() + text[1:]
    parts = _ALNUM_PARTS.findall(text)
    if not parts:
        return fallback
    name = parts[0].lower() + "".join(part.capitalize() for part in parts[1:])
    if name[0].isdigit():
        name = f"n{name}"
    return name


def sanitize_rdf_local_name(
    label: str,
    *,
    fallback: str = "Entity",
    pascal: bool = True,
) -> str:
    """Backward-compatible wrapper for class/property local name sanitization."""
    if pascal:
        return sanitize_rdf_class_name(label, fallback=fallback)
    return sanitize_rdf_property_name(label, fallback=fallback)


def slugify_verb(value: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "_", str(value).lower()).strip("_")
    return slug or "entity"


def title_case_label(label: str) -> str:
    return sanitize_rdf_class_name(label, fallback=FALLBACK_ENTITY_CLASS)


def slug_to_predicate_name(slug: str) -> str:
    """Derive a predicate local name from a verb slug."""
    parts = [part for part in slug.split("_") if part]
    if not parts:
        parts = _ALNUM_PARTS.findall(slug)
    if not parts:
        return "relatedTo"
    return sanitize_rdf_property_name(
        "_".join(parts),
        fallback="relatedTo",
    )


@dataclass(frozen=True)
class OntologyVocabulary:
    """Per-document class and predicate vocabulary from clustering."""

    ner_class_map: dict[str, str] = field(default_factory=dict)
    node_classes: frozenset[str] = field(default_factory=frozenset)
    predicate_aliases: dict[str, str] = field(default_factory=dict)
    class_map: dict[str, str] = field(default_factory=dict)
    subject_class_map: dict[str, str] = field(default_factory=dict)
    object_class_map: dict[str, str] = field(default_factory=dict)

    @classmethod
    def empty(cls) -> OntologyVocabulary:
        """Return an empty vocabulary (no clustered labels yet)."""
        return cls()

    def class_for_ner_label(self, label: str | None) -> str:
        if not label:
            return FALLBACK_ENTITY_CLASS
        key = str(label).lower()
        mapped = self.ner_class_map.get(key, title_case_label(key))
        return self.canonical_class(mapped)

    def class_for_entity(self, text: str, *, role: str = "subject") -> str | None:
        key = str(text).strip().lower()
        if not key:
            return None
        if role == "object":
            mapped = self.object_class_map.get(key)
        else:
            mapped = self.subject_class_map.get(key)
        if mapped:
            return self.canonical_class(mapped)
        return None

    def canonical_class(self, class_name: str) -> str:
        mapped = self.class_map.get(class_name, class_name)
        return sanitize_rdf_class_name(mapped, fallback=FALLBACK_ENTITY_CLASS)

    def predicate_for_verb(self, verb: str) -> str:
        normalized = slugify_verb(verb)
        mapped = self.predicate_aliases.get(
            normalized,
            slug_to_predicate_name(normalized),
        )
        return sanitize_rdf_property_name(mapped, fallback="relatedTo")

    def is_node_class(self, class_name: str) -> bool:
        canonical = self.canonical_class(class_name)
        if canonical in {FALLBACK_ENTITY_CLASS, METRIC_CLASS}:
            return False
        if self.node_classes:
            return canonical in self.node_classes
        return True

    def to_report(self) -> dict[str, object]:
        return {
            "ner_class_map": dict(self.ner_class_map),
            "node_classes": sorted(self.node_classes),
            "predicate_aliases": dict(self.predicate_aliases),
            "class_map": dict(self.class_map),
            "subject_class_map": dict(self.subject_class_map),
            "object_class_map": dict(self.object_class_map),
        }
