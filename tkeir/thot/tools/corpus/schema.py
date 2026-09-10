"""Title: Record-oriented corpus schema for ingest.

Shape taken from the OSINT C2 compilation and consumed by
``POST /ingest/json-records`` / ``thot.tools.ingest.json_records``:

``{"dataset": {…}, "records": [{…}, …]}``.

Each record **must** carry ``doc_id``, ``title``, and ``text``. Other C2
fields (classification, location, tags, …) are optional extras.

Author: Eric Blaudez

Copyright (c) 2026 Thales
Licensed under the MIT License.
"""

from __future__ import annotations

from typing import Any, Mapping, TypedDict

REQUIRED_RECORD_FIELDS: tuple[str, str, str] = (
    "doc_id",
    "title",
    "text",
)

# Optional record keys observed on the C2 OSINT compilation (not required).
OPTIONAL_RECORD_FIELDS: frozenset[str] = frozenset(
    {
        "dtg",
        "timestamp_utc",
        "precedence",
        "classification",
        "handling_caveats",
        "originator",
        "domain",
        "source_type",
        "source_category",
        "pir_ref",
        "language",
        "account",
        "location",
        "collection",
        "evaluation",
        "correlation",
        "post_time_utc",
        "collection_time_utc",
        "reporting_latency_minutes",
        "tags",
    }
)

# Keys written on every generated ``dataset`` block.
DATASET_CORE_FIELDS: frozenset[str] = frozenset(
    {
        "name",
        "version",
        "generated_utc",
        "record_count",
        "languages",
    }
)


class DatasetBlock(TypedDict, total=False):
    """``dataset`` object on a record-oriented corpus.

    Example:
        >>> from thot.tools.corpus.schema import DatasetBlock
        >>> block: DatasetBlock = {"name": "demo"}
        >>> block["name"]
        'demo'
    """

    name: str
    version: str
    generated_utc: str
    record_count: int
    languages: list[str]
    note: str
    classification_of_compilation: str
    coverage_window_utc: dict[str, str]
    standards: dict[str, str]
    pir_register: dict[str, str]


class RecordBlock(TypedDict, total=False):
    """One corpus record. ``doc_id``, ``title``, ``text`` are required.

    Example:
        >>> from thot.tools.corpus.schema import RecordBlock
        >>> row: RecordBlock = {"doc_id": "1", "title": "T", "text": "b"}
        >>> row["doc_id"]
        '1'
    """

    doc_id: str
    title: str
    text: str


class RecordCorpus(TypedDict):
    """Top-level record-oriented corpus document.

    Example:
        >>> from thot.tools.corpus.schema import RecordCorpus
        >>> payload: RecordCorpus = {
        ...     "dataset": {"name": "demo"},
        ...     "records": [{"doc_id": "1", "title": "T", "text": "b"}],
        ... }
        >>> payload["dataset"]["name"]
        'demo'
    """

    dataset: DatasetBlock
    records: list[dict[str, Any]]


def _nonempty_str(value: Any) -> str | None:
    """Return a stripped string or ``None`` when empty.

    Args:
        value: Any JSON-like scalar.

    Returns:
        Stripped text, or ``None`` when missing/blank.

    Example:
        >>> _nonempty_str("  a  ")
        'a'
        >>> _nonempty_str("") is None
        True
    """
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def validate_record(record: Mapping[str, Any], *, index: int) -> None:
    """Raise ``ValueError`` when a record misses a mandatory field.

    Args:
        record: Candidate record mapping.
        index: Position in ``records`` (used in the error message).

    Example:
        >>> validate_record(
        ...     {"doc_id": "1", "title": "T", "text": "body"}, index=0
        ... )
    """
    if not isinstance(record, Mapping):
        raise ValueError(f"records[{index}] must be an object")
    missing: list[str] = []
    for key in REQUIRED_RECORD_FIELDS:
        if _nonempty_str(record.get(key)) is None:
            missing.append(key)
    if missing:
        ident = _nonempty_str(record.get("doc_id")) or f"index {index}"
        raise ValueError(
            f"record {ident} missing mandatory field(s): "
            + ", ".join(missing)
        )


def validate_record_corpus(payload: Any) -> RecordCorpus:
    """Validate a ``{dataset, records}`` payload for JSON-record ingest.

    Args:
        payload: Parsed JSON object.

    Returns:
        The same mapping, typed as ``RecordCorpus``.

    Example:
        >>> validate_record_corpus(
        ...     {
        ...         "dataset": {"name": "demo"},
        ...         "records": [
        ...             {"doc_id": "1", "title": "T", "text": "body"}
        ...         ],
        ...     }
        ... )["dataset"]["name"]
        'demo'
    """
    if not isinstance(payload, dict):
        raise ValueError("corpus must be a JSON object")
    dataset = payload.get("dataset")
    if not isinstance(dataset, dict):
        raise ValueError("corpus.dataset must be an object")
    if _nonempty_str(dataset.get("name")) is None:
        raise ValueError("corpus.dataset.name is required")
    records = payload.get("records")
    if not isinstance(records, list):
        raise ValueError("corpus.records must be an array")
    seen: set[str] = set()
    for index, record in enumerate(records):
        if not isinstance(record, dict):
            raise ValueError(f"records[{index}] must be an object")
        validate_record(record, index=index)
        doc_id = str(record["doc_id"]).strip()
        if doc_id in seen:
            raise ValueError(f"duplicate doc_id: {doc_id}")
        seen.add(doc_id)
    return payload  # type: ignore[return-value]
