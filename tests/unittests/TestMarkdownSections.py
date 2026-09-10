"""Unit tests for markdown vs raw section splitting.

Author: Eric Blaudez

Copyright (c) 2026 Thales
Licensed under the MIT License.
"""

from __future__ import annotations

from thot.tasks.converters.MarkdownSections import (
    looks_like_markdown,
    markdown_to_content,
    text_to_content,
    unwrap_inline_markdown,
)
from thot.tasks.converters.RawTextConverter import RawTextConverter
from thot.tools.ingest.json_records import (
    record_to_markdown,
    split_record_documents,
)


def test_detects_markdown_headings_not_hashtags():
    assert looks_like_markdown("# Title\n\nHello.\n")
    assert not looks_like_markdown("Cautious calm around Suez.")
    assert not looks_like_markdown("See #Suez in the channel.")


def test_markdown_sections_and_subsections():
    source = (
        "# Report\n\n"
        "Intro paragraph.\n\n"
        "## Background\n\n"
        "The fleet is quiet.\n\n"
        "### Ports\n\n"
        "Suez is busy.\n"
    )
    title, blocks = markdown_to_content(source)
    assert title == "Report"
    assert blocks[0] == "Intro paragraph."
    assert blocks[1].startswith("Background")
    assert "The fleet is quiet." in blocks[1]
    assert "Background / Ports" in blocks[2]
    assert "Suez is busy." in blocks[2]


def test_raw_paragraph_split():
    title, blocks, fmt = text_to_content("One.\n\nTwo.\n")
    assert fmt == "raw"
    assert title == ""
    assert blocks == ["One.", "Two."]


def test_unwrap_information_bullets():
    assert unwrap_inline_markdown("- **domain:** OSINT") == "domain: OSINT"


def test_raw_converter_splits_record_markdown():
    record = {
        "doc_id": "C2-1",
        "title": "OSINT Report - Suez",
        "text": (
            "Cautious calm.\n\n"
            "## Ports\n\n"
            "Suez Gulf Approach is watched."
        ),
        "domain": "OSINT_SOCMINT",
        "location": {"country": "Egypt"},
    }
    md = record_to_markdown(record, source="demo/C2-1")
    doc = RawTextConverter.convert(md.encode("utf-8"), "file://c.md")
    assert doc["title"] == "OSINT Report - Suez"
    joined = "\n".join(doc["content"])
    assert "Cautious calm." in joined
    assert "Ports" in joined
    assert "Suez Gulf Approach is watched." in joined
    assert any("Information" in block for block in doc["content"])
    assert doc["conversion-info"]["text-format"] == "markdown"
    assert doc["conversion-info"]["content-blocks"] >= 3


def test_json_records_stamp_text_format():
    raw_docs = split_record_documents(
        {
            "records": [
                {
                    "doc_id": "r1",
                    "title": "T",
                    "text": "Plain prose only.",
                }
            ]
        },
        filename="c.json",
    )
    assert raw_docs[0]["metadata"]["text_format"] == "raw"
    md_docs = split_record_documents(
        {
            "records": [
                {
                    "doc_id": "r2",
                    "title": "T",
                    "text": "Intro.\n\n## Ports\n\nBusy.\n",
                }
            ]
        },
        filename="c.json",
    )
    assert md_docs[0]["metadata"]["text_format"] == "markdown"
