"""Title: User workspace unit tests

Author: Eric Blaudez

Copyright (c) 2026 Thales
Licensed under the MIT License.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from thot.tools.ingest.user_workspace import (
    UserWorkspace,
    sanitize_relative_path,
)


def test_sanitize_relative_path_rejects_traversal():
    with pytest.raises(ValueError):
        sanitize_relative_path("../secret")
    with pytest.raises(ValueError):
        sanitize_relative_path("/abs")
    assert sanitize_relative_path("reports/a.md") == "reports/a.md"


def test_user_workspace_write_list_delete(tmp_path: Path):
    ws = UserWorkspace("analyst@tkeir", root=tmp_path)
    ws.mkdir("reports")
    record = ws.write_file(
        "reports/note.md",
        b"# Hello\n",
        content_type="text/markdown",
        ingest_id="01TEST",
    )
    assert record.source_ref.startswith("user:analyst@tkeir:")
    listing = ws.list_dir("reports")
    assert listing["entries"][0]["name"] == "note.md"
    assert listing["entries"][0]["status"] == "pending"
    removed = ws.delete_file("reports/note.md")
    assert removed is not None
    assert ws.list_dir("reports")["entries"] == []


def test_user_workspace_copy_provenance(tmp_path: Path):
    source = UserWorkspace("analyst", root=tmp_path)
    target = UserWorkspace("commander", root=tmp_path)
    source.write_file(
        "wiki/eagle.md", b"# Eagle\n", content_type="text/markdown"
    )
    content = source.read_file_bytes("wiki/eagle.md")
    dest = target.write_file(
        "received/analyst/eagle.md",
        content,
        content_type="text/markdown",
        status="pending",
        copied_from_user="analyst",
        copied_from_path="wiki/eagle.md",
        copied_from_source_ref=source.source_ref_for("wiki/eagle.md"),
    )
    assert dest.source_ref.startswith("user:commander:")
    assert dest.copied_from_user == "analyst"
    listing = target.list_dir("received/analyst")
    assert listing["entries"][0]["copied_from_user"] == "analyst"
    assert listing["entries"][0]["status"] == "pending"


def test_user_workspace_migrates_inbox_to_received(tmp_path: Path):
    target = UserWorkspace("commander", root=tmp_path)
    # Seed a legacy inbox tree + catalog without write_file (which remaps
    # inbox/ → received/ for new writes).
    legacy = target.files_dir / "inbox" / "analyst" / "report.md"
    legacy.parent.mkdir(parents=True, exist_ok=True)
    legacy.write_bytes(b"# Report\n")
    target.user_dir.mkdir(parents=True, exist_ok=True)
    target.catalog_path.write_text(
        json.dumps(
            {
                "user_space": "commander",
                "files": {
                    "inbox/analyst/report.md": {
                        "path": "inbox/analyst/report.md",
                        "source_ref": "user:commander:inbox/analyst/report.md",
                        "status": "pending",
                        "size_bytes": 9,
                        "content_type": "text/markdown",
                        "copied_from_user": "analyst",
                        "copied_from_path": "reports/report.md",
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    again = UserWorkspace("commander", root=tmp_path)
    again.ensure_layout()
    assert (again.files_dir / "received" / "analyst" / "report.md").is_file()
    assert again.get_record("received/analyst/report.md") is not None
    assert again.get_record("inbox/analyst/report.md") is None
