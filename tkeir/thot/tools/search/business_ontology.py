"""Title: In-memory business ontology (SKOS-like) for query expansion and overlap.

Concept ids / linked concepts are also indexed on Vespa chunks (Graph-RAG).
The full ontology graph is loaded per query for expansion and relation scoring.

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


@dataclass(frozen=True)
class ParaphraseBridge:
    """Claim ↔ document surface-form bridge for paraphrase recall."""

    claim: str
    document: str


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
    paraphrase_bridges: list[ParaphraseBridge] = field(default_factory=list)


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
        """Index preferred labels, synonyms, surface forms, and bridges."""
        from thot.tools.search.lexical_signal import token_stems

        index: dict[str, str] = {}
        for concept in self.concepts.values():
            labels = (
                [concept.preferred_label]
                + list(concept.synonyms)
                + list(concept.surface_forms)
            )
            for bridge in concept.paraphrase_bridges:
                labels.append(bridge.claim)
                labels.append(bridge.document)
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

    def parents_within(self, concept_id: str, max_depth: int) -> set[str]:
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
        if self.is_descendant(doc_concept, query_concept, max_depth):
            return "narrower"
        if self.is_descendant(query_concept, doc_concept, max_depth):
            return "broader"
        q_parents = self.parents_within(query_concept, max_depth)
        d_parents = self.parents_within(doc_concept, max_depth)
        if q_parents & d_parents:
            return "shared_parent"
        return None


def _paraphrase_bridges(raw: dict[str, Any]) -> list[ParaphraseBridge]:
    bridges: list[ParaphraseBridge] = []
    for row in raw.get("paraphrase_bridges") or []:
        if not isinstance(row, dict):
            continue
        claim = str(row.get("claim") or row.get("claim_form") or "").strip()
        document = str(
            row.get("document") or row.get("document_form") or ""
        ).strip()
        if claim and document:
            bridges.append(ParaphraseBridge(claim=claim, document=document))
    return bridges


def _concept_from_mapping(raw: dict[str, Any]) -> BusinessConcept:
    return BusinessConcept(
        concept_id=str(raw["concept_id"]),
        preferred_label=str(raw.get("preferred_label") or raw["concept_id"]),
        synonyms=[str(x) for x in raw.get("synonyms") or []],
        surface_forms=[str(x) for x in raw.get("surface_forms") or []],
        broader=[str(x) for x in raw.get("broader") or []],
        narrower=[str(x) for x in raw.get("narrower") or []],
        related=[str(x) for x in raw.get("related") or []],
        paraphrase_bridges=_paraphrase_bridges(raw),
    )


def business_ontology_from_data(data: Any) -> BusinessOntology:
    """Build an ontology from a query payload (list or ``{concepts: [...]}``).

    The full graph is **not** stored server-side; clients pass concepts on each
    search / RAG request for query expansion and overlap scoring. Matched
    concept ids are also written onto Vespa chunks at index time.

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
        LOGGER.warning(
            "Unrecognized business ontology payload type=%s", type(data)
        )
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


def dataset_business_ontology_path(
    dataset: str,
    datasets_dir: Path | str | None = None,
) -> Path:
    """Return ``datasets/<dataset>/business_ontology.yaml``."""
    from thot.core.TkeirPaths import repo_root

    root = (
        Path(datasets_dir) if datasets_dir else Path(repo_root()) / "datasets"
    )
    return root / str(dataset).strip() / "business_ontology.yaml"


def load_dataset_business_ontology_payload(
    dataset: str,
    datasets_dir: Path | str | None = None,
) -> dict[str, Any] | None:
    """Load ``datasets/<dataset>/business_ontology.yaml`` as a request payload.

    Used at **index time** (chunk concept fields) and **query time**
    (expansion / overlap). Works for BEIR (``scifact``, ``fiqa``, …) and
    demo corpora (``osint``, ``enterprise``).

    Args:
        dataset: Dataset folder name under ``datasets/``.
        datasets_dir: Optional override of the datasets root.

    Returns:
        ``{concepts: [...]}`` or ``None`` when the file is missing/invalid.
    """
    name = (dataset or "").strip()
    if not name:
        return None
    path = dataset_business_ontology_path(name, datasets_dir)
    if not path.is_file():
        LOGGER.debug("No business ontology for dataset=%s at %s", name, path)
        return None
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or not data.get("concepts"):
        LOGGER.warning("Empty or invalid business ontology at %s", path)
        return None
    return data


