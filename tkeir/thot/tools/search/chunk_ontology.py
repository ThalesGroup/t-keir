"""Title: Chunk ontology fields for Graph-RAG style Vespa indexing.

Extract concept ids / linked ids / searchable labels from document ontology
(JSON-LD, SVO) and optional external business ontology, then attach them to
chunks for attribute overlap + BM25.

External ontology concepts are attached **only when a label is evidenced in
the chunk text** (not the document title alone). Linked neighbors
(broader / narrower / related) require the same chunk-text evidence.

``expansion_labels`` prefer paraphrase-bridge partners (not full synonym
lists). Causal / directionality hubs never expand labels (too generic).
Sparse vectors stay pure BGE-M3 — labels are for dumps / BM25 probe only.

Author: Eric Blaudez

Copyright (c) 2026 Thales
Licensed under the MIT License.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

LOGGER = logging.getLogger(__name__)

_WORD_RE = re.compile(r"[\w][\w\-]{1,}", re.UNICODE)

# Cross-cutting linguistic hubs — match as concept_ids OK; never dump full
# synonym lists into expansion_labels (generic verbs flood ranking).
_EXPANSION_HUB_PREFIXES = (
    "CAUSAL_",
    "DIRECTIONALITY",
    "SPECIFICITY_",
    "MECHANISTIC_",
)


def _is_expansion_hub(concept_id: str) -> bool:
    cid = (concept_id or "").strip().upper()
    return any(cid.startswith(prefix) for prefix in _EXPANSION_HUB_PREFIXES)


def _labels_from_concept_row(raw: dict[str, Any]) -> list[str]:
    labels = [str(raw.get("preferred_label") or raw.get("concept_id") or "")]
    labels.extend(str(x) for x in (raw.get("synonyms") or []) if x)
    labels.extend(str(x) for x in (raw.get("surface_forms") or []) if x)
    # paraphrase_bridges: claim ↔ document surface forms
    for bridge in raw.get("paraphrase_bridges") or []:
        if not isinstance(bridge, dict):
            continue
        for key in ("claim", "document", "claim_form", "document_form"):
            val = bridge.get(key)
            if val:
                labels.append(str(val))
    return [lab.strip() for lab in labels if lab and str(lab).strip()]


def _expansion_labels_for_row(
    raw: dict[str, Any],
    *,
    max_labels: int = 8,
) -> list[str]:
    """Safe expansion labels (preferred + paraphrase bridges only).

    Causal / directionality hubs return empty — their synonym lists are too
    generic for ranking. Other concepts keep preferred + bridge partners.
    """
    cid = str(raw.get("concept_id") or "").strip()
    if _is_expansion_hub(cid):
        return []
    preferred = str(raw.get("preferred_label") or "").strip()
    bridges: list[str] = []
    for bridge in raw.get("paraphrase_bridges") or []:
        if not isinstance(bridge, dict):
            continue
        for key in ("claim", "document", "claim_form", "document_form"):
            val = bridge.get(key)
            if val:
                bridges.append(str(val).strip())
    ordered = [preferred, *bridges]
    out: list[str] = []
    seen: set[str] = set()
    for lab in ordered:
        if not lab:
            continue
        key = lab.casefold()
        if key in seen:
            continue
        seen.add(key)
        out.append(lab)
        if len(out) >= max_labels:
            break
    return out


def _bridge_hit_in_text(raw: dict[str, Any], haystack_cf: str) -> bool:
    """True when any paraphrase-bridge side appears in the chunk."""
    for bridge in raw.get("paraphrase_bridges") or []:
        if not isinstance(bridge, dict):
            continue
        for key in ("claim", "document", "claim_form", "document_form"):
            val = bridge.get(key)
            if val and _label_in_text(str(val), haystack_cf):
                return True
    return False


def _label_in_text(label: str, haystack_cf: str) -> bool:
    """True when ``label`` appears in casefolded text with token boundaries."""
    cleaned = (label or "").strip()
    if len(cleaned) < 3:
        return False
    pattern = re.compile(
        r"(?<![a-z0-9])" + re.escape(cleaned.casefold()) + r"(?![a-z0-9])"
    )
    return pattern.search(haystack_cf) is not None


def _chunk_match_text(chunk: dict[str, Any]) -> str:
    """Body text used to decide whether a concept belongs to this chunk."""
    return str(
        chunk.get("text_raw")
        or chunk.get("search_vector_payload")
        or ""
    ).strip()


def extract_concepts_from_json_ld(json_ld: str | dict[str, Any]) -> list[str]:
    """Collect concept identifiers / short labels from document JSON-LD."""
    if isinstance(json_ld, str):
        if not json_ld.strip():
            return []
        try:
            data = json.loads(json_ld)
        except json.JSONDecodeError:
            return []
    else:
        data = json_ld
    found: list[str] = []
    seen: set[str] = set()

    def _walk(node: Any) -> None:
        if isinstance(node, dict):
            for key in ("identifier", "@id", "concept_id", "id"):
                val = node.get(key)
                if isinstance(val, str) and val.strip():
                    cid = val.strip()
                    # Skip URLs as ids unless last path segment is usable.
                    if "://" in cid:
                        cid = cid.rstrip("/").rsplit("/", 1)[-1]
                    if cid and cid not in seen and len(cid) < 120:
                        seen.add(cid)
                        found.append(cid)
            for key in ("name", "label", "prefLabel", "preferred_label"):
                val = node.get(key)
                if isinstance(val, str) and val.strip() and len(val) < 120:
                    lab = val.strip()
                    if lab not in seen:
                        seen.add(lab)
                        found.append(lab)
            for value in node.values():
                _walk(value)
        elif isinstance(node, list):
            for item in node:
                _walk(item)

    _walk(data)
    return found


def extract_svo_concept_labels(document: dict[str, Any]) -> list[str]:
    """Pull entity-like strings from SVO / kg structures on the document."""
    labels: list[str] = []
    seen: set[str] = set()

    def _add(text: str) -> None:
        tok = (text or "").strip()
        if len(tok) < 3 or tok.casefold() in seen:
            return
        seen.add(tok.casefold())
        labels.append(tok)

    for key in ("kg", "svo_triplets", "svo"):
        payload = document.get(key)
        if not payload:
            continue
        if isinstance(payload, dict):
            payload = payload.get("triplets") or payload.get("triples") or []
        if not isinstance(payload, list):
            continue
        for row in payload:
            if isinstance(row, dict):
                for part in (
                    row.get("subject"),
                    row.get("object"),
                    row.get("predicate"),
                    row.get("s"),
                    row.get("o"),
                    row.get("p"),
                ):
                    if isinstance(part, dict):
                        _add(str(part.get("text") or part.get("lemma") or ""))
                    elif part:
                        _add(str(part))
            elif isinstance(row, (list, tuple)) and len(row) >= 2:
                for part in row[:3]:
                    _add(str(part))
    return labels


def match_external_concepts(
    text: str,
    ontology_payload: dict[str, Any] | None,
) -> tuple[list[str], list[str], list[str]]:
    """Match external ontology concepts against **chunk** text only.

    A concept is kept only when at least one of its labels (preferred,
    synonym, surface form, paraphrase bridge) appears in ``text`` with
    token boundaries. Linked neighbors (broader / narrower / related) are
    included only when **they also** have label evidence in the same text —
    so graph expansion never attaches unrelated ontology nodes to a chunk.

    Returns:
        ``(concept_ids, linked_concept_ids, labels)``.
    """
    if not ontology_payload or not text.strip():
        return [], [], []
    concepts = ontology_payload.get("concepts") or []
    if not concepts:
        return [], [], []

    haystack = text.casefold()
    concept_ids: list[str] = []
    linked: list[str] = []
    labels: list[str] = []
    seen_ids: set[str] = set()
    seen_linked: set[str] = set()
    seen_labels: set[str] = set()

    by_id = {
        str(row.get("concept_id")): row
        for row in concepts
        if isinstance(row, dict) and row.get("concept_id")
    }

    def _add_label(lab: str) -> None:
        key = lab.casefold()
        if key in seen_labels:
            return
        seen_labels.add(key)
        labels.append(lab)

    for raw in concepts:
        if not isinstance(raw, dict):
            continue
        cid = str(raw.get("concept_id") or "").strip()
        if not cid:
            continue
        matched_labels: list[str] = []
        for label in _labels_from_concept_row(raw):
            if _label_in_text(label, haystack):
                matched_labels.append(label)
        # Paraphrase bridge alone is enough evidence (claim↔doc mismatch).
        if not matched_labels and _bridge_hit_in_text(raw, haystack):
            matched_labels = [
                lab
                for lab in _labels_from_concept_row(raw)
                if _label_in_text(lab, haystack)
            ] or [str(raw.get("preferred_label") or cid)]
        if not matched_labels:
            continue
        if cid not in seen_ids:
            seen_ids.add(cid)
            concept_ids.append(cid)
        # Expand full synonym / bridge set into labels (SPLADE-like).
        for lab in _expansion_labels_for_row(raw):
            _add_label(lab)

        for rel in ("broader", "narrower", "related"):
            for other in raw.get(rel) or []:
                oid = str(other).strip()
                if (
                    not oid
                    or oid in seen_ids
                    or oid in seen_linked
                ):
                    continue
                other_row = by_id.get(oid)
                linked_labels: list[str] = []
                if other_row:
                    for label in _labels_from_concept_row(other_row):
                        if _label_in_text(label, haystack):
                            linked_labels.append(label)
                    if not linked_labels and _bridge_hit_in_text(
                        other_row, haystack
                    ):
                        linked_labels = [
                            lab
                            for lab in _labels_from_concept_row(other_row)
                            if _label_in_text(lab, haystack)
                        ] or [
                            str(other_row.get("preferred_label") or oid)
                        ]
                elif _label_in_text(oid, haystack):
                    linked_labels.append(oid)
                if not linked_labels:
                    # Neighbor has no surface evidence in this chunk — skip.
                    continue
                seen_linked.add(oid)
                linked.append(oid)
                if other_row:
                    for lab in _expansion_labels_for_row(other_row):
                        _add_label(lab)
                else:
                    for lab in linked_labels:
                        _add_label(lab)

    return concept_ids, linked, labels


def chunk_ontology_fields(
    chunk: dict[str, Any],
    document: dict[str, Any],
    *,
    ontology_payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build Vespa ontology fields for one chunk.

    Combines document-extracted JSON-LD / SVO concepts with optional external
    ontology matches. External matches use **chunk body text only** so a
    title-only hit does not tag every passage.
    """
    ontology = document.get("document_ontology") or {}
    json_ld = ontology.get("json_ld") or ontology.get(
        "rdf_graph_serialized", ""
    )
    doc_concepts = extract_concepts_from_json_ld(json_ld)
    svo_labels = extract_svo_concept_labels(document)

    chunk_text = _chunk_match_text(chunk)
    hay = chunk_text.casefold()

    # Document JSON-LD: keep only concepts evidenced in this chunk.
    local_concepts: list[str] = []
    for cid in doc_concepts:
        if not hay:
            break
        if cid.casefold() in hay or any(
            tok and tok in hay
            for tok in _WORD_RE.findall(cid.casefold())
            if len(tok) >= 4
        ):
            local_concepts.append(cid)
        elif _label_in_text(cid, hay):
            local_concepts.append(cid)

    # External business ontology: chunk text only (never title-alone).
    ext_ids, ext_linked, ext_labels = match_external_concepts(
        chunk_text, ontology_payload
    )

    concept_ids: list[str] = []
    seen: set[str] = set()
    for cid in [*ext_ids, *local_concepts]:
        key = cid.casefold()
        if key in seen:
            continue
        seen.add(key)
        concept_ids.append(cid)

    linked_ids: list[str] = []
    seen_l: set[str] = set()
    for cid in ext_linked:
        key = cid.casefold()
        if key in seen or key in seen_l:
            continue
        seen_l.add(key)
        linked_ids.append(cid)

    # SVO labels only when they also appear in the chunk body.
    chunk_svo = [lab for lab in svo_labels if _label_in_text(lab, hay)] if hay else []

    labels: list[str] = []
    seen_lab: set[str] = set()
    for lab in [*ext_labels, *chunk_svo, *local_concepts]:
        key = lab.casefold()
        if key in seen_lab or len(lab) < 2:
            continue
        seen_lab.add(key)
        labels.append(lab)

    return {
        "concept_ids": concept_ids[:64],
        "linked_concept_ids": linked_ids[:64],
        # Expanded labels (synonyms + paraphrase bridges) for sparse enrich.
        "ontology_text": " ".join(labels[:96]),
        "expansion_labels": labels[:96],
    }
