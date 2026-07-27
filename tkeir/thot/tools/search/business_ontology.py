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
        claim = str(
            row.get("claim") or row.get("claim_form") or ""
        ).strip()
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
        synonyms=[str(x) for x in (raw.get("synonyms") or [])],
        surface_forms=[str(x) for x in (raw.get("surface_forms") or [])],
        broader=[str(x) for x in (raw.get("broader") or [])],
        narrower=[str(x) for x in (raw.get("narrower") or [])],
        related=[str(x) for x in (raw.get("related") or [])],
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


def dataset_business_ontology_path(
    dataset: str,
    datasets_dir: Path | str | None = None,
) -> Path:
    """Return ``datasets/<dataset>/business_ontology.yaml``."""
    from thot.core.TkeirPaths import repo_root

    root = Path(datasets_dir) if datasets_dir else Path(repo_root()) / "datasets"
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

        from thot.tasks.document_ontology.OntologyAlignment import (
            _canonical_class_label,
            _cluster_labels,
        )
        from thot.tasks.document_ontology.label_vectorizer import (
            vectorize_labels_tfidf,
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
        counts = Counter(
            mapping.get(lab, lab).casefold() for lab in cleaned
        )
        centers.sort(
            key=lambda lab: (-counts.get(lab.casefold(), 0), lab.casefold())
        )
        return _rows(centers or cleaned)
    except Exception as exc:  # noqa: BLE001
        LOGGER.debug("core-concept clustering skipped: %s", exc)
        return _rows(cleaned)


def annotate_document_with_business_ontology(
    document: dict[str, Any],
    ontology_payload: dict[str, Any],
) -> dict[str, Any]:
    """Tag document ontology + KG with external concepts evidenced in text.

    - Merges into existing ``document_ontology.json_ld`` (does not wipe NLP).
    - Marks external DefinedTerm nodes with ``provenance: \"external\"``.
    - Appends KG triples (``rel:has_concept`` / ``rel:related_to``) with
      ``provenance: \"external\"``; existing document triples keep/get
      ``provenance: \"document\"``.
    - Selects ``core_concepts`` (cluster centers) always attached on the doc.

    Args:
        document: Pipeline document (returned as a shallow copy when tagged).
        ontology_payload: ``{concepts: [...]}`` from
            :func:`load_dataset_business_ontology_payload`.

    Returns:
        Document with merged ontology, KG provenance, and ``core_concepts``.
    """
    import re

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
    haystack = f"{title} {body} {chunk_text}".lower()
    if not haystack.strip():
        return document

    by_id: dict[str, dict[str, Any]] = {}
    matched_rows: list[dict[str, Any]] = []
    matched_ids: list[str] = []
    matched_labels: list[str] = []

    for raw in concepts:
        if not isinstance(raw, dict):
            continue
        cid = str(raw.get("concept_id") or "").strip()
        preferred = str(raw.get("preferred_label") or cid).strip()
        if not cid or not preferred:
            continue
        by_id[cid] = raw
        labels = [preferred]
        labels.extend(str(x) for x in (raw.get("synonyms") or []) if x)
        labels.extend(str(x) for x in (raw.get("surface_forms") or []) if x)
        for bridge in raw.get("paraphrase_bridges") or []:
            if not isinstance(bridge, dict):
                continue
            for key in ("claim", "document", "claim_form", "document_form"):
                val = bridge.get(key)
                if val:
                    labels.append(str(val))
        hit = False
        for label in labels:
            label = label.strip()
            if len(label) < 3:
                continue
            pattern = re.compile(
                r"(?<![a-z0-9])" + re.escape(label.lower()) + r"(?![a-z0-9])"
            )
            if pattern.search(haystack):
                hit = True
                break
        if not hit:
            continue
        matched_ids.append(cid)
        matched_labels.append(preferred)
        matched_rows.append(
            {
                "@type": "DefinedTerm",
                "name": preferred,
                "identifier": cid,
                "preferred_label": preferred,
                "provenance": "external",
            }
        )

    document = dict(document)

    # Ensure existing document-side KG triples carry provenance.
    kg = list(document.get("kg") or [])
    for triple in kg:
        if isinstance(triple, dict) and not triple.get("provenance"):
            triple["provenance"] = "document"

    # External concept triples + related links among matched concepts.
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
    for cid, preferred in zip(matched_ids, matched_labels, strict=True):
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
                    object_label=str(
                        other.get("preferred_label") or rid
                    ),
                )
            )
            existing_ext.add(rel_key)
    document["kg"] = kg

    # Merge json_ld graph: keep document nodes, add external DefinedTerms.
    existing_ont = dict(document.get("document_ontology") or {})
    graph = _parse_json_ld_graph(existing_ont.get("json_ld"))
    for node in graph:
        if "provenance" not in node:
            node["provenance"] = "document"
    seen_ids = {
        str(node.get("identifier") or node.get("@id") or "").strip()
        for node in graph
    }
    for row in matched_rows:
        cid = str(row.get("identifier") or "").strip()
        if cid and cid in seen_ids:
            continue
        graph.append(row)
        if cid:
            seen_ids.add(cid)

    # Core concepts = cluster centers over matched + document entities.
    entity_labels = matched_labels + _document_entity_labels(document)
    entity_ids = matched_ids + [""] * (
        len(entity_labels) - len(matched_ids)
    )
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
        key = cid or lab
        if key in seen_ids:
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
        seen_ids.add(key)

    status = str(existing_ont.get("shacl_status") or "").strip()
    if matched_rows:
        status = status or "dataset-ontology"
        if status and status != "dataset-ontology" and "external" not in status:
            status = f"{status}+external"
    document["document_ontology"] = {
        **existing_ont,
        "json_ld": json.dumps({"@graph": graph}, ensure_ascii=False),
        "shacl_status": status or ("dataset-ontology" if matched_rows else ""),
        "external_concept_ids": list(matched_ids),
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