def _concepts_list(payload: Any) -> list[dict[str, Any]]:
    """Normalize a request payload to a list of concept dicts."""
    if payload is None:
        return []
    if isinstance(payload, list):
        return [row for row in payload if isinstance(row, dict)]
    if isinstance(payload, dict):
        rows = payload.get("concepts")
        if isinstance(rows, list):
            return [row for row in rows if isinstance(row, dict)]
    return []


def merge_business_ontology_payloads(
    *payloads: Any,
) -> dict[str, Any] | None:
    """Merge concept lists by ``concept_id`` (later payloads override)."""
    by_id: dict[str, dict[str, Any]] = {}
    for payload in payloads:
        for row in _concepts_list(payload):
            cid = str(row.get("concept_id") or "").strip()
            if cid:
                by_id[cid] = dict(row)
    if not by_id:
        return None
    return {"concepts": list(by_id.values())}


def resolve_search_business_ontology(
    *,
    dataset: str | None = None,
    request_payload: Any = None,
    search_enabled: bool = True,
    datasets_dir: Path | str | None = None,
) -> dict[str, Any] | None:
    """Load dataset YAML (default ``osint``) and merge with request payload.

    Used by ``/search`` and ``/rag/query`` so live demos always expand against
    ``datasets/<dataset>/business_ontology.yaml`` unless search is disabled.
    """
    name = (dataset or "osint").strip() or "osint"
    file_payload = (
        load_dataset_business_ontology_payload(name, datasets_dir)
        if search_enabled
        else None
    )
    return merge_business_ontology_payloads(file_payload, request_payload)


def business_ontology_to_json_ld(payload: Any) -> str:
    """Serialize business-ontology concepts as OWL/SKOS JSON-LD.

    Emits ``owl:Class`` nodes with ``rdfs:label``, ``rdfs:subClassOf`` (from
    ``broader``), and SKOS ``broader`` / ``narrower`` / ``related`` links so
    the fused navigator graph and Python reasoner can walk the taxonomy.
    """
    concepts = _concepts_list(payload)
    if not concepts:
        return "[]"

    def _concept_iri(cid: str) -> str:
        return f"http://tkeir.local/concept/{cid}"

    context: dict[str, Any] = {
        "rdfs": "http://www.w3.org/2000/01/rdf-schema#",
        "owl": "http://www.w3.org/2002/07/owl#",
        "skos": "http://www.w3.org/2004/02/skos/core#",
        "schema": "http://schema.org/",
        "name": "rdfs:label",
        "alternateName": "schema:alternateName",
        "identifier": "schema:identifier",
        "broader": {"@id": "skos:broader", "@type": "@id"},
        "narrower": {"@id": "skos:narrower", "@type": "@id"},
        "related": {"@id": "skos:related", "@type": "@id"},
        "subClassOf": {"@id": "rdfs:subClassOf", "@type": "@id"},
        "DefinedTerm": "http://schema.org/DefinedTerm",
    }

    nodes: list[dict[str, Any]] = []
    for raw in concepts:
        cid = str(raw.get("concept_id") or "").strip()
        preferred = str(raw.get("preferred_label") or cid).strip()
        if not cid or not preferred:
            continue
        broader_iris = [
            {"@id": _concept_iri(str(x).strip())}
            for x in raw.get("broader") or []
            if str(x).strip()
        ]
        node: dict[str, Any] = {
            "@id": _concept_iri(cid),
            "@type": ["DefinedTerm", "owl:Class"],
            "name": preferred,
            "identifier": cid,
            "schema:provenance": "business_ontology",
        }
        synonyms = [str(x).strip() for x in raw.get("synonyms") or [] if x]
        surfaces = [
            str(x).strip() for x in raw.get("surface_forms") or [] if x
        ]
        alt = list(dict.fromkeys([*synonyms, *surfaces]))
        if alt:
            node["alternateName"] = alt
        if broader_iris:
            node["broader"] = broader_iris
            # OWL hierarchy: concept ⊑ broader parent
            node["subClassOf"] = broader_iris
        narrower_iris = [
            {"@id": _concept_iri(str(x).strip())}
            for x in raw.get("narrower") or []
            if str(x).strip()
        ]
        if narrower_iris:
            node["narrower"] = narrower_iris
        related_iris = [
            {"@id": _concept_iri(str(x).strip())}
            for x in raw.get("related") or []
            if str(x).strip()
        ]
        if related_iris:
            node["related"] = related_iris
        nodes.append(node)
    return json.dumps(
        {"@context": context, "@graph": nodes}, ensure_ascii=False
    )


