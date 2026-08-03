"""Title: Derive / enrich a document ontology from existing reference ontologies.

Loads OWL/TTL/RDF reference graphs (bundled under
``tkeir/resources/ontologies/`` and/or absolute paths such as ingest-staged
uploads), matches document classes and labeled individuals by label
similarity, then adds linking triples before SHACL validation and Vespa
``json_ld`` storage.

Corpus / application ontologies are not discovered from the workspace —
clients upload them with each ingest request.

Author: Eric Blaudez

Copyright (c) 2026 Thales
Licensed under the MIT License.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from rdflib import OWL, RDF, RDFS, Graph, Literal, URIRef
from rdflib.term import Node

from thot.core.ThotLogger import ThotLogger
from thot.tasks.document_ontology.OntologyBuilder import TKEIR

DEFAULT_SIMILARITY_THRESHOLD = 0.8
_CAMEL_BOUNDARY = re.compile(
    r"(?<!^)(?=[A-Z])|(?<=[a-z])(?=[0-9])|(?<=[0-9])(?=[A-Za-z])"
)
_TOKEN_SPLIT = re.compile(r"[^a-zA-Z0-9]+")
_FORMAT_BY_SUFFIX = {
    ".ttl": "turtle",
    ".turtle": "turtle",
    ".n3": "n3",
    ".nt": "nt",
    ".rdf": "xml",
    ".owl": "xml",
    ".xml": "xml",
    ".jsonld": "json-ld",
    ".json": "json-ld",
}


def _lemma_token(token: str) -> str:
    """Normalize a token to a coarse lemma for fuzzy label matching.

    Args:
        token: Raw token from a class or property label.

    Returns:
        Lower-cased lemma (simple English plural stripping).

    Example:
        >>> _lemma_token("writers")
        'writer'
        >>> _lemma_token("Units")
        'unit'
    """
    normalized = token.lower().strip()
    if not normalized:
        return ""
    if len(normalized) > 3 and normalized.endswith("ies"):
        return normalized[:-3] + "y"
    if (
        len(normalized) > 3
        and normalized.endswith("s")
        and not normalized.endswith("ss")
    ):
        return normalized[:-1]
    return normalized


def _label_lemmas(label: str) -> list[str]:
    """Split a label into deduplicated lemma tokens.

    Args:
        label: Human-readable or camelCase ontology label.

    Returns:
        Ordered unique lemmas.

    Example:
        >>> _label_lemmas("GroundUnits")
        ['ground', 'unit']
        >>> _label_lemmas("writtenBy")
        ['written', 'by']
    """
    spaced = _CAMEL_BOUNDARY.sub(" ", str(label).strip())
    lemmas: list[str] = []
    seen: set[str] = set()
    for token in _TOKEN_SPLIT.split(spaced):
        if not token:
            continue
        lemma = _lemma_token(token)
        if lemma and lemma not in seen:
            seen.add(lemma)
            lemmas.append(lemma)
    return lemmas


def _label_lemma_text(label: str) -> str:
    """Join label lemmas into a single comparison string.

    Args:
        label: Ontology label.

    Returns:
        Space-separated lemma string.

    Example:
        >>> _label_lemma_text("GroundUnits")
        'ground unit'
    """
    return " ".join(_label_lemmas(label))


@dataclass(frozen=True)
class DerivationSettings:
    """Configuration for enriching a document graph from reference ontologies.

    Attributes:
        enabled: When False, :func:`derive_document_graph` is a no-op.
        paths: Reference ontology file paths from config.
        similarity_threshold: Minimum label score to accept a match.
        match_classes: Align document classes to reference classes.
        match_individuals: Align labeled individuals.
        match_properties: Reserved for property alignment (unused today).
        add_subclass_links: Emit ``rdfs:subClassOf`` for class matches.
        add_type_links: Emit extra ``rdf:type`` for individual→class matches.
        add_same_as_links: Emit ``owl:sameAs`` for individual matches.
        include_matched_axioms: Copy reference triples about matched URIs.
        min_label_length: Ignore shorter reference labels.
        save_report: Prefer full derivation details in the document payload.

    Example:
        >>> DerivationSettings(enabled=True, paths=("a.ttl",)).enabled
        True
    """

    enabled: bool = False
    paths: tuple[str, ...] = ()
    similarity_threshold: float = DEFAULT_SIMILARITY_THRESHOLD
    match_classes: bool = True
    match_individuals: bool = True
    match_properties: bool = False
    add_subclass_links: bool = True
    add_type_links: bool = True
    add_same_as_links: bool = True
    include_matched_axioms: bool = False
    min_label_length: int = 3
    save_report: bool = False


@dataclass
class _RefConcept:
    """One labeled concept extracted from a reference ontology.

    Example:
        >>> from rdflib import URIRef
        >>> c = _RefConcept(
        ...     URIRef("http://example.org/Unit"),
        ...     "Unit",
        ...     "class",
        ...     "unit",
        ... )
        >>> c.kind
        'class'
    """

    uri: URIRef
    label: str
    kind: str  # class | individual | property
    normalized: str


def _normalize_label(label: str) -> str:
    """Normalize a label for exact / fuzzy matching.

    Args:
        label: Raw ``rdfs:label`` or local name.

    Returns:
        Lower-cased, whitespace-collapsed label.

    Example:
        >>> _normalize_label(" Ground Unit ")
        'ground unit'
    """
    text = re.sub(r"\s+", " ", str(label).strip().lower())
    return text


def resolve_ontology_path(
    path: str,
    *,
    search_roots: list[Path] | None = None,
) -> Path:
    """Resolve an ontology file path with env expansion and search roots.

    Args:
        path: Absolute path, ``~``/``$ENV`` path, or relative name.
        search_roots: Directories to join with a relative ``path``.

    Returns:
        Absolute path to an existing file.

    Raises:
        FileNotFoundError: If no candidate file exists.

    Example:
        >>> from pathlib import Path
        >>> import tempfile
        >>> with tempfile.TemporaryDirectory() as td:
        ...     root = Path(td)
        ...     target = root / "ref.ttl"
        ...     _ = target.write_text("@prefix : <http://ex/> .", encoding="utf-8")
        ...     resolve_ontology_path("ref.ttl", search_roots=[root]) == target.resolve()
        True
    """
    expanded = os.path.expandvars(os.path.expanduser(str(path).strip()))
    candidate = Path(expanded)
    if candidate.is_file():
        return candidate.resolve()
    roots = search_roots or []
    for root in roots:
        joined = (root / expanded).resolve()
        if joined.is_file():
            return joined
    raise FileNotFoundError(f"reference ontology not found: {path}")


def default_search_roots() -> list[Path]:
    """Return directories used to resolve relative ontology paths.

    Only product-bundled locations are searched (never corpus / workspace
    application data). Absolute paths (e.g. ingest-staged uploads under
    ``INGEST_ROOT``) resolve directly in :func:`resolve_ontology_path`.

    Returns:
        Ordered unique roots under ``tkeir/resources/``.

    Example:
        >>> roots = default_search_roots()
        >>> isinstance(roots[0], Path) and len(roots) >= 1
        True
    """
    from thot.core.TkeirPaths import ontologies_dir, package_root

    roots = [
        Path(ontologies_dir()),
        Path(package_root()) / "resources",
        Path(package_root()) / "resources" / "modeling" / "ontologies",
    ]
    # Optional override for operators who ship extra generic ontologies.
    env_root = os.environ.get("TKEIR_ONTOLOGY_ROOT", "").strip()
    if env_root:
        roots.insert(0, Path(env_root).expanduser())

    seen: set[str] = set()
    ordered: list[Path] = []
    for root in roots:
        key = str(root.resolve()) if root.exists() else str(root)
        if key not in seen:
            seen.add(key)
            ordered.append(root)
    return ordered


def guess_rdf_format(path: Path) -> str:
    """Guess rdflib parse format from file suffix.

    Args:
        path: Ontology file path (suffix inspected only).

    Returns:
        An rdflib format name such as ``turtle`` or ``xml``.

    Example:
        >>> guess_rdf_format(Path("c2sim_combined.ttl"))
        'turtle'
        >>> guess_rdf_format(Path("c2sim_core.owl"))
        'xml'
    """
    return _FORMAT_BY_SUFFIX.get(path.suffix.lower(), "xml")


def load_reference_graph(
    paths: list[str] | tuple[str, ...],
    *,
    search_roots: list[Path] | None = None,
    call_context=None,
) -> Graph:
    """Load and merge one or more reference ontology files.

    Args:
        paths: File paths (absolute or resolvable via ``search_roots``).
        search_roots: Optional path search roots.
        call_context: Optional :class:`~thot.core.ThotLogger` context.

    Returns:
        Merged :class:`~rdflib.Graph`.

    Example:
        >>> from pathlib import Path
        >>> import tempfile
        >>> with tempfile.TemporaryDirectory() as td:
        ...     p = Path(td) / "mini.ttl"
        ...     _ = p.write_text(
        ...         "@prefix ex: <http://example.org/> .\\n"
        ...         "@prefix owl: <http://www.w3.org/2002/07/owl#> .\\n"
        ...         "@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .\\n"
        ...         'ex:Unit a owl:Class ; rdfs:label "Unit" .\\n',
        ...         encoding="utf-8",
        ...     )
        ...     g = load_reference_graph([str(p)])
        ...     len(g) > 0
        True
    """
    merged = Graph()
    roots = (
        search_roots if search_roots is not None else default_search_roots()
    )
    for raw in paths:
        path = resolve_ontology_path(raw, search_roots=roots)
        fmt = guess_rdf_format(path)
        try:
            merged.parse(path.as_posix(), format=fmt)
        except Exception:
            # OWL files sometimes parse better as turtle when mis-suffixed.
            merged.parse(path.as_posix(), format="xml")
        ThotLogger.info(
            f"Loaded reference ontology {path} ({fmt})",
            context=call_context,
        )
    return merged


def _labels_for(graph: Graph, subject: Node) -> list[str]:
    """Collect ``rdfs:label`` values (or local name fallback) for a subject.

    Args:
        graph: RDF graph.
        subject: Node to label.

    Returns:
        Non-empty label strings when available.

    Example:
        >>> from rdflib import Graph, Literal, URIRef, RDFS
        >>> g = Graph()
        >>> node = URIRef("http://example.org/Unit")
        >>> _ = g.add((node, RDFS.label, Literal("Ground Unit")))
        >>> _labels_for(g, node)
        ['Ground Unit']
    """
    labels: list[str] = []
    for _, _, obj in graph.triples((subject, RDFS.label, None)):
        if isinstance(obj, Literal):
            text = str(obj).strip()
            if text:
                labels.append(text)
    if not labels and isinstance(subject, URIRef):
        local = str(subject).rsplit("#", 1)[-1].rsplit("/", 1)[-1]
        if local:
            labels.append(local)
    return labels


def _append_reference_concept(    concepts: list[_RefConcept],
    seen: set[tuple[str, str, str]],
    graph: Graph,
    uri: URIRef,
    kind: str,
    min_label_length: int,
) -> None:
    """_append_reference_concept helper.
    
        Example:
            >>> from thot.tasks.document_ontology.OntologyDerivation import _append_reference_concept
            >>> callable(_append_reference_concept)
            True
    """

    for label in _labels_for(graph, uri):
        if len(label.strip()) < min_label_length:
            continue
        key = (str(uri), kind, _normalize_label(label))
        if key in seen:
            continue
        seen.add(key)
        concepts.append(
            _RefConcept(
                uri=uri,
                label=label,
                kind=kind,
                normalized=_normalize_label(label),
            )
        )


def _extract_typed_concepts(    graph: Graph,
    concepts: list[_RefConcept],
    seen: set[tuple[str, str, str]],
    rdf_type: Node,
    kind: str,
    min_label_length: int,
) -> None:
    """_extract_typed_concepts helper.
    
        Example:
            >>> from thot.tasks.document_ontology.OntologyDerivation import _extract_typed_concepts
            >>> callable(_extract_typed_concepts)
            True
    """

    for uri in graph.subjects(RDF.type, rdf_type):
        if isinstance(uri, URIRef):
            _append_reference_concept(
                concepts, seen, graph, uri, kind, min_label_length
            )


def _extract_labeled_concepts(    graph: Graph,
    concepts: list[_RefConcept],
    seen: set[tuple[str, str, str]],
    min_label_length: int,
) -> None:
    """_extract_labeled_concepts helper.
    
        Example:
            >>> from thot.tasks.document_ontology.OntologyDerivation import _extract_labeled_concepts
            >>> callable(_extract_labeled_concepts)
            True
    """

    for subj, _, _ in graph.triples((None, RDFS.label, None)):
        if not isinstance(subj, URIRef):
            continue
        types = {o for o in graph.objects(subj, RDF.type)}
        if OWL.Class in types or RDFS.Class in types:
            _append_reference_concept(
                concepts, seen, graph, subj, "class", min_label_length
            )
        elif (
            OWL.ObjectProperty in types
            or OWL.DatatypeProperty in types
            or RDF.Property in types
        ):
            _append_reference_concept(
                concepts, seen, graph, subj, "property", min_label_length
            )
        elif OWL.NamedIndividual in types or types:
            _append_reference_concept(
                concepts, seen, graph, subj, "individual", min_label_length
            )


def extract_reference_concepts(
    graph: Graph,
    *,
    min_label_length: int = 3,
) -> list[_RefConcept]:
    """Extract labeled classes, individuals, and properties from a reference graph.

    Args:
        graph: Reference ontology graph.
        min_label_length: Skip shorter labels.

    Returns:
        Deduplicated :class:`_RefConcept` list.

    Example:
        >>> from rdflib import Graph, Literal, URIRef, OWL, RDF, RDFS
        >>> g = Graph()
        >>> cls = URIRef("http://example.org/GroundUnit")
        >>> _ = g.add((cls, RDF.type, OWL.Class))
        >>> _ = g.add((cls, RDFS.label, Literal("GroundUnit")))
        >>> concepts = extract_reference_concepts(g)
        >>> concepts[0].kind
        'class'
        >>> concepts[0].normalized
        'groundunit'
    """
    concepts: list[_RefConcept] = []
    seen: set[tuple[str, str, str]] = set()

    _extract_typed_concepts(
        graph, concepts, seen, OWL.Class, "class", min_label_length
    )
    _extract_typed_concepts(
        graph, concepts, seen, RDFS.Class, "class", min_label_length
    )
    _extract_typed_concepts(
        graph, concepts, seen, OWL.ObjectProperty, "property", min_label_length
    )
    _extract_typed_concepts(
        graph,
        concepts,
        seen,
        OWL.DatatypeProperty,
        "property",
        min_label_length,
    )
    _extract_typed_concepts(
        graph, concepts, seen, RDF.Property, "property", min_label_length
    )
    _extract_typed_concepts(
        graph,
        concepts,
        seen,
        OWL.NamedIndividual,
        "individual",
        min_label_length,
    )
    _extract_labeled_concepts(graph, concepts, seen, min_label_length)

    return concepts


def _lemma_jaccard(a: str, b: str) -> float:
    """Jaccard similarity over lemma bags of two labels.

    Args:
        a: First label.
        b: Second label.

    Returns:
        Score in ``[0.0, 1.0]``.

    Example:
        >>> _lemma_jaccard("Ground Unit", "Ground Units")
        1.0
        >>> _lemma_jaccard("alpha", "bravo")
        0.0
    """
    la = set(_label_lemmas(a))
    lb = set(_label_lemmas(b))
    if not la or not lb:
        return 0.0
    return len(la & lb) / len(la | lb)


def _score_labels(doc_label: str, ref_label: str) -> float:
    """Score how well a document label matches a reference label.

    Args:
        doc_label: Label from the document graph.
        ref_label: Label from the reference ontology.

    Returns:
        Similarity in ``[0.0, 1.0]`` (1.0 = exact normalized match).

    Example:
        >>> _score_labels("Task Group ALPHA", "Task Group ALPHA")
        1.0
        >>> _score_labels("Ground Unit", "Ground Units") >= 0.9
        True
    """
    dn = _normalize_label(doc_label)
    rn = _normalize_label(ref_label)
    if not dn or not rn:
        return 0.0
    if dn == rn:
        return 1.0
    if dn in rn or rn in dn:
        return 0.92
    jaccard = _lemma_jaccard(doc_label, ref_label)
    if _label_lemma_text(doc_label) == _label_lemma_text(ref_label):
        return max(jaccard, 0.95)
    return jaccard


def _best_match(
    doc_label: str,
    concepts: list[_RefConcept],
    *,
    kinds: set[str],
    threshold: float,
) -> _RefConcept | None:
    """Return the best reference concept for ``doc_label`` above ``threshold``.

    Args:
        doc_label: Document-side label.
        concepts: Candidate reference concepts.
        kinds: Allowed concept kinds (``class``, ``individual``, …).
        threshold: Minimum accepted score.

    Returns:
        Best :class:`_RefConcept` or ``None``.

    Example:
        >>> from rdflib import URIRef
        >>> concepts = [
        ...     _RefConcept(URIRef("http://ex/A"), "Unit ALPHA", "individual", "unit alpha"),
        ...     _RefConcept(URIRef("http://ex/B"), "Other", "class", "other"),
        ... ]
        >>> hit = _best_match(
        ...     "Unit ALPHA", concepts, kinds={"individual"}, threshold=0.8
        ... )
        >>> hit is not None and str(hit.uri).endswith("/A")
        True
    """
    best: _RefConcept | None = None
    best_score = 0.0
    for concept in concepts:
        if concept.kind not in kinds:
            continue
        score = _score_labels(doc_label, concept.label)
        if score > best_score:
            best_score = score
            best = concept
    if best is None or best_score < threshold:
        return None
    return best


def _document_class_nodes(graph: Graph) -> dict[URIRef, str]:
    """Map TKEIR class URIs used as ``rdf:type`` objects to a display label.

    Args:
        graph: Document RDF graph.

    Returns:
        Mapping of TKEIR class URI → label (or local name).

    Example:
        >>> from rdflib import Graph, RDF, URIRef
        >>> from thot.tasks.document_ontology.OntologyBuilder import TKEIR
        >>> g = Graph()
        >>> _ = g.add((URIRef("http://tkeir.local/doc/e1"), RDF.type, TKEIR.Organization))
        >>> TKEIR.Organization in _document_class_nodes(g)
        True
    """
    found: dict[URIRef, str] = {}
    for _, _, obj in graph.triples((None, RDF.type, None)):
        if not isinstance(obj, URIRef):
            continue
        if not str(obj).startswith(str(TKEIR)):
            continue
        labels = _labels_for(graph, obj)
        local = str(obj).rsplit("/", 1)[-1]
        found[obj] = labels[0] if labels else local
    return found


def _document_individuals(graph: Graph) -> dict[URIRef, str]:
    """Map labeled non-class individuals in the document graph.

    Args:
        graph: Document RDF graph.

    Returns:
        Mapping of individual URI → ``rdfs:label`` text.

    Example:
        >>> from rdflib import Graph, Literal, URIRef, RDF, RDFS
        >>> from thot.tasks.document_ontology.OntologyBuilder import TKEIR
        >>> g = Graph()
        >>> node = URIRef("http://tkeir.local/doc/e1")
        >>> _ = g.add((node, RDF.type, TKEIR.Organization))
        >>> _ = g.add((node, RDFS.label, Literal("Acme")))
        >>> _document_individuals(g)[node]
        'Acme'
    """
    found: dict[URIRef, str] = {}
    for subj, _, lab in graph.triples((None, RDFS.label, None)):
        if not isinstance(subj, URIRef) or not isinstance(lab, Literal):
            continue
        types = set(graph.objects(subj, RDF.type))
        if OWL.Class in types or RDFS.Class in types:
            continue
        text = str(lab).strip()
        if text:
            found[subj] = text
    return found


def _copy_matched_axioms(
    document_graph: Graph,
    reference_graph: Graph,
    matched_uris: set[URIRef],
) -> int:
    """Copy reference triples that mention matched URIs into the document graph.

    Args:
        document_graph: Destination graph (mutated).
        reference_graph: Source reference ontology.
        matched_uris: URIs whose incident triples should be copied.

    Returns:
        Number of triples added.

    Example:
        >>> from rdflib import Graph, Literal, URIRef, RDF, RDFS, OWL
        >>> doc, ref = Graph(), Graph()
        >>> uri = URIRef("http://ex/Unit")
        >>> _ = ref.add((uri, RDF.type, OWL.Class))
        >>> _ = ref.add((uri, RDFS.label, Literal("Unit")))
        >>> _copy_matched_axioms(doc, ref, {uri}) >= 1
        True
    """
    added = 0
    for uri in matched_uris:
        for triple in reference_graph.triples((uri, None, None)):
            if triple not in document_graph:
                document_graph.add(triple)
                added += 1
        for triple in reference_graph.triples((None, None, uri)):
            if triple not in document_graph:
                document_graph.add(triple)
                added += 1
    return added


def _apply_subclass_links(    document_graph: Graph,
    concepts: list[_RefConcept],
    cfg: DerivationSettings,
    matched_uris: set[URIRef],
    details: list[dict[str, Any]],
) -> int:
    """_apply_subclass_links helper.
    
        Example:
            >>> from thot.tasks.document_ontology.OntologyDerivation import _apply_subclass_links
            >>> callable(_apply_subclass_links)
            True
    """

    links = 0
    if not (cfg.match_classes and cfg.add_subclass_links):
        return links
    for class_uri, label in _document_class_nodes(document_graph).items():
        hit = _best_match(
            label,
            concepts,
            kinds={"class"},
            threshold=cfg.similarity_threshold,
        )
        if hit is None:
            continue
        triple = (class_uri, RDFS.subClassOf, hit.uri)
        if triple not in document_graph:
            document_graph.add(triple)
            links += 1
        matched_uris.add(hit.uri)
        details.append(
            {
                "kind": "subclass",
                "document": str(class_uri),
                "reference": str(hit.uri),
                "label": label,
                "reference_label": hit.label,
            }
        )
    return links


def _apply_individual_type_link(    document_graph: Graph,
    node: URIRef,
    label: str,
    concepts: list[_RefConcept],
    cfg: DerivationSettings,
    matched_uris: set[URIRef],
    details: list[dict[str, Any]],
) -> int:
    """_apply_individual_type_link helper.
    
        Example:
            >>> from thot.tasks.document_ontology.OntologyDerivation import _apply_individual_type_link
            >>> callable(_apply_individual_type_link)
            True
    """

    if not (cfg.match_individuals and cfg.add_type_links):
        return 0
    class_hit = _best_match(
        label,
        concepts,
        kinds={"class"},
        threshold=cfg.similarity_threshold,
    )
    if class_hit is None:
        return 0
    triple = (node, RDF.type, class_hit.uri)
    added = 0
    if triple not in document_graph:
        document_graph.add(triple)
        added = 1
    matched_uris.add(class_hit.uri)
    details.append(
        {
            "kind": "type",
            "document": str(node),
            "reference": str(class_hit.uri),
            "label": label,
            "reference_label": class_hit.label,
        }
    )
    return added


def _apply_individual_same_as_link(    document_graph: Graph,
    node: URIRef,
    label: str,
    concepts: list[_RefConcept],
    cfg: DerivationSettings,
    matched_uris: set[URIRef],
    details: list[dict[str, Any]],
) -> int:
    """_apply_individual_same_as_link helper.
    
        Example:
            >>> from thot.tasks.document_ontology.OntologyDerivation import _apply_individual_same_as_link
            >>> callable(_apply_individual_same_as_link)
            True
    """

    if not (cfg.match_individuals and cfg.add_same_as_links):
        return 0
    ind_hit = _best_match(
        label,
        concepts,
        kinds={"individual"},
        threshold=cfg.similarity_threshold,
    )
    if ind_hit is None:
        return 0
    triple = (node, OWL.sameAs, ind_hit.uri)
    added = 0
    if triple not in document_graph:
        document_graph.add(triple)
        added = 1
    matched_uris.add(ind_hit.uri)
    details.append(
        {
            "kind": "sameAs",
            "document": str(node),
            "reference": str(ind_hit.uri),
            "label": label,
            "reference_label": ind_hit.label,
        }
    )
    return added


def derive_document_graph(
    document_graph: Graph,
    reference_graph: Graph,
    *,
    settings: DerivationSettings | None = None,
    call_context=None,
) -> tuple[Graph, dict[str, Any]]:
    """Enrich ``document_graph`` with links derived from ``reference_graph``.

    Adds ``rdfs:subClassOf``, extra ``rdf:type``, and/or ``owl:sameAs`` triples
    when document labels match reference concepts above the similarity
    threshold.

    Args:
        document_graph: Document ontology graph (mutated in place).
        reference_graph: Existing ontology to derive from.
        settings: Derivation options; defaults to enabled settings.
        call_context: Optional logger context.

    Returns:
        Tuple of ``(document_graph, report_dict)``.

    Example:
        >>> from rdflib import Graph, Literal, URIRef, OWL, RDF, RDFS
        >>> from thot.tasks.document_ontology.OntologyBuilder import TKEIR
        >>> doc = Graph()
        >>> entity = URIRef("http://tkeir.local/doc/e1")
        >>> _ = doc.add((entity, RDF.type, TKEIR.Organization))
        >>> _ = doc.add((entity, RDFS.label, Literal("Task Group ALPHA")))
        >>> ref = Graph()
        >>> unit = URIRef("http://www.sisostds.org/ontologies/C2SIM#Unit_ALPHA")
        >>> _ = ref.add((unit, RDF.type, OWL.NamedIndividual))
        >>> _ = ref.add((unit, RDFS.label, Literal("Task Group ALPHA")))
        >>> enriched, report = derive_document_graph(
        ...     doc,
        ...     ref,
        ...     settings=DerivationSettings(
        ...         enabled=True,
        ...         add_same_as_links=True,
        ...         add_type_links=False,
        ...     ),
        ... )
        >>> report["matches"]
        1
        >>> (entity, OWL.sameAs, unit) in enriched
        True
    """
    cfg = settings or DerivationSettings(enabled=True)
    report: dict[str, Any] = {
        "enabled": True,
        "status": "SKIPPED",
        "matches": 0,
        "subclass_links": 0,
        "type_links": 0,
        "same_as_links": 0,
        "axioms_copied": 0,
        "details": [],
    }
    if not cfg.enabled:
        report["enabled"] = False
        return document_graph, report

    concepts = extract_reference_concepts(
        reference_graph, min_label_length=cfg.min_label_length
    )
    if not concepts:
        report["status"] = "NO_REFERENCE_CONCEPTS"
        return document_graph, report

    matched_uris: set[URIRef] = set()
    details: list[dict[str, Any]] = []

    report["subclass_links"] = _apply_subclass_links(
        document_graph,
        concepts,
        cfg,
        matched_uris,
        details,
    )

    for node, label in _document_individuals(document_graph).items():
        report["type_links"] += _apply_individual_type_link(
            document_graph,
            node,
            label,
            concepts,
            cfg,
            matched_uris,
            details,
        )
        report["same_as_links"] += _apply_individual_same_as_link(
            document_graph,
            node,
            label,
            concepts,
            cfg,
            matched_uris,
            details,
        )

    if cfg.include_matched_axioms and matched_uris:
        report["axioms_copied"] = _copy_matched_axioms(
            document_graph, reference_graph, matched_uris
        )

    report["matches"] = len(details)
    report["details"] = details
    report["status"] = "APPLIED" if details else "NO_MATCHES"
    ThotLogger.info(
        "Document ontology derivation "
        f"status={report['status']} matches={report['matches']} "
        f"subclass={report['subclass_links']} type={report['type_links']} "
        f"sameAs={report['same_as_links']}",
        context=call_context,
    )
    return document_graph, report


def parse_derivation_settings(
    raw: dict[str, Any] | None,
) -> DerivationSettings:
    """Parse ``derive-from`` builder configuration.

    Args:
        raw: Mapping from YAML (``derive-from``) or ``None``.

    Returns:
        Normalized :class:`DerivationSettings`.

    Example:
        >>> s = parse_derivation_settings({"enabled": True, "paths": ["a.ttl"]})
        >>> s.enabled and s.paths == ("a.ttl",)
        True
    """
    cfg = raw if isinstance(raw, dict) else {}
    paths_raw = cfg.get("paths") or cfg.get("path") or []
    if isinstance(paths_raw, str):
        paths: tuple[str, ...] = (paths_raw,)
    else:
        paths = tuple(str(p) for p in paths_raw if str(p).strip())
    similarity_raw = cfg.get(
        "similarity-threshold",
        cfg.get("similarity_threshold", DEFAULT_SIMILARITY_THRESHOLD),
    )
    if similarity_raw is None:
        similarity_raw = DEFAULT_SIMILARITY_THRESHOLD
    min_label_raw = cfg.get(
        "min-label-length",
        cfg.get("min_label_length", 3),
    )
    if min_label_raw is None:
        min_label_raw = 3
    return DerivationSettings(
        enabled=bool(cfg.get("enabled", False)),
        paths=paths,
        similarity_threshold=float(similarity_raw),
        match_classes=bool(
            cfg.get("match-classes", cfg.get("match_classes", True))
        ),
        match_individuals=bool(
            cfg.get("match-individuals", cfg.get("match_individuals", True))
        ),
        match_properties=bool(
            cfg.get("match-properties", cfg.get("match_properties", False))
        ),
        add_subclass_links=bool(
            cfg.get(
                "add-subclass-links",
                cfg.get("add_subclass_links", True),
            )
        ),
        add_type_links=bool(
            cfg.get("add-type-links", cfg.get("add_type_links", True))
        ),
        add_same_as_links=bool(
            cfg.get("add-same-as-links", cfg.get("add_same_as_links", True))
        ),
        include_matched_axioms=bool(
            cfg.get(
                "include-matched-axioms",
                cfg.get("include_matched_axioms", False),
            )
        ),
        min_label_length=max(1, int(min_label_raw)),
        save_report=bool(
            cfg.get("save-report", cfg.get("save_report", False))
        ),
    )


def derivation_paths_for_document(
    tkeir_doc: dict[str, Any],
    settings: DerivationSettings,
) -> list[str]:
    """Merge config paths with optional per-document overrides.

    Document keys consulted: ``ontologies``, ``derive_from_ontologies``,
    ``ontology_sources``, and the same keys under ``metadata``.

    Args:
        tkeir_doc: T-KEIR document dict.
        settings: Parsed builder settings (provides default ``paths``).

    Returns:
        Deduplicated ordered list of ontology paths.

    Example:
        >>> settings = DerivationSettings(paths=("base.ttl",))
        >>> derivation_paths_for_document(
        ...     {"ontologies": ["extra.ttl"]},
        ...     settings,
        ... )
        ['base.ttl', 'extra.ttl']
    """
    from thot.tasks.document_ontology.OntologyLexicon import (
        ontology_paths_from_document,
    )

    paths: list[str] = list(settings.paths)
    paths.extend(ontology_paths_from_document(tkeir_doc))
    seen: set[str] = set()
    ordered: list[str] = []
    for path in paths:
        if path not in seen:
            seen.add(path)
            ordered.append(path)
    return ordered
