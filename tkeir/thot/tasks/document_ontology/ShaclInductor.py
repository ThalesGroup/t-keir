"""Induce SHACL node shapes from aligned document RDF graphs."""

from __future__ import annotations

from collections import defaultdict
from typing import cast

from rdflib import Graph, URIRef
from rdflib.namespace import RDF

from thot.tasks.document_ontology.OntologyAlignment import extract_class_labels
from thot.tasks.document_ontology.OntologyBuilder import TKEIR
from thot.tasks.document_ontology.OntologyVocabulary import (
    METRIC_CLASS,
    sanitize_rdf_class_name,
    sanitize_rdf_property_name,
)
from thot.tasks.document_ontology.ShaclShapes import DOCUMENT_SHACL_SHAPES_TTL


def _local_name(uri: URIRef) -> str:
    """Local name helper.

    Example:
        >>> from rdflib import URIRef
        >>> _local_name(URIRef('http://example.org#Person'))
        'Person'
    """
    text = str(uri)
    if "#" in text:
        return text.rsplit("#", 1)[-1]
    return text.rsplit("/", 1)[-1]


def _rewrite_shapes_ttl(
    shapes_ttl: str,
    class_map: dict[str, str],
    property_map: dict[str, str],
) -> str:
    """Replace class/property tokens in Turtle SHACL with canonical names.

    Example:
        >>> _rewrite_shapes_ttl('tkeir:writers', {'writers': 'Writer'}, {})
        'tkeir:Writer'
    """
    updated = shapes_ttl
    for old_label, new_label in class_map.items():
        if old_label != new_label:
            old_safe = sanitize_rdf_class_name(old_label, fallback=old_label)
            new_safe = sanitize_rdf_class_name(new_label, fallback=new_label)
            updated = updated.replace(
                f"tkeir:{old_label}", f"tkeir:{new_safe}"
            )
            if old_safe != old_label:
                updated = updated.replace(
                    f"tkeir:{old_safe}", f"tkeir:{new_safe}"
                )
    for old_label, new_label in property_map.items():
        if old_label != new_label:
            old_safe = sanitize_rdf_property_name(
                old_label, fallback=old_label
            )
            new_safe = sanitize_rdf_property_name(
                new_label, fallback=new_label
            )
            updated = updated.replace(
                f"tkeir:{old_label}", f"tkeir:{new_safe}"
            )
            if old_safe != old_label:
                updated = updated.replace(
                    f"tkeir:{old_safe}", f"tkeir:{new_safe}"
                )
    return updated


def _resolve_node_classes(
    graph: Graph,
    alignment_report: dict[str, object] | None,
) -> frozenset[str]:
    """Resolve node classes helper.

    Example:
        >>> from rdflib import Graph
        >>> _resolve_node_classes(Graph(), {'node_classes': ['Person']})
        frozenset({'Person'})
    """
    report = alignment_report or {}
    direct = report.get("node_classes")
    if isinstance(direct, (list, set, frozenset)):
        return frozenset(str(item) for item in direct)

    vocabulary = report.get("vocabulary") or {}
    if isinstance(vocabulary, dict):
        inner = vocabulary.get("vocabulary") or vocabulary
        classes = inner.get("node_classes")
        if isinstance(classes, (list, set, frozenset)):
            return frozenset(str(item) for item in classes)
    return frozenset(extract_class_labels(graph))


def _collect_typed_property_constraints(
    graph: Graph,
    node_classes: frozenset[str],
) -> dict[str, dict[str, set[str]]]:
    """Map class label -> property label -> set of object class labels.

    Example:
        >>> from rdflib import Graph, URIRef
        >>> from rdflib.namespace import RDF
        >>> from thot.tasks.document_ontology.OntologyBuilder import TKEIR
        >>> graph = Graph()
        >>> subj = URIRef('http://ex/s')
        >>> obj = URIRef('http://ex/o')
        >>> _ = graph.add((subj, RDF.type, TKEIR.Person))
        >>> _ = graph.add((obj, RDF.type, TKEIR.Organization))
        >>> _ = graph.add((subj, TKEIR.worksFor, obj))
        >>> 'worksFor' in _collect_typed_property_constraints(
        ...     graph, frozenset({'Person', 'Organization'})
        ... )['Person']
        True
    """
    constraints: dict[str, dict[str, set[str]]] = defaultdict(
        lambda: defaultdict(set)
    )
    for subject, predicate, obj in graph:
        if not isinstance(predicate, URIRef) or not isinstance(obj, URIRef):
            continue
        if not str(predicate).startswith(str(TKEIR)):
            continue
        subject_type = graph.value(subject, RDF.type)
        object_type = graph.value(obj, RDF.type)
        if not isinstance(subject_type, URIRef) or not isinstance(
            object_type, URIRef
        ):
            continue
        subject_class = _local_name(subject_type)
        object_class = _local_name(object_type)
        predicate_name = _local_name(predicate)
        if (
            subject_class not in node_classes
            or object_class not in node_classes
        ):
            continue
        constraints[subject_class][predicate_name].add(object_class)
    return constraints