def infer_dataset_name(
    document: dict[str, Any] | None = None,
    *,
    dataset: str | None = None,
    source_doc_id: str | None = None,
) -> str | None:
    """Infer dataset id from an explicit arg, document field, or ``beir:`` id."""
    if dataset and str(dataset).strip():
        return str(dataset).strip()
    if document:
        for key in ("dataset", "corpus", "beir_dataset"):
            raw = document.get(key)
            if raw and str(raw).strip():
                return str(raw).strip()
        source_doc_id = source_doc_id or document.get("source_doc_id")
    sid = str(source_doc_id or "").strip()
    if sid.startswith("beir:"):
        parts = sid.split(":", 2)
        if len(parts) >= 2 and parts[1].strip():
            return parts[1].strip()
    return None


def _kg_text_slot(text: str, *, label: str = "") -> dict[str, Any]:
    """Build a subject/property/value slot for a KG triple."""
    token = str(text or "").strip()
    return {
        "content": token,
        "label_content": label or "",
        "lemma_content": token.lower(),
        "class": -1,
        "positions": [-1],
        **({"label": label} if label else {}),
    }


def _kg_triple(
    *,
    subject: str,
    predicate: str,
    obj: str,
    provenance: str,
    field_type: str = "external_ontology",
    confidence: float = 1.0,
    object_label: str = "",
) -> dict[str, Any]:
    """One KG triple with an explicit provenance flag."""
    return {
        "subject": _kg_text_slot(subject),
        "property": _kg_text_slot(predicate),
        "value": _kg_text_slot(obj, label=object_label),
        "automatically_fill": True,
        "confidence": float(confidence),
        "weight": 0.0,
        "field_type": field_type,
        "provenance": provenance,
    }


def _parse_json_ld_graph(json_ld: Any) -> list[dict[str, Any]]:
    """Extract ``@graph`` nodes from a json_ld string or dict."""
    if not json_ld:
        return []
    data: Any = json_ld
    if isinstance(json_ld, str):
        if not json_ld.strip():
            return []
        try:
            data = json.loads(json_ld)
        except json.JSONDecodeError:
            return []
    if isinstance(data, list):
        return [row for row in data if isinstance(row, dict)]
    if isinstance(data, dict):
        graph = data.get("@graph")
        if isinstance(graph, list):
            return [row for row in graph if isinstance(row, dict)]
        return [data]
    return []


def _json_ld_was_array(json_ld: Any) -> bool:
    """True when the stored json_ld is a top-level array (NLP pipeline shape)."""
    if isinstance(json_ld, list):
        return True
    if isinstance(json_ld, str):
        return json_ld.lstrip().startswith("[")
    return False


def _json_ld_node_labels(node: dict[str, Any]) -> list[str]:
    """Collect human labels from a JSON-LD node (schema.org or RDF)."""
    labels: list[str] = []
    for key in (
        "name",
        "preferred_label",
        "identifier",
        "http://www.w3.org/2000/01/rdf-schema#label",
        "rdfs:label",
    ):
        raw = node.get(key)
        if isinstance(raw, str) and raw.strip():
            labels.append(raw.strip())
        elif isinstance(raw, list):
            for item in raw:
                if isinstance(item, dict):
                    val = item.get("@value")
                    if val:
                        labels.append(str(val).strip())
                elif item:
                    labels.append(str(item).strip())
    return [lab for lab in labels if lab]


