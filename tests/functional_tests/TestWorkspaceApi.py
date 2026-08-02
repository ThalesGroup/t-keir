"""Functional HTTP contracts for My-files / workspace endpoints."""

from __future__ import annotations

from io import BytesIO


def test_workspace_tree_lists_root(ingest_harness):
    client, _root = ingest_harness
    response = client.get("/workspace/tree")
    assert response.status_code == 200
    body = response.json()
    assert "user_space" in body
    assert isinstance(body.get("entries"), list)


def test_workspace_mkdir_and_upload_without_index(ingest_harness):
    client, _root = ingest_harness
    mkdir = client.post("/workspace/mkdir", json={"path": "func-smoke"})
    assert mkdir.status_code == 200
    assert mkdir.json()["kind"] == "directory"

    upload = client.post(
        "/workspace/upload",
        files={
            "file": (
                "note.md",
                BytesIO(b"# functional workspace note\n"),
                "text/markdown",
            )
        },
        data={"path": "func-smoke/note.md", "index": "false"},
    )
    assert upload.status_code == 202
    body = upload.json()
    assert body["path"] == "func-smoke/note.md"
    assert body.get("ingest_id") in (None, "")
    assert body.get("status") == "pending"


def test_workspace_status_batch(ingest_harness):
    client, _root = ingest_harness
    client.post("/workspace/mkdir", json={"path": "func-status"})
    client.post(
        "/workspace/upload",
        files={
            "file": ("a.md", BytesIO(b"a\n"), "text/markdown"),
        },
        data={"path": "func-status/a.md", "index": "false"},
    )
    status = client.post(
        "/workspace/status",
        json={"paths": ["func-status/a.md", "missing.md"]},
    )
    assert status.status_code == 200
    body = status.json()
    assert body["total"] == 2
    assert "done" in body
    assert isinstance(body.get("files"), list)


def test_workspace_file_rejects_traversal(ingest_harness):
    client, _root = ingest_harness
    response = client.get("/workspace/file", params={"path": "../etc/passwd"})
    assert response.status_code == 400


def test_workspace_file_missing_returns_404(ingest_harness):
    client, _root = ingest_harness
    response = client.get(
        "/workspace/file", params={"path": "no-such-file.md"}
    )
    assert response.status_code == 404


def test_workspace_index_unknown_path_reports_error(ingest_harness):
    client, _root = ingest_harness
    response = client.post(
        "/workspace/index",
        json={"paths": ["definitely-missing.md"]},
    )
    # Endpoint returns 202 with per-path errors, or 400 for empty/invalid.
    assert response.status_code in {202, 400}
    if response.status_code == 202:
        body = response.json()
        assert body.get("queued_count", 0) == 0
        assert body.get("errors")