def _induced_property_shape_lines(
    class_label: str,
    property_label: str,
    object_classes: set[str],
) -> list[str]:
    """Induced property shape lines helper.

    Example:
        >>> _induced_property_shape_lines('Person', 'worksFor', {'Organization'})[0]
        'tkeir:PersonInducedWorksForShape a sh:NodeShape ;'
    """
    class_name = sanitize_rdf_class_name(class_label, fallback="Entity")
    property_name = sanitize_rdf_property_name(
        property_label, fallback="relatedTo"
    )
    object_class = sanitize_rdf_class_name(
        sorted(object_classes)[0], fallback="Entity"
    )
    shape_property = (
        property_name[0].upper() + property_name[1:]
        if property_name
        else "RelatedTo"
    )
    return [
        f"tkeir:{class_name}Induced{shape_property}Shape a sh:NodeShape ;",
        f"  sh:targetClass tkeir:{class_name} ;",
        "  sh:property [",
        f"    sh:path tkeir:{property_name} ;",
        f"    sh:class tkeir:{object_class} ;",
        "    sh:minCount 1 ;",
        "  ] .",
        "",
    ]


def _metric_numeric_shape_lines() -> list[str]:
    """Metric numeric shape lines helper.

    Example:
        >>> _metric_numeric_shape_lines()[0]
        'tkeir:MetricNumericValueShape a sh:NodeShape ;'
    """
    return [
        f"tkeir:{METRIC_CLASS}NumericValueShape a sh:NodeShape ;",
        f"  sh:targetClass tkeir:{METRIC_CLASS} ;",
        "  sh:property [",
        "    sh:path tkeir:hasNumericValue ;",
        "    sh:datatype xsd:decimal ;",
        "    sh:minCount 1 ;",
        "  ] .",
        "",
    ]


def induce_document_shacl_shapes(
    graph: Graph,
    alignment_report: dict[str, object] | None = None,
) -> str:
    """Build SHACL shapes for the aligned graph.

    Starts from prefix-only base shapes, rewrites them with canonical class/property
    names from alignment, then appends induced node shapes for typed properties
    observed in the graph.

    Example:
        >>> from rdflib import Graph
        >>> from thot.tasks.document_ontology.ShaclInductor import induce_document_shacl_shapes
        >>> '@prefix sh:' in induce_document_shacl_shapes(Graph())
        True
    """
    alignment_report = alignment_report or {}
    class_map = cast(dict[str, str], alignment_report.get("class_map") or {})
    property_map = cast(
        dict[str, str], alignment_report.get("property_map") or {}
    )
    node_classes = _resolve_node_classes(graph, alignment_report)

    shapes_ttl = _rewrite_shapes_ttl(
        DOCUMENT_SHACL_SHAPES_TTL,
        class_map,
        property_map,
    )

    constraints = _collect_typed_property_constraints(graph, node_classes)
    induced_lines = [
        "@prefix sh: <http://www.w3.org/ns/shacl#> .",
        "@prefix tkeir: <http://tkeir.local/ontology/> .",
        "@prefix xsd: <http://www.w3.org/2001/XMLSchema#> .",
        "",
    ]

    if METRIC_CLASS in extract_class_labels(graph):
        induced_lines.extend(_metric_numeric_shape_lines())

    for class_label in sorted(constraints):
        canonical_class = class_map.get(class_label, class_label)
        for property_label, object_classes in sorted(
            constraints[class_label].items()
        ):
            canonical_property = property_map.get(
                property_label, property_label
            )
            canonical_objects = {
                class_map.get(object_class, object_class)
                for object_class in object_classes
            }
            induced_lines.extend(
                _induced_property_shape_lines(
                    canonical_class,
                    canonical_property,
                    canonical_objects,
                )
            )

    if len(induced_lines) > 5:
        return (
            shapes_ttl.rstrip()
            + "\n\n"
            + "\n".join(induced_lines).rstrip()
            + "\n"
        )
    return shapes_ttl