def _enrich_nlp_nodes_with_ontology_paths(
    graph: list[dict[str, Any]],
    *,
    matched_ids: list[str],
    matched_paths: list[list[str]],
    matched_labels: list[str],
    matched_surfaces: list[str],
    by_id: dict[str, dict[str, Any]],
) -> None:
    """Stamp ontology paths onto NLP mention/keyword nodes that match BO terms.

    Pipeline ``document_ontology.json_ld`` uses RDF-style nodes (e.g. Misc for
    ``DARK_ACTIVITY_AIS_OFF``). Attach the broader path so the returned ontology
    shows ``C4ISR/…/DARK_ACTIVITY`` on that same mention.
    """
    path_by_norm: dict[str, tuple[str, list[str], list[str], str]] = {}
    for cid, path, preferred, surface in zip(
        matched_ids,
        matched_paths,
        matched_labels,
        matched_surfaces,
        strict=True,
    ):
        labels = _path_labels(path, by_id)
        compact = "/".join(path)
        payload = (cid, path, labels, compact)
        for candidate in (
            cid,
            preferred,
            surface,
            cid.replace("_", " "),
            *[str(x) for x in (by_id.get(cid) or {}).get("synonyms") or []],
            *[
                str(x)
                for x in (by_id.get(cid) or {}).get("surface_forms") or []
            ],
        ):
            norm = _normalize_for_ontology_match(candidate)
            if norm:
                path_by_norm[norm] = payload

    path_pred = "http://tkeir.local/ontology/ontologyPath"
    concept_pred = "http://tkeir.local/ontology/mapsToConcept"
    path_ids_pred = "http://tkeir.local/ontology/ontologyPathIds"
    for node in graph:
        if not isinstance(node, dict):
            continue
        node_labels = _json_ld_node_labels(node)
        hit: tuple[str, list[str], list[str], str] | None = None
        for lab in node_labels:
            hit = path_by_norm.get(_normalize_for_ontology_match(lab))
            if hit:
                break
        if hit is None:
            continue
        cid, path, labels, compact = hit
        node["ontology_path"] = list(path)
        node["ontology_path_labels"] = list(labels)
        node["ontology_path_text"] = " > ".join(labels)
        node["ontology_path_compact"] = compact
        node["maps_to_concept"] = cid
        # Reinforce: map NLP nodes onto BO without rebranding them as
        # external-only (external DefinedTerms keep provenance=external).
        existing_prov = str(node.get("provenance") or "").strip().lower()
        if existing_prov in {"", "document"}:
            node["provenance"] = "document+external"
        elif existing_prov == "external":
            node["provenance"] = "external"
        # else keep document+external / other combined tags
        node[path_pred] = [{"@value": compact}]
        node[path_ids_pred] = [
            {"@value": json.dumps(path, ensure_ascii=False)}
        ]
        node[concept_pred] = [{"@id": f"http://tkeir.local/concept/{cid}"}]


def _serialize_document_json_ld(
    graph: list[dict[str, Any]], *, as_array: bool
) -> str:
    """Serialize graph preserving NLP array shape when that was the input."""
    if as_array:
        return json.dumps(graph, ensure_ascii=False)
    return json.dumps({"@graph": graph}, ensure_ascii=False)


def _document_entity_labels(document: dict[str, Any]) -> list[str]:
    """Collect subject/object surface strings from document KG triples."""
    labels: list[str] = []
    seen: set[str] = set()
    for triple in document.get("kg") or []:
        if not isinstance(triple, dict):
            continue
        # Skip already-external triples when gathering document-side labels.
        if str(triple.get("provenance") or "").lower() == "external":
            continue
        for key in ("subject", "value"):
            slot = triple.get(key) or {}
            raw = slot.get("content")
            if isinstance(raw, list):
                text = " ".join(str(x) for x in raw if x).strip()
            else:
                text = str(raw or "").strip()
            if len(text) < 3:
                continue
            folded = text.casefold()
            if folded in seen:
                continue
            seen.add(folded)
            labels.append(text)
    return labels


