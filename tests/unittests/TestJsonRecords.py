"""Unit tests for JSON record → markdown ingest helpers."""

from __future__ import annotations

import json

from thot.tools.ingest.json_records import (
    extract_record_concepts,
    load_and_split,
    record_to_markdown,
    source_name,
    split_record_documents,
    workspace_markdown_files_from_json,
)

SAMPLE = {
    "dataset": {"name": "demo"},
    "records": [
        {
            "doc_id": "C2-202606-0001",
            "title": "OSINT Report - Suez",
            "text": "Cautious calm around Suez Gulf Approach.",
            "domain": "OSINT_SOCMINT",
            "classification": "UNCLASSIFIED",
            "location": {"country": "Egypt", "mgrs": "36RVT70864126"},
            "tags": ["maritime", "suez"],
        }
    ],
}


def test_source_name_uses_filename_and_doc_id():
    assert (
        source_name("c2_middle_east_multi_source_1000_v3_en.json", "C2-1")
        == "c2_middle_east_multi_source_1000_v3_en/C2-1"
    )


def test_record_to_markdown_includes_attributes():
    md = record_to_markdown(SAMPLE["records"][0], source="demo/C2-1")
    assert md.startswith("# OSINT Report - Suez\n")
    # Body text comes immediately after the title (before Information).
    assert (
        "\n\nCautious calm around Suez Gulf Approach.\n\n## Information\n"
        in md
    )
    assert "**domain:** OSINT_SOCMINT" in md
    assert "Egypt" in md
    assert "**source:**" in md
    assert "Structured attributes" not in md
    assert "## Report" not in md


def test_extract_concepts_skips_title_and_text():
    concepts = extract_record_concepts(SAMPLE["records"][0])
    joined = " ".join(concepts)
    assert "OSINT_SOCMINT" in joined or "DOMAIN:OSINT_SOCMINT" in joined
    assert "Cautious calm" not in joined
    assert "OSINT Report - Suez" not in joined


def test_split_and_load():
    docs = split_record_documents(
        SAMPLE,
        filename="c2_middle_east_multi_source_1000_v3_en.json",
        limit=1,
    )
    assert len(docs) == 1
    doc = docs[0]
    assert doc["source_doc_id"] == (
        "c2_middle_east_multi_source_1000_v3_en/C2-202606-0001"
    )
    assert doc["filename"].endswith(".md")
    assert doc["record_concept_ids"]
    # Domain-agnostic metadata: all non-narrative fields, not an OSINT allowlist.
    assert doc["metadata"]["classification"] == "UNCLASSIFIED"
    assert doc["metadata"]["domain"] == "OSINT_SOCMINT"
    assert doc["metadata"]["location"]["country"] == "Egypt"
    assert doc["metadata"]["tags"] == ["maritime", "suez"]
    # title is an ingest promo field; narrative body is excluded
    assert doc["metadata"]["title"] == "OSINT Report - Suez"
    assert "text" not in doc["metadata"]

    loaded = load_and_split(
        json.dumps(SAMPLE).encode(),
        filename="demo.json",
        limit=1,
    )
    assert loaded[0]["doc_id"] == "C2-202606-0001"


def test_split_metadata_keeps_enterprise_fields():
    payload = {
        "records": [
            {
                "doc_id": "ENT-1",
                "title": "Sanctions note",
                "text": "Open-source filing.",
                "kri_ref": "KRI-02",
                "jurisdiction": "Nicosia",
                "primary_entity": "DESERT FALCON",
                "domain": "OPEN_SOURCE_ANALYTICS",
            }
        ]
    }
    doc = split_record_documents(payload, filename="enterprise.json")[0]
    assert doc["metadata"]["kri_ref"] == "KRI-02"
    assert doc["metadata"]["jurisdiction"] == "Nicosia"
    assert doc["metadata"]["primary_entity"] == "DESERT FALCON"
    assert doc["metadata"]["doc_type"] == "OPEN_SOURCE_ANALYTICS"
    assert "text" not in doc["metadata"]


def test_workspace_markdown_files_from_json():
    files = workspace_markdown_files_from_json(
        json.dumps(SAMPLE).encode(),
        filename="user_j2_analyst.json",
        directory="imports",
    )
    assert files is not None
    assert len(files) == 1
    assert files[0]["path"] == "imports/user_j2_analyst/C2-202606-0001.md"
    assert files[0]["doc_id"] == "C2-202606-0001"
    assert files[0]["markdown"].startswith("# OSINT Report - Suez\n")

    assert (
        workspace_markdown_files_from_json(
            b'{"not": "a corpus"}',
            filename="other.json",
        )
        is None
    )
