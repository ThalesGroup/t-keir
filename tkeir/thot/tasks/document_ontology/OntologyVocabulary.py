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
    """Convert arbitrary text to a valid PascalCase Turtle class local name.

    Example:
        >>> sanitize_rdf_class_name('hello world')
        'HelloWorld'
        >>> sanitize_rdf_class_name('Organization')
        'Organization'
        >>> sanitize_rdf_class_name('mandarin.[7')
        'Mandarin7'
    """
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


def sanitize_rdf_property_name(
    label: str, *, fallback: str = "relatedTo"
) -> str:
    """Convert arbitrary text to a valid camelCase Turtle property local name.

    Example:
        >>> sanitize_rdf_property_name('can-speak!')
        'canSpeak'
        >>> sanitize_rdf_property_name('relatedTo')
        'relatedTo'
    """
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
    """Backward-compatible wrapper for class/property local name sanitization.

    Example:
        >>> sanitize_rdf_local_name('hello world')
        'HelloWorld'
        >>> sanitize_rdf_local_name('can-speak!', pascal=False)
        'canSpeak'
    """
    if pascal:
        return sanitize_rdf_class_name(label, fallback=fallback)
    return sanitize_rdf_property_name(label, fallback=fallback)


def slugify_verb(value: str) -> str:
    """Normalize a verb phrase to a lowercase slug.

    Example:
        >>> slugify_verb('Launched By')
        'launched_by'
        >>> slugify_verb('')
        'entity'
    """
    slug = re.sub(r"[^a-zA-Z0-9]+", "_", str(value).lower()).strip("_")
    return slug or "entity"


def title_case_label(label: str) -> str:
    """Convert a label to a PascalCase class name.

    Example:
        >>> title_case_label('organization')
        'Organization'
    """
    return sanitize_rdf_class_name(label, fallback=FALLBACK_ENTITY_CLASS)


def slug_to_predicate_name(slug: str) -> str:
    """Derive a predicate local name from a verb slug.

    Example:
        >>> slug_to_predicate_name('launched_by')
        'launchedBy'
        >>> slug_to_predicate_name('')
        'relatedTo'
    """
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
        """Return an empty vocabulary (no clustered labels yet).

        Example:
            >>> OntologyVocabulary.empty().ner_class_map
            {}
        """
        return cls()

    def class_for_ner_label(self, label: str | None) -> str:
        """Map a NER label to a canonical RDF class name.

        Example:
            >>> OntologyVocabulary.empty().class_for_ner_label(None)
            'Entity'
            >>> OntologyVocabulary.empty().class_for_ner_label('organization')
            'Organization'
            >>> vocab = OntologyVocabulary(
            ...     ner_class_map={'org': 'Company'},
            ...     class_map={'Company': 'Corporation'},
            ... )
            >>> vocab.class_for_ner_label('org')
            'Corporation'
        """
        if not label:
            return FALLBACK_ENTITY_CLASS
        key = str(label).lower()
        mapped = self.ner_class_map.get(key, title_case_label(key))
        return self.canonical_class(mapped)

    def class_for_entity(
        self, text: str, *, role: str = "subject"
    ) -> str | None:
        """Look up a canonical class for an entity mention by role.

        Example:
            >>> OntologyVocabulary.empty().class_for_entity('')
            >>> vocab = OntologyVocabulary(
            ...     subject_class_map={'acme': 'Organization'},
            ...     object_class_map={'widget': 'Product'},
            ... )
            >>> vocab.class_for_entity('ACME')
            'Organization'
            >>> vocab.class_for_entity('Widget', role='object')
            'Product'
        """
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
        """Resolve class aliases and sanitize to a valid RDF class name.

        Example:
            >>> vocab = OntologyVocabulary(class_map={'Company': 'Corporation'})
            >>> vocab.canonical_class('Company')
            'Corporation'
        """
        mapped = self.class_map.get(class_name, class_name)
        return sanitize_rdf_class_name(mapped, fallback=FALLBACK_ENTITY_CLASS)

    def predicate_for_verb(self, verb: str) -> str:
        """Map a verb to a canonical RDF predicate local name.

        Example:
            >>> OntologyVocabulary.empty().predicate_for_verb('launched by')
            'launchedBy'
            >>> vocab = OntologyVocabulary(
            ...     predicate_aliases={'launched': 'founded'},
            ... )
            >>> vocab.predicate_for_verb('Launched')
            'founded'
        """
        normalized = slugify_verb(verb)
        mapped = self.predicate_aliases.get(
            normalized,
            slug_to_predicate_name(normalized),
        )
        return sanitize_rdf_property_name(mapped, fallback="relatedTo")

    def is_node_class(self, class_name: str) -> bool:
        """Return whether a class represents a concrete graph node type.

        Example:
            >>> vocab = OntologyVocabulary(node_classes=frozenset({'Organization'}))
            >>> vocab.is_node_class('Organization')
            True
            >>> vocab.is_node_class('Entity')
            False
            >>> OntologyVocabulary.empty().is_node_class('Foo')
            True
        """
        canonical = self.canonical_class(class_name)
        if canonical in {FALLBACK_ENTITY_CLASS, METRIC_CLASS}:
            return False
        if self.node_classes:
            return canonical in self.node_classes
        return True

    def to_report(self) -> dict[str, object]:
        """Serialize vocabulary mappings for reporting and debugging.

        Example:
            >>> vocab = OntologyVocabulary(
            ...     ner_class_map={'org': 'Company'},
            ...     node_classes=frozenset({'Company'}),
            ... )
            >>> sorted(vocab.to_report())
            ['class_map', 'ner_class_map', 'node_classes', 'object_class_map', 'predicate_aliases', 'subject_class_map']
            >>> vocab.to_report()['ner_class_map']
            {'org': 'Company'}
        """
        return {
            "ner_class_map": dict(self.ner_class_map),
            "node_classes": sorted(self.node_classes),
            "predicate_aliases": dict(self.predicate_aliases),
            "class_map": dict(self.class_map),
            "subject_class_map": dict(self.subject_class_map),
            "object_class_map": dict(self.object_class_map),
        }