def select_core_concepts(
    labels: list[str],
    *,
    concept_ids: list[str] | None = None,
    max_core: int = 12,
    similarity_threshold: float = 0.55,
    min_cluster_size: int = 2,
) -> list[dict[str, Any]]:
    """Pick the most important labels — nearest to each cluster centroid.

    Mirrors document-ontology alignment: agglomerative TF-IDF clustering,
    then the member closest to the cluster mean. Always returns at least the
    unique input labels when clustering is not applicable (too few items).

    Returns:
        List of ``{label, concept_id?, role: "cluster_center"}``.
    """
    cleaned: list[str] = []
    seen: set[str] = set()
    id_by_label: dict[str, str] = {}
    ids = list(concept_ids or [])
    for index, lab in enumerate(labels):
        text = str(lab or "").strip()
        if len(text) < 2:
            continue
        key = text.casefold()
        if key in seen:
            continue
        seen.add(key)
        cleaned.append(text)
        if index < len(ids) and ids[index]:
            id_by_label[key] = str(ids[index])

    def _rows(labs: list[str]) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for lab in labs[:max_core]:
            row: dict[str, Any] = {
                "label": lab,
                "role": "cluster_center",
            }
            cid = id_by_label.get(lab.casefold())
            if cid:
                row["concept_id"] = cid
            out.append(row)
        return out

    if not cleaned:
        return []
    if len(cleaned) < min_cluster_size:
        return _rows(cleaned)

    mapping: dict[str, str] = {lab: lab for lab in cleaned}
    try:
        from collections import Counter

        from thot.tasks.document_ontology.label_vectorizer import (
            vectorize_labels_tfidf,
        )
        from thot.tasks.document_ontology.OntologyAlignment import (
            _canonical_class_label,
            _cluster_labels,
        )

        vectors = vectorize_labels_tfidf(cleaned)
        mapping = _cluster_labels(
            cleaned,
            vectors,
            similarity_threshold=similarity_threshold,
            min_cluster_size=min_cluster_size,
            canonical_picker=_canonical_class_label,
        )
        centers: list[str] = []
        center_seen: set[str] = set()
        for canonical in mapping.values():
            key = canonical.casefold()
            if key in center_seen:
                continue
            center_seen.add(key)
            centers.append(canonical)
        counts = Counter(mapping.get(lab, lab).casefold() for lab in cleaned)
        centers.sort(
            key=lambda lab: (-counts.get(lab.casefold(), 0), lab.casefold())
        )
        return _rows(centers or cleaned)
    except Exception as exc:  # noqa: BLE001
        LOGGER.debug("core-concept clustering skipped: %s", exc)
        return _rows(cleaned)


def _concept_broader_paths(
    concept_id: str,
    by_id: dict[str, dict[str, Any]],
    *,
    max_depth: int = 32,
) -> list[list[str]]:
    """Return all root→leaf ``concept_id`` paths via ``broader`` links.

    Each path ends with ``concept_id``. Cycles / missing parents are skipped.
    """
    cid = str(concept_id or "").strip()
    if not cid:
        return []
    if cid not in by_id:
        return [[cid]]

    collected: list[list[str]] = []

    def _walk(node: str, ascending: list[str]) -> None:
        # ascending is node … → leaf (cid), built while walking up.
        if len(ascending) > max_depth:
            collected.append(list(reversed(ascending)))
            return
        parents = [
            str(p).strip()
            for p in (by_id.get(node) or {}).get("broader") or []
            if str(p).strip()
            and str(p).strip() in by_id
            and str(p).strip() not in ascending
        ]
        if not parents:
            collected.append(list(reversed(ascending)))
            return
        for parent in parents:
            _walk(parent, [*ascending, parent])

    _walk(cid, [cid])
    uniq: dict[tuple[str, ...], list[str]] = {
        tuple(path): path for path in collected if path and path[-1] == cid
    }
    return sorted(uniq.values(), key=lambda path: (-len(path), path)) or [
        [cid]
    ]


def _path_labels(
    path: list[str], by_id: dict[str, dict[str, Any]]
) -> list[str]:
    """Map a concept_id path to preferred labels."""
    labels: list[str] = []
    for cid in path:
        raw = by_id.get(cid) or {}
        labels.append(str(raw.get("preferred_label") or cid).strip() or cid)
    return labels


def _defined_term_node(
    *,
    concept_id: str,
    preferred_label: str,
    ontology_path: list[str] | None = None,
    ontology_path_labels: list[str] | None = None,
    role: str | None = None,
    matched: bool = False,
) -> dict[str, Any]:
    """Build a DefinedTerm JSON-LD node for an external business concept."""
    node: dict[str, Any] = {
        "@type": "DefinedTerm",
        "name": preferred_label,
        "identifier": concept_id,
        "preferred_label": preferred_label,
        "provenance": "external",
    }
    if ontology_path:
        node["ontology_path"] = list(ontology_path)
        node["ontology_path_compact"] = "/".join(ontology_path)
        node["skos:broader"] = (
            list(ontology_path[:-1]) if len(ontology_path) > 1 else []
        )
    if ontology_path_labels:
        node["ontology_path_labels"] = list(ontology_path_labels)
        node["ontology_path_text"] = " > ".join(ontology_path_labels)
    if role:
        node["role"] = role
    if matched:
        node["matched_in_text"] = True
    return node


