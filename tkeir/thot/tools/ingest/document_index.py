"""Title: Document-level index fields (tags, author, simhash, ontology pointers).

Builds Vespa ``corpus_doc`` payloads from a pipeline document and its
chunks. The indexed document id is ``sha256(source_ref)[:40]``; every
chunk stores that value as ``parent_doc_id``.

Author: Eric Blaudez

Copyright (c) 2026 Thales
Licensed under the MIT License.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from thot.tools.collector.simhash import hamming_distance, simhash64
from thot.tools.search.vespa_client import sanitize_vespa_string

KIND_TEXT = "texte"
KIND_MAP = "carte"
KIND_LANDSCAPE = "paysage"
KIND_IMAGE = "image"
KIND_TABLE = "table"

_LOCATION_LABELS = frozenset(
    {
        "location",
        "gpe",
        "loc",
        "city",
        "facility",
        "fac",
        "place",
        "geoloc",
    }
)
_TIME_LABELS = frozenset({"date", "time", "datetime", "year"})
_PERSON_LABELS = frozenset({"person", "per", "cite_person"})
_MAP_HINTS = (
    "carte",
    "carto",
    "map",
    "geomap",
    "gis",
    "geojson",
    "kml",
    "shapefile",
)
_LANDSCAPE_HINTS = (
    "paysage",
    "landscape",
    "relief",
    "terrain",
    "orthophoto",
)
_IMAGE_EXT = frozenset(
    {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".webp", ".gif", ".bmp"}
)
_TABLE_EXT = frozenset({".csv", ".tsv", ".xlsx", ".xls", ".ods"})
_MAP_EXT = frozenset({".geojson", ".kml", ".kmz", ".shp", ".gpkg", ".tif"})
_AUTHOR_KEYS = (
    "author",
    "authors",
    "creator",
    "dc:creator",
    "created_by",
)
_COLLECTION_KEYS = (
    "collection",
    "corpus",
    "topic_id",
    "dataset",
    "pack",
)
_FORMAT_KEYS = (
    "source_format",
    "file_type",
    "input_format",
    "format",
    "mime_type",
    "doc_type",
)


def corpus_doc_docid(source_ref: str) -> str:
    """Stable Vespa docid for one ``corpus_doc`` (indexed document id).

    Chunks store this value in ``parent_doc_id``.

    Example:
        >>> from thot.tools.ingest.document_index import corpus_doc_docid
        >>> len(corpus_doc_docid('geomaps/r1')) == 40
        True
        >>> corpus_doc_docid('geomaps/r1') == corpus_doc_docid('geomaps/r1')
        True
    """
    digest = hashlib.sha256((source_ref or "").encode("utf-8")).hexdigest()
    return digest[:40]


def unique_strings(values: list[Any], *, limit: int = 32) -> list[str]:
    """Deduplicate trimmed strings, preserving order.

    Example:
        >>> from thot.tools.ingest.document_index import unique_strings
        >>> unique_strings(['Paris', 'paris', ' Lyon ', ''])
        ['Paris', 'Lyon']
    """
    out: list[str] = []
    seen: set[str] = set()
    for raw in values:
        text = str(raw or "").strip()
        if not text:
            continue
        key = text.casefold()
        if key in seen:
            continue
        seen.add(key)
        out.append(text[:180])
        if len(out) >= limit:
            break
    return out


def _metadata(document: dict[str, Any]) -> dict[str, Any]:
    """Return the document metadata mapping.

    Example:
        >>> from thot.tools.ingest.document_index import _metadata
        >>> _metadata({'metadata': {'author': 'Ada'}})['author']
        'Ada'
    """
    meta = document.get("metadata")
    return meta if isinstance(meta, dict) else {}


def _ner_spans(document: dict[str, Any]) -> list[dict[str, Any]]:
    """Collect title + content NER spans.

    Example:
        >>> from thot.tools.ingest.document_index import _ner_spans
        >>> _ner_spans({'content_ner': [{'text': 'Paris', 'label': 'GPE'}]})[0]['text']
        'Paris'
    """
    spans: list[dict[str, Any]] = []
    for key in ("title_ner", "content_ner"):
        for item in document.get(key) or []:
            if isinstance(item, dict):
                spans.append(item)
    return spans


def _label_of(span: dict[str, Any]) -> str:
    """Normalized NER label.

    Example:
        >>> from thot.tools.ingest.document_index import _label_of
        >>> _label_of({'label': 'GPE'})
        'gpe'
    """
    return str(span.get("label") or span.get("type") or "").strip().casefold()


def _text_of(span: dict[str, Any]) -> str:
    """NER surface form.

    Example:
        >>> from thot.tools.ingest.document_index import _text_of
        >>> _text_of({'text': 'Paris'})
        'Paris'
    """
    return str(span.get("text") or span.get("mention") or "").strip()


def _haystack(document: dict[str, Any]) -> str:
    """Lowercased title + dataset + format hints for kind detection.

    Example:
        >>> from thot.tools.ingest.document_index import _haystack
        >>> 'map' in _haystack({'title': 'City map', 'dataset': 'geomaps'})
        True
    """
    meta = _metadata(document)
    parts = [
        str(document.get("title") or ""),
        str(document.get("dataset") or ""),
        str(document.get("source_doc_id") or document.get("source") or ""),
        str(meta.get("doc_type") or ""),
        str(meta.get("file_type") or ""),
        str(meta.get("format") or ""),
    ]
    return " ".join(parts).casefold()


def extract_author(document: dict[str, Any]) -> str:
    """Author from metadata, then title PERSON NER.

    Example:
        >>> from thot.tools.ingest.document_index import extract_author
        >>> extract_author({'metadata': {'author': 'Ada Lovelace'}})
        'Ada Lovelace'
        >>> extract_author({
        ...     'title_ner': [{'text': 'Marie Curie', 'label': 'PERSON'}],
        ... })
        'Marie Curie'
    """
    meta = _metadata(document)
    for key in _AUTHOR_KEYS:
        value = meta.get(key) or document.get(key)
        if isinstance(value, list) and value:
            value = value[0]
        text = str(value or "").strip()
        if text:
            return text[:180]
    for span in document.get("title_ner") or []:
        if isinstance(span, dict) and _label_of(span) in _PERSON_LABELS:
            text = _text_of(span)
            if text:
                return text[:180]
    return ""


def extract_collection(document: dict[str, Any]) -> str:
    """Collection / corpus / dataset tag.

    Example:
        >>> from thot.tools.ingest.document_index import extract_collection
        >>> extract_collection({'dataset': 'geomaps'})
        'geomaps'
    """
    meta = _metadata(document)
    for key in _COLLECTION_KEYS:
        value = meta.get(key) or document.get(key)
        text = str(value or "").strip()
        if text:
            return text[:180]
    return ""


def extract_doc_format(document: dict[str, Any]) -> str:
    """File / converter format (pdf, markdown, geojson, …).

    Example:
        >>> from thot.tools.ingest.document_index import extract_doc_format
        >>> extract_doc_format({'metadata': {'file_type': 'pdf'}})
        'pdf'
        >>> extract_doc_format({'source_doc_id': 'file://maps/a.geojson'})
        'geojson'
    """
    meta = _metadata(document)
    for key in _FORMAT_KEYS:
        value = meta.get(key) or document.get(key)
        text = str(value or "").strip().lstrip(".").casefold()
        if text:
            return text.split(";")[0].split("/")[-1][:40]
    source = str(document.get("source_doc_id") or document.get("source") or "")
    path = source
    if "://" in source:
        path = urlparse(source).path or source
    suffix = Path(path).suffix.casefold().lstrip(".")
    return suffix[:40]


def infer_data_kind(document: dict[str, Any]) -> str:
    """Data type: ``texte``, ``carte``, ``paysage``, ``image``, ``table``.

    Example:
        >>> from thot.tools.ingest.document_index import infer_data_kind
        >>> infer_data_kind({'title': 'Carte IGN', 'metadata': {'file_type': 'geojson'}})
        'carte'
        >>> infer_data_kind({'title': 'Note', 'metadata': {'file_type': 'pdf'}})
        'texte'
    """
    fmt = extract_doc_format(document)
    ext = f".{fmt}" if fmt else ""
    hay = _haystack(document)
    if any(token in hay for token in _LANDSCAPE_HINTS):
        return KIND_LANDSCAPE
    if ext in _MAP_EXT or any(token in hay for token in _MAP_HINTS):
        return KIND_MAP
    if ext in _TABLE_EXT:
        return KIND_TABLE
    if ext in _IMAGE_EXT:
        return KIND_IMAGE
    return KIND_TEXT


def extract_location_tags(
    document: dict[str, Any], *, limit: int = 16
) -> list[str]:
    """Location tags from NER (GPE / LOC / location).

    Example:
        >>> from thot.tools.ingest.document_index import extract_location_tags
        >>> extract_location_tags({
        ...     'content_ner': [{'text': 'Suez', 'label': 'location'}],
        ... })
        ['Suez']
    """
    values = [
        _text_of(span)
        for span in _ner_spans(document)
        if _label_of(span) in _LOCATION_LABELS
    ]
    meta = _metadata(document)
    for key in ("location", "place", "country", "city"):
        if meta.get(key):
            values.append(str(meta.get(key)))
    return unique_strings(values, limit=limit)


def extract_time_tags(
    document: dict[str, Any], *, limit: int = 16
) -> list[str]:
    """Time tags from DATE NER and metadata.

    Example:
        >>> from thot.tools.ingest.document_index import extract_time_tags
        >>> extract_time_tags({
        ...     'content_ner': [{'text': '2024', 'label': 'DATE'}],
        ... })
        ['2024']
    """
    values = [
        _text_of(span)
        for span in _ner_spans(document)
        if _label_of(span) in _TIME_LABELS
    ]
    meta = _metadata(document)
    for key in ("date", "year", "published", "created"):
        if meta.get(key):
            values.append(str(meta.get(key)))
    return unique_strings(values, limit=limit)


def extract_auto_tags(
    document: dict[str, Any],
    *,
    extra: list[str] | None = None,
    limit: int = 24,
) -> list[str]:
    """Auto-detected tags: keywords, data kind, format, extras.

    Example:
        >>> from thot.tools.ingest.document_index import extract_auto_tags
        >>> tags = extract_auto_tags(
        ...     {'keywords': [{'text': 'AIS'}], 'dataset': 'osint'},
        ...     extra=['texte'],
        ... )
        >>> 'AIS' in tags and 'texte' in tags
        True
    """
    values: list[Any] = list(extra or [])
    for item in document.get("keywords") or []:
        if isinstance(item, dict):
            values.append(item.get("text") or item.get("keyword"))
        else:
            values.append(item)
    meta = _metadata(document)
    for key in ("tags", "labels", "topics"):
        raw = meta.get(key)
        if isinstance(raw, list):
            values.extend(raw)
        elif raw:
            values.append(raw)
    return unique_strings(values, limit=limit)


def document_body_text(
    document: dict[str, Any],
    chunk_texts: list[str],
    *,
    max_chars: int = 32000,
) -> str:
    """Title plus concatenated chunk/content text for BM25.

    Example:
        >>> from thot.tools.ingest.document_index import document_body_text
        >>> document_body_text({'title': 'A'}, ['hello world'])
        'A\\n\\nhello world'
    """
    title = str(document.get("title") or "").strip()
    content = document.get("content")
    if isinstance(content, list):
        body = " ".join(str(part) for part in content if part).strip()
    else:
        body = str(content or "").strip()
    if not body:
        body = "\n\n".join(text for text in chunk_texts if text).strip()
    text = f"{title}\n\n{body}".strip() if title else body
    return text[: max(256, int(max_chars))]


def simhash_hex(value: int) -> str:
    """16-character hex fingerprint.

    Example:
        >>> from thot.tools.ingest.document_index import simhash_hex
        >>> simhash_hex(255)
        '00000000000000ff'
    """
    return f"{int(value) & ((1 << 64) - 1):016x}"


def simhash_prefix(value: int, *, bits: int = 16) -> int:
    """High bits of a 64-bit simhash for Vespa prefix filter.

    Example:
        >>> from thot.tools.ingest.document_index import simhash_prefix
        >>> simhash_prefix(0xABCD << 48, bits=16) == 0xABCD
        True
    """
    width = max(1, min(32, int(bits)))
    shift = 64 - width
    return (int(value) >> shift) & ((1 << width) - 1)


def mean_dense(vectors: list[list[float]], dim: int) -> list[float]:
    """Mean-pool chunk dense embeddings to one document vector.

    Example:
        >>> from thot.tools.ingest.document_index import mean_dense
        >>> mean_dense([[1.0, 3.0], [3.0, 1.0]], 2)
        [2.0, 2.0]
    """
    size = max(1, int(dim))
    if not vectors:
        return [0.0] * size
    acc = [0.0] * size
    for vec in vectors:
        for index, value in enumerate(vec[:size]):
            acc[index] += float(value)
    count = float(len(vectors))
    return [item / count for item in acc]


def merge_sparse(maps: list[dict[str, float]]) -> dict[str, float]:
    """Union sparse maps, keeping the max weight per token.

    Example:
        >>> from thot.tools.ingest.document_index import merge_sparse
        >>> merge_sparse([{'a': 0.2}, {'a': 0.9, 'b': 0.1}])
        {'a': 0.9, 'b': 0.1}
    """
    out: dict[str, float] = {}
    for mapping in maps:
        for token, weight in mapping.items():
            value = float(weight)
            prev = out.get(token)
            if prev is None or value > prev:
                out[token] = value
    return out


def pick_near_duplicate(
    fingerprint: int,
    candidates: list[dict[str, Any]],
    *,
    source_ref: str,
    max_hamming: int = 3,
) -> str:
    """Return ``source_ref`` of a near-duplicate corpus_doc, else ``\"\"``.

    Example:
        >>> from thot.tools.ingest.document_index import pick_near_duplicate
        >>> pick_near_duplicate(0b1111, [
        ...     {'source_ref': 'other', 'simhash_hex': '000000000000000f'},
        ... ], source_ref='self')
        'other'
        >>> pick_near_duplicate(0b1111, [
        ...     {'source_ref': 'self', 'simhash_hex': '000000000000000f'},
        ... ], source_ref='self')
        ''
    """
    self_ref = (source_ref or "").strip()
    limit = max(0, int(max_hamming))
    for row in candidates:
        other = str(row.get("source_ref") or "").strip()
        if not other or other == self_ref:
            continue
        hex_value = str(row.get("simhash_hex") or "").strip()
        try:
            existing = int(hex_value, 16) if hex_value else 0
        except ValueError:
            continue
        if hamming_distance(fingerprint, existing) <= limit:
            return other
    return ""


@dataclass(frozen=True)
class DocumentIndexMeta:
    """Extracted document-level tags and fingerprint.

    Example:
        >>> from thot.tools.ingest.document_index import DocumentIndexMeta
        >>> meta = DocumentIndexMeta.from_document(
        ...     {'source_doc_id': 'd1', 'title': 'Note', 'dataset': 'osint'},
        ...     ['hello world from the analyst desk'],
        ... )
        >>> meta.data_kind
        'texte'
        >>> meta.document_id == meta.document_id
        True
    """

    document_id: str
    source_ref: str
    title: str
    author: str
    collection: str
    doc_format: str
    data_kind: str
    location_tags: list[str] = field(default_factory=list)
    time_tags: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    doc_text: str = ""
    simhash: int = 0
    simhash_hex: str = ""
    simhash_prefix: int = 0

    @classmethod
    def from_document(
        cls,
        document: dict[str, Any],
        chunk_texts: list[str],
        *,
        prefix_bits: int = 16,
        max_doc_text_chars: int = 32000,
    ) -> DocumentIndexMeta:
        """Build metadata from a pipeline document and chunk texts.

        Example:
            >>> from thot.tools.ingest.document_index import DocumentIndexMeta
            >>> meta = DocumentIndexMeta.from_document(
            ...     {'source_doc_id': 'x', 'title': 'T'}, ['body'],
            ... )
            >>> meta.title
            'T'
        """
        source_ref = str(
            document.get("source_doc_id") or document.get("source") or ""
        )
        kind = infer_data_kind(document)
        fmt = extract_doc_format(document)
        collection = extract_collection(document)
        author = extract_author(document)
        locations = extract_location_tags(document)
        times = extract_time_tags(document)
        extras = [kind, fmt, collection]
        tags = extract_auto_tags(document, extra=extras)
        body = document_body_text(
            document, chunk_texts, max_chars=max_doc_text_chars
        )
        fingerprint = simhash64(body)
        return cls(
            document_id=corpus_doc_docid(source_ref),
            source_ref=source_ref,
            title=str(document.get("title") or "").strip(),
            author=author,
            collection=collection,
            doc_format=fmt,
            data_kind=kind,
            location_tags=locations,
            time_tags=times,
            tags=tags,
            doc_text=body,
            simhash=fingerprint,
            simhash_hex=simhash_hex(fingerprint),
            simhash_prefix=simhash_prefix(fingerprint, bits=prefix_bits),
        )


def build_corpus_doc_fields(
    meta: DocumentIndexMeta,
    *,
    dense: list[float],
    sparse: dict[str, float],
    embedding_dim: int,
    chunk_ids: list[str],
    ontology_concept_ids: list[str],
    ontology_rel_keys: list[str],
    duplicate_of: str = "",
) -> dict[str, Any]:
    """Vespa fields for one ``corpus_doc``.

    Example:
        >>> from thot.tools.ingest.document_index import (
        ...     DocumentIndexMeta, build_corpus_doc_fields,
        ... )
        >>> meta = DocumentIndexMeta.from_document(
        ...     {'source_doc_id': 'd1', 'title': 'T'}, ['hello'],
        ... )
        >>> fields = build_corpus_doc_fields(
        ...     meta, dense=[0.1, 0.2], sparse={'1': 0.5},
        ...     embedding_dim=2, chunk_ids=['d1#c0'],
        ...     ontology_concept_ids=['C1'], ontology_rel_keys=[],
        ... )
        >>> fields['document_id'] == meta.document_id
        True
        >>> fields['chunk_count']
        1
    """
    import time

    from thot.tools.search.bge_m3 import (
        vespa_dense_tensor,
        vespa_sparse_tensor,
    )

    return {
        "source_ref": sanitize_vespa_string(meta.source_ref),
        "document_id": meta.document_id,
        "title": sanitize_vespa_string(meta.title),
        "doc_text": sanitize_vespa_string(meta.doc_text),
        "author": sanitize_vespa_string(meta.author),
        "collection": sanitize_vespa_string(meta.collection),
        "doc_format": sanitize_vespa_string(meta.doc_format),
        "data_kind": sanitize_vespa_string(meta.data_kind),
        "location_tags": [
            sanitize_vespa_string(tag) for tag in meta.location_tags
        ],
        "time_tags": [sanitize_vespa_string(tag) for tag in meta.time_tags],
        "tags": [sanitize_vespa_string(tag) for tag in meta.tags],
        "simhash_hex": meta.simhash_hex,
        "simhash_prefix": int(meta.simhash_prefix),
        "duplicate_of": sanitize_vespa_string(duplicate_of),
        "ontology_concept_ids": [
            sanitize_vespa_string(cid) for cid in ontology_concept_ids if cid
        ],
        "ontology_rel_keys": [
            sanitize_vespa_string(key) for key in ontology_rel_keys if key
        ],
        "chunk_ids": [sanitize_vespa_string(cid) for cid in chunk_ids if cid],
        "chunk_count": len(chunk_ids),
        "dense_vector": vespa_dense_tensor(dense, embedding_dim),
        "sparse_vector": vespa_sparse_tensor(sparse),
        "freshness_ttl_seconds": 0,
        "pinned": False,
        "doc_timestamp": int(time.time()),
        "source_type": "ingest",
    }
