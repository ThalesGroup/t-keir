"""Unit tests for record-oriented corpus generation from markdown.

Author: Eric Blaudez

Copyright (c) 2026 Thales
Licensed under the MIT License.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from thot.tools.corpus.builder import (
    corpus_from_markdown_dir,
    corpus_from_source_dir,
    write_record_corpus,
)
from thot.tools.corpus.cli import main
from thot.tools.corpus.markdown_records import parse_markdown_record
from thot.tools.corpus.schema import validate_record_corpus
from thot.tools.ingest.json_records import (
    is_record_corpus,
    record_to_markdown,
    split_record_documents,
)


def test_parse_heading_and_body():
    record = parse_markdown_record(
        "# OSINT Report - Suez\n\nCautious calm.\n",
        default_id="sitrep",
    )
    assert record == {
        "doc_id": "sitrep",
        "title": "OSINT Report - Suez",
        "text": "Cautious calm.",
    }


def test_frontmatter_overrides_and_extras():
    raw = (
        "---\n"
        "doc_id: C2-0001\n"
        "classification: UNCLASSIFIED\n"
        "location:\n"
        "  country: Egypt\n"
        "---\n"
        "# Front title\n\n"
        "Body text.\n"
    )
    record = parse_markdown_record(raw, default_id="ignored")
    assert record["doc_id"] == "C2-0001"
    assert record["title"] == "Front title"
    assert record["text"] == "Body text."
    assert record["classification"] == "UNCLASSIFIED"
    assert record["location"]["country"] == "Egypt"


def test_information_section_roundtrip():
    source = {
        "doc_id": "C2-1",
        "title": "OSINT Report - Suez",
        "text": "Cautious calm around Suez.",
        "domain": "OSINT_SOCMINT",
        "classification": "UNCLASSIFIED",
        "location": {"country": "Egypt", "mgrs": "36RVT70864126"},
    }
    md = record_to_markdown(source, source="demo/C2-1")
    record = parse_markdown_record(md, default_id="fallback")
    assert record["doc_id"] == "C2-1"
    assert record["title"] == "OSINT Report - Suez"
    assert record["text"] == "Cautious calm around Suez."
    assert record["domain"] == "OSINT_SOCMINT"
    assert record["classification"] == "UNCLASSIFIED"
    assert record["location"]["country"] == "Egypt"
    assert "source" not in record


def test_corpus_from_markdown_dir(tmp_path: Path):
    (tmp_path / "nested").mkdir()
    (tmp_path / "alpha.md").write_text(
        "# Alpha\n\nFirst document.\n",
        encoding="utf-8",
    )
    (tmp_path / "nested" / "bravo.md").write_text(
        "---\ndoc_id: BR-1\n---\n# Bravo\n\nSecond document.\n",
        encoding="utf-8",
    )
    payload = corpus_from_markdown_dir(
        tmp_path,
        name="c2_from_md",
        version="3.0-test",
        note="Simulated data.",
        generated_utc="2026-07-28T06:00:00Z",
    )
    assert payload["dataset"]["name"] == "c2_from_md"
    assert payload["dataset"]["version"] == "3.0-test"
    assert payload["dataset"]["record_count"] == 2
    assert payload["dataset"]["generated_utc"] == "2026-07-28T06:00:00Z"
    assert payload["dataset"]["languages"] == ["en"]
    assert payload["dataset"]["note"] == "Simulated data."
    ids = {row["doc_id"] for row in payload["records"]}
    assert ids == {"alpha", "BR-1"}
    by_id = {row["doc_id"]: row for row in payload["records"]}
    assert by_id["alpha"]["title"] == "Alpha"
    assert by_id["alpha"]["text"] == "First document."
    assert set(by_id["alpha"]) == {"doc_id", "title", "text"}
    validate_record_corpus(payload)
    assert is_record_corpus(payload)
    docs = split_record_documents(payload, filename="c2_from_md.json")
    assert len(docs) == 2
    sources = {doc["source_doc_id"] for doc in docs}
    assert sources == {"c2_from_md/alpha", "c2_from_md/BR-1"}


def test_missing_text_fails(tmp_path: Path):
    (tmp_path / "empty.md").write_text("# Only title\n", encoding="utf-8")
    with pytest.raises(ValueError, match="text"):
        corpus_from_markdown_dir(tmp_path, name="bad")


def test_skip_empty(tmp_path: Path):
    (tmp_path / "empty.md").write_text("# Only title\n", encoding="utf-8")
    (tmp_path / "ok.md").write_text("# Ok\n\nBody.\n", encoding="utf-8")
    payload = corpus_from_markdown_dir(tmp_path, name="ok", skip_empty=True)
    assert payload["dataset"]["record_count"] == 1
    assert payload["records"][0]["doc_id"] == "ok"


def test_validate_requires_dataset_and_mandatory_fields():
    with pytest.raises(ValueError, match="dataset"):
        validate_record_corpus({"records": []})
    with pytest.raises(ValueError, match="title"):
        validate_record_corpus(
            {
                "dataset": {"name": "x"},
                "records": [{"doc_id": "1", "text": "t"}],
            }
        )


def test_cli_writes_json(tmp_path: Path):
    md_dir = tmp_path / "md"
    md_dir.mkdir()
    (md_dir / "r1.md").write_text("# One\n\nText one.\n", encoding="utf-8")
    out = tmp_path / "corpus.json"
    assert (
        main(
            [
                "--input-dir",
                str(md_dir),
                "--output",
                str(out),
                "--name",
                "cli-demo",
            ]
        )
        == 0
    )
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["dataset"]["name"] == "cli-demo"
    assert payload["records"][0]["doc_id"] == "r1"
    assert payload["records"][0]["title"] == "One"
    assert payload["records"][0]["text"] == "Text one."


def test_write_record_corpus_roundtrip(tmp_path: Path):
    dest = tmp_path / "out.json"
    path = write_record_corpus(
        {
            "dataset": {"name": "d"},
            "records": [{"doc_id": "1", "title": "T", "text": "b"}],
        },
        dest,
    )
    loaded = json.loads(path.read_text(encoding="utf-8"))
    assert loaded["dataset"]["name"] == "d"
    validate_record_corpus(loaded)


def test_convert_source_tree_preserves_layout(tmp_path: Path):
    from thot.tools.corpus.convert_tree import convert_source_tree

    src = tmp_path / "src"
    (src / "reports").mkdir(parents=True)
    (src / "tables").mkdir()
    (src / "reports" / "note.txt").write_text(
        "Hello from a text file.\n",
        encoding="utf-8",
    )
    (src / "tables" / "people.csv").write_text(
        "Name,Age\nAda,36\n",
        encoding="utf-8",
    )
    (src / ".hidden").mkdir()
    (src / ".hidden" / "secret.txt").write_text("nope\n", encoding="utf-8")
    dest = tmp_path / "md"
    result = convert_source_tree(src, dest, ocr_config={"enabled": False})
    names = sorted(
        path.relative_to(dest).as_posix() for path in result.written
    )
    assert names == ["reports/note.txt.md", "tables/people.csv.md"]
    note = (dest / "reports" / "note.txt.md").read_text(encoding="utf-8")
    assert "Hello from a text file." in note
    assert "**source_format:** txt" in note
    assert "**file_type:** raw" in note
    assert "**source_path:** `reports/note.txt`" in note


def test_corpus_from_source_dir_json_records(tmp_path: Path):
    src = tmp_path / "data"
    src.mkdir()
    (src / "alpha.txt").write_text(
        "First converted document.\n", encoding="utf-8"
    )
    dest = tmp_path / "markdown"
    payload = corpus_from_source_dir(
        src,
        dest,
        name="geomix",
        ocr_config={"enabled": False},
        generated_utc="2026-09-10T08:00:00Z",
    )
    assert payload["dataset"]["name"] == "geomix"
    assert payload["dataset"]["record_count"] == 1
    record = payload["records"][0]
    assert record["doc_id"] == "alpha.txt"
    assert "First converted document." in record["text"]
    assert record["source_format"] == "txt"
    assert record["file_type"] == "raw"
    assert record["source_path"] == "alpha.txt"
    validate_record_corpus(payload)
    assert is_record_corpus(payload)


def test_cli_converts_mixed_tree(tmp_path: Path):
    src = tmp_path / "mixed"
    (src / "docs").mkdir(parents=True)
    (src / "docs" / "readme.txt").write_text(
        "Mixed tree body.\n", encoding="utf-8"
    )
    md_dir = tmp_path / "out-md"
    out = tmp_path / "corpus.json"
    assert (
        main(
            [
                "--input-dir",
                str(src),
                "--markdown-dir",
                str(md_dir),
                "--output",
                str(out),
                "--name",
                "mixed-demo",
                "--no-ocr",
            ]
        )
        == 0
    )
    assert (md_dir / "docs" / "readme.txt.md").is_file()
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["dataset"]["name"] == "mixed-demo"
    assert payload["records"][0]["doc_id"] == "docs/readme.txt"
    assert payload["records"][0]["source_format"] == "txt"


def test_corpus_from_image_becomes_record(tmp_path: Path):
    from io import BytesIO

    from PIL import Image

    src = tmp_path / "maps"
    src.mkdir()
    buf = BytesIO()
    Image.new("RGB", (256, 256), (12, 80, 200)).save(buf, format="PNG")
    (src / "chart.png").write_bytes(buf.getvalue())
    dest = tmp_path / "markdown"
    payload = corpus_from_source_dir(
        src,
        dest,
        name="images",
        ocr_config={"enabled": False, "analyze-images": True},
    )
    assert payload["dataset"]["record_count"] == 1
    record = payload["records"][0]
    assert record["doc_id"] == "chart.png"
    assert record["file_type"] == "image"
    assert record["source_format"] == "png"
    assert record["source_path"] == "chart.png"
    assert (dest / "chart.png.md").is_file()
    assert "Image analysis" in record["text"]
    assert "256x256" in record["text"]


def test_corpus_zip_nested_image_and_text(tmp_path: Path):
    import io
    import zipfile
    from io import BytesIO

    from PIL import Image

    src = tmp_path / "pack"
    src.mkdir()
    img = BytesIO()
    Image.new("RGB", (256, 256), "navy").save(img, format="PNG")
    archive = io.BytesIO()
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr("readme.txt", "Nested text body.")
        zf.writestr("photo.png", img.getvalue())
    (src / "bundle.zip").write_bytes(archive.getvalue())
    payload = corpus_from_source_dir(
        src,
        tmp_path / "markdown",
        name="archive",
        ocr_config={"enabled": False, "analyze-images": True},
    )
    record = payload["records"][0]
    assert record["file_type"] == "zip"
    assert "Nested text body." in record["text"]
    assert "Image analysis" in record["text"]
    assert "photo.png" in record["text"]


def test_cli_markdown_only_skips_convert(tmp_path: Path):
    md_dir = tmp_path / "md"
    md_dir.mkdir()
    (md_dir / "r1.md").write_text("# One\n\nText one.\n", encoding="utf-8")
    sibling = tmp_path / "md-markdown"
    out = tmp_path / "corpus.json"
    assert (
        main(
            [
                "--input-dir",
                str(md_dir),
                "--output",
                str(out),
                "--name",
                "cli-demo",
            ]
        )
        == 0
    )
    assert not sibling.exists()
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["records"][0]["doc_id"] == "r1"


def test_progress_formatters():
    from thot.tools.corpus.progress import (
        eta_seconds,
        format_bytes,
        format_duration,
        format_run_summary,
        RunStats,
    )

    assert format_duration(None) == "estimating"
    assert format_duration(12.4) == "12.4s"
    assert format_duration(65) == "1m 05s"
    assert eta_seconds(10.0, 5, 10) == 10.0
    assert eta_seconds(1.0, 1, 10) is None
    assert format_bytes(2048) == "2.0 KiB"
    text = format_run_summary(
        RunStats(
            label="convert",
            files_total=3,
            written=3,
            elapsed_seconds=1.5,
            workers_peak=4,
        )
    )
    assert "Corpus convert summary" in text
    assert "converted    : 3" in text
    assert "cached       : 0" in text


def test_adaptive_workers_plan_and_limiter():
    from pathlib import Path

    from thot.tools.corpus.adaptive import AdaptiveLimiter, plan_workers

    fixed = plan_workers([Path("a.txt"), Path("b.txt")], requested=1)
    assert fixed.initial == 1
    assert fixed.maximum == 1
    assert fixed.adaptive is False
    auto = plan_workers(
        [Path("a.txt")] * 12,
        requested=0,
        cpu_count=4,
        ocr_enabled=False,
        captions=False,
    )
    assert auto.adaptive is True
    assert auto.maximum >= auto.initial >= 1
    limiter = AdaptiveLimiter(initial=1, maximum=4, minimum=1)
    for _ in range(8):
        limiter.acquire()
        limiter.release(0.01, remaining=20)
    assert limiter.current > 1
    assert limiter.peak >= limiter.current
    assert limiter.grows >= 1


def test_convert_source_tree_parallel_progress(tmp_path: Path, caplog):
    import logging

    from thot.tools.corpus.convert_tree import convert_source_tree

    src = tmp_path / "src"
    src.mkdir()
    for index in range(6):
        (src / f"n{index}.txt").write_text(
            f"Document number {index}.\n", encoding="utf-8"
        )
    dest = tmp_path / "md"
    with caplog.at_level(logging.INFO):
        result = convert_source_tree(
            src,
            dest,
            ocr_config={"enabled": False},
            workers=2,
        )
    assert len(result.written) == 6
    assert result.stats.written == 6
    assert result.stats.files_total == 6
    assert result.stats.elapsed_seconds >= 0
    assert result.stats.workers_peak >= 1
    joined = caplog.text
    assert "elapsed" in joined
    assert "Corpus convert summary" in joined
    assert "workers" in joined


def test_cli_workers_flag(tmp_path: Path):
    src = tmp_path / "mixed"
    src.mkdir()
    (src / "a.txt").write_text("Alpha body.\n", encoding="utf-8")
    (src / "b.txt").write_text("Bravo body.\n", encoding="utf-8")
    md_dir = tmp_path / "out-md"
    out = tmp_path / "corpus.json"
    assert (
        main(
            [
                "--input-dir",
                str(src),
                "--markdown-dir",
                str(md_dir),
                "--output",
                str(out),
                "--name",
                "parallel-demo",
                "--no-ocr",
                "--workers",
                "2",
            ]
        )
        == 0
    )
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["dataset"]["record_count"] == 2


def test_cli_skips_blank_text_by_default(tmp_path: Path):
    md_dir = tmp_path / "md"
    md_dir.mkdir()
    (md_dir / "PORTRAYAL.XML.md").write_text(
        "# PORTRAYAL.XML\n\n## Information\n\n"
        "- **source_path:** `DISPLAY/PORTRAYAL.XML`\n",
        encoding="utf-8",
    )
    (md_dir / "ok.md").write_text("# Ok\n\nBody text.\n", encoding="utf-8")
    out = tmp_path / "corpus.json"
    assert (
        main(
            [
                "--input-dir",
                str(md_dir),
                "--output",
                str(out),
                "--name",
                "portrayal",
            ]
        )
        == 0
    )
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["dataset"]["record_count"] == 1
    assert payload["records"][0]["doc_id"] == "ok"


def test_cli_keep_empty_fails_on_blank_text(tmp_path: Path):
    md_dir = tmp_path / "md"
    md_dir.mkdir()
    (md_dir / "empty.md").write_text("# Only title\n", encoding="utf-8")
    out = tmp_path / "corpus.json"
    assert (
        main(
            [
                "--input-dir",
                str(md_dir),
                "--output",
                str(out),
                "--name",
                "bad",
                "--keep-empty",
            ]
        )
        == 1
    )
    assert not out.exists()


def test_convert_skips_existing_markdown_unless_forced(tmp_path: Path):
    from thot.tools.corpus.convert_tree import convert_source_tree

    src = tmp_path / "src"
    src.mkdir()
    source = src / "note.txt"
    source.write_text("Original body.\n", encoding="utf-8")
    dest = tmp_path / "md"
    first = convert_source_tree(
        src, dest, ocr_config={"enabled": False}, workers=1
    )
    sidecar = dest / "note.txt.md"
    assert first.written == [sidecar]
    assert first.cached == 0
    original = sidecar.read_text(encoding="utf-8")
    source.write_text(
        "Changed body that must not be converted.\n", encoding="utf-8"
    )
    second = convert_source_tree(
        src, dest, ocr_config={"enabled": False}, workers=1
    )
    assert second.written == []
    assert second.cached == 1
    assert sidecar.read_text(encoding="utf-8") == original
    third = convert_source_tree(
        src, dest, ocr_config={"enabled": False}, workers=1, force=True
    )
    assert third.cached == 0
    assert third.written == [sidecar]
    assert "Changed body" in sidecar.read_text(encoding="utf-8")


def test_corpus_from_source_dir_skips_cached_and_blank_text(tmp_path: Path):
    src = tmp_path / "src"
    src.mkdir()
    (src / "ok.txt").write_text("Keep this document.\n", encoding="utf-8")
    (src / "empty.txt").write_text("   \n", encoding="utf-8")
    dest = tmp_path / "md"
    first = corpus_from_source_dir(
        src,
        dest,
        name="cache-demo",
        ocr_config={"enabled": False},
        workers=1,
    )
    assert first["dataset"]["record_count"] == 1
    assert (dest / "ok.txt.md").is_file()
    assert (dest / "empty.txt.md").is_file()
    original = (dest / "ok.txt.md").read_text(encoding="utf-8")
    (src / "ok.txt").write_text(
        "Must not replace cached markdown.\n", encoding="utf-8"
    )
    second = corpus_from_source_dir(
        src,
        dest,
        name="cache-demo",
        ocr_config={"enabled": False},
        workers=1,
    )
    assert second["dataset"]["record_count"] == 1
    assert "Keep this document." in second["records"][0]["text"]
    assert (dest / "ok.txt.md").read_text(encoding="utf-8") == original