def _normalize_for_ontology_match(text: str) -> str:
    """Normalize text for ontology label matching.

    Underscores, hyphens, and punctuation become spaces so
    ``DARK_ACTIVITY_AIS_OFF`` matches ``DARK_ACTIVITY AIS_OFF`` and
    ``MARITIME_ANALYTICS`` matches ``MARITIME ANALYTICS``.
    """
    import re
    import unicodedata

    value = unicodedata.normalize("NFKC", str(text or "")).lower()
    value = value.replace("—", " ").replace("–", " ").replace("−", " ")
    value = re.sub(r"[_\-/\\|]+", " ", value)
    value = re.sub(r"[^\w\s]", " ", value, flags=re.UNICODE)
    value = re.sub(r"\s+", " ", value).strip()
    # Common UK/US spelling so ontology synonyms still hit pipeline text.
    value = value.replace("behavioural", "behavioral")
    value = value.replace("behaviour", "behavior")
    return value


def _ontology_match_labels(raw: dict[str, Any], concept_id: str) -> list[str]:
    """Collect all surface labels used to detect a concept in text."""
    preferred = str(raw.get("preferred_label") or concept_id).strip()
    labels = [preferred, concept_id]
    # Spaced / underscored concept id variants.
    if "_" in concept_id:
        labels.append(concept_id.replace("_", " "))
    labels.extend(str(x) for x in raw.get("synonyms") or [] if x)
    labels.extend(str(x) for x in raw.get("surface_forms") or [] if x)
    for bridge in raw.get("paraphrase_bridges") or []:
        if not isinstance(bridge, dict):
            continue
        for key in ("claim", "document", "claim_form", "document_form"):
            val = bridge.get(key)
            if val:
                labels.append(str(val))
    # De-dupe while preserving order.
    seen: set[str] = set()
    out: list[str] = []
    for label in labels:
        key = label.strip()
        if not key:
            continue
        fold = key.casefold()
        if fold in seen:
            continue
        seen.add(fold)
        out.append(key)
    return out


def _label_hits_haystack(label: str, haystack_norm: str) -> bool:
    """True when normalized ``label`` appears as a whole phrase in haystack."""
    import re

    needle = _normalize_for_ontology_match(label)
    if len(needle) < 2:
        return False
    # Allow short all-caps codes (AIS, B1) but skip ultra-generic 1-char noise.
    if len(needle) < 3 and " " not in needle and not needle.isalnum():
        return False
    pattern = re.compile(
        r"(?<![a-z0-9])" + re.escape(needle) + r"(?![a-z0-9])"
    )
    return pattern.search(haystack_norm) is not None


def annotate_document_with_business_ontology(
    document: dict[str, Any],
    ontology_payload: dict[str, Any],
) -> dict[str, Any]:
    """Tag document ontology + KG with external concepts evidenced in text.

    - Merges into existing ``document_ontology.json_ld`` (does not wipe NLP).
    - Marks external DefinedTerm nodes with ``provenance: \"external\"``.
    - For each matched term, also attaches the **complete broader path**
      (root → … → matched concept) and inserts every ancestor DefinedTerm.
    - Appends KG triples (``rel:has_concept`` / ``rel:broader`` /
      ``rel:related_to``) with ``provenance: \"external\"``.
    - Selects ``core_concepts`` (cluster centers) always attached on the doc.

    Args:
        document: Pipeline document (returned as a shallow copy when tagged).
        ontology_payload: ``{concepts: [...]}`` from
            :func:`load_dataset_business_ontology_payload`.

    Returns:
        Document with merged ontology, KG provenance, and ``core_concepts``.
    """
    concepts = ontology_payload.get("concepts") or []
    if not concepts:
        return document

    title = str(document.get("title") or "")
    content = document.get("content") or []
    if isinstance(content, list):
        body = " ".join(str(part) for part in content if part)
    else:
        body = str(content or "")
    chunks = document.get("golden_chunks") or []
    chunk_text = " ".join(
        str(chunk.get("text_raw") or chunk.get("search_vector_payload") or "")
        for chunk in chunks
    )
    haystack_norm = _normalize_for_ontology_match(
        f"{title} {body} {chunk_text}"
    )
    if not haystack_norm:
        return document

    by_id: dict[str, dict[str, Any]] = {}
    for raw in concepts:
        if not isinstance(raw, dict):
            continue
        cid = str(raw.get("concept_id") or "").strip()
        if cid:
            by_id[cid] = raw

    matched_ids: list[str] = []
    matched_labels: list[str] = []
    matched_paths: list[list[str]] = []
    matched_surfaces: list[str] = []
    path_concept_ids: set[str] = set()

    for cid, raw in by_id.items():
        preferred = str(raw.get("preferred_label") or cid).strip()
        if not preferred:
            continue
        labels = _ontology_match_labels(raw, cid)
        hit_label = ""
        for label in labels:
            if _label_hits_haystack(label, haystack_norm):
                hit_label = label
                break
        if not hit_label:
            continue
        paths = _concept_broader_paths(cid, by_id)
        primary_path = paths[0] if paths else [cid]
        matched_ids.append(cid)
        matched_labels.append(preferred)
        matched_paths.append(primary_path)
        matched_surfaces.append(hit_label)
        path_concept_ids.update(primary_path)

    if not matched_ids:
        return document

    document = dict(document)

    # Ensure existing document-side KG triples carry provenance.
    kg = list(document.get("kg") or [])
    for triple in kg:
        if isinstance(triple, dict) and not triple.get("provenance"):
            triple["provenance"] = "document"

    # External concept triples + broader path edges + related links.
    source_ref = str(
        document.get("source_doc_id") or document.get("source") or "document"
    )
    existing_ext = {
        (
            str((t.get("subject") or {}).get("content") or ""),
            str((t.get("property") or {}).get("content") or ""),
            str((t.get("value") or {}).get("content") or ""),
        )
        for t in kg
        if isinstance(t, dict)
        and str(t.get("provenance") or "").lower() == "external"
    }
    for cid, preferred, path in zip(
        matched_ids, matched_labels, matched_paths, strict=True
    ):
        key = (source_ref, "rel:has_concept", cid)
        if key not in existing_ext:
            kg.append(
                _kg_triple(
                    subject=source_ref,
                    predicate="rel:has_concept",
                    obj=cid,
                    provenance="external",
                    object_label=preferred,
                )
            )
            existing_ext.add(key)
        # Path edges: parent --broader--> child (SKOS sense: child broader parent
        # is stored as child→parent; here rel:broader means "has broader").
        for idx in range(len(path) - 1):
            parent_id = path[idx]
            child_id = path[idx + 1]
            parent_lab = str(
                (by_id.get(parent_id) or {}).get("preferred_label")
                or parent_id
            )
            bro_key = (child_id, "rel:broader", parent_id)
            if bro_key not in existing_ext:
                kg.append(
                    _kg_triple(
                        subject=child_id,
                        predicate="rel:broader",
                        obj=parent_id,
                        provenance="external",
                        object_label=parent_lab,
                    )
                )
                existing_ext.add(bro_key)
        raw = by_id.get(cid) or {}
        for related_id in raw.get("related") or []:
            rid = str(related_id).strip()
            if not rid or rid not in by_id:
                continue
            if rid not in matched_ids:
                continue
            rel_key = (cid, "rel:related_to", rid)
            if rel_key in existing_ext:
                continue
            other = by_id[rid]
            kg.append(
                _kg_triple(
                    subject=cid,
                    predicate="rel:related_to",
                    obj=rid,
                    provenance="external",
                    object_label=str(other.get("preferred_label") or rid),
                )
            )
            existing_ext.add(rel_key)
    document["kg"] = kg

    # Merge json_ld graph: keep document nodes, add matched + ancestor terms.
    existing_ont = dict(document.get("document_ontology") or {})
    raw_json_ld = existing_ont.get("json_ld")
    as_array = _json_ld_was_array(raw_json_ld)
    graph = _parse_json_ld_graph(raw_json_ld)
    for node in graph:
        if "provenance" not in node:
            node["provenance"] = "document"
    seen_ids = {
        str(node.get("identifier") or node.get("@id") or "").strip()
        for node in graph
    }

    matched_rows: list[dict[str, Any]] = []
    ontology_paths: list[dict[str, Any]] = []
    for cid, preferred, path, surface in zip(
        matched_ids,
        matched_labels,
        matched_paths,
        matched_surfaces,
        strict=True,
    ):
        labels = _path_labels(path, by_id)
        compact = "/".join(path)
        # Insert ancestors first (without matched flag).
        for ancestor_id in path[:-1]:
            if ancestor_id in seen_ids:
                continue
            anc = by_id.get(ancestor_id) or {}
            anc_label = str(anc.get("preferred_label") or ancestor_id).strip()
            anc_paths = _concept_broader_paths(ancestor_id, by_id)
            anc_path = anc_paths[0] if anc_paths else [ancestor_id]
            anc_labels = _path_labels(anc_path, by_id)
            graph.append(
                _defined_term_node(
                    concept_id=ancestor_id,
                    preferred_label=anc_label,
                    ontology_path=anc_path,
                    ontology_path_labels=anc_labels,
                    role="ontology_path",
                    matched=False,
                )
            )
            seen_ids.add(ancestor_id)
        row = _defined_term_node(
            concept_id=cid,
            preferred_label=preferred,
            ontology_path=path,
            ontology_path_labels=labels,
            role="matched_term",
            matched=True,
        )
        row["ontology_path_compact"] = compact
        row["matched_surface"] = surface
        matched_rows.append(row)
        ontology_paths.append(
            {
                "concept_id": cid,
                "preferred_label": preferred,
                "matched_surface": surface,
                "ontology_path": path,
                "ontology_path_labels": labels,
                "ontology_path_text": " > ".join(labels),
                "ontology_path_compact": compact,
            }
        )
        if cid not in seen_ids:
            graph.append(row)
            seen_ids.add(cid)
        else:
            # Enrich an already-present node with the path.
            for node in graph:
                if str(node.get("identifier") or "").strip() == cid:
                    node.update(
                        {
                            "ontology_path": path,
                            "ontology_path_labels": labels,
                            "ontology_path_text": " > ".join(labels),
                            "ontology_path_compact": compact,
                            "matched_in_text": True,
                            "matched_surface": surface,
                            "provenance": "external",
                        }
                    )
                    break

    # Stamp paths onto NLP Misc/Keyword mentions (e.g. DARK_ACTIVITY_AIS_OFF).
    _enrich_nlp_nodes_with_ontology_paths(
        graph,
        matched_ids=matched_ids,
        matched_paths=matched_paths,
        matched_labels=matched_labels,
        matched_surfaces=matched_surfaces,
        by_id=by_id,
    )

    # Core concepts = document NLP labels first, then BO matches — reinforce
    # kg/NER rather than letting external ids monopolize the cluster centers.
    doc_labels = _document_entity_labels(document)
    entity_labels = doc_labels + matched_labels
    entity_ids = [""] * len(doc_labels) + matched_ids
    # Pad if lengths drift (matched_labels should align with matched_ids).
    if len(entity_ids) < len(entity_labels):
        entity_ids.extend([""] * (len(entity_labels) - len(entity_ids)))
    entity_ids = entity_ids[: len(entity_labels)]
    core = select_core_concepts(
        entity_labels,
        concept_ids=entity_ids,
        max_core=12,
    )
    document["core_concepts"] = core
    # Guarantee core concept ids appear as DefinedTerms on the document.
    for row in core:
        cid = str(row.get("concept_id") or "").strip()
        lab = str(row.get("label") or "").strip()
        if not cid and not lab:
            continue
        core_key = cid or lab
        if core_key in seen_ids:
            continue
        graph.append(
            {
                "@type": "DefinedTerm",
                "name": lab or cid,
                "identifier": cid or lab,
                "preferred_label": lab or cid,
                "provenance": "external" if cid in matched_ids else "document",
                "role": "cluster_center",
            }
        )
        seen_ids.add(core_key)

    status = str(existing_ont.get("shacl_status") or "").strip()
    if matched_rows:
        status = status or "dataset-ontology"
        if (
            status
            and status != "dataset-ontology"
            and "external" not in status
        ):
            status = f"{status}+external"
    document["document_ontology"] = {
        **existing_ont,
        "json_ld": _serialize_document_json_ld(graph, as_array=as_array),
        "shacl_status": status or ("dataset-ontology" if matched_rows else ""),
        "external_concept_ids": list(matched_ids),
        "external_ontology_path_ids": sorted(path_concept_ids),
        "external_ontology_paths": ontology_paths,
        "core_concepts": core,
    }
    return document


def resolve_index_ontology_payload(
    document: dict[str, Any],
    *,
    dataset: str | None = None,
    ontology_payload: dict[str, Any] | None = None,
    datasets_dir: Path | str | None = None,
) -> tuple[dict[str, Any] | None, str | None]:
    """Resolve the business ontology to apply at index time for one document.

    Preference order:
    1. Explicit ``ontology_payload``
    2. ``datasets/<dataset>/business_ontology.yaml`` for inferred dataset

    Returns:
        ``(payload_or_none, dataset_name_or_none)``.
    """
    name = infer_dataset_name(document, dataset=dataset)
    if ontology_payload is not None:
        return ontology_payload, name
    if not name:
        return None, None
    return load_dataset_business_ontology_payload(name, datasets_dir), name
