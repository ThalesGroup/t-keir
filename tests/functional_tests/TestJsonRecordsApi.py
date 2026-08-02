"""Functional HTTP contracts for admin JSON-records corpus ingest."""

from __future__ import annotations

import json
from io import BytesIO


def _tiny_corpus() -> bytes:
    return json.dumps(
        {
            "records": [
                {
                    "doc_id": "FUNC-0001",
                    "title": "Functional smoke record",
                    "text": "Short body for JSON-records ingest.",
                    "classification": "UNCLASSIFIED",
                }
            ]
        }
    ).encode("utf-8")


def test_json_records_accepts_split_corpus(ingest_harness):
    client, _root = ingest_harness
    response = client.post(
        "/ingest/json-records",
        files={
            "file": (
                "corpus.json",
                BytesIO(_tiny_corpus()),
                "application/json",
            )
        },
        data={
            "options": json.dumps(
                {
                    "split_records": True,
                    "index_target": "global",
                    "limit": 1,
                }
            )
        },
    )
    assert response.status_code == 202, response.text[:400]
    body = response.json()
    assert body["queued"] >= 1
    assert body["record_count"] >= 1
    assert body.get("batch_id")
    assert isinstance(body.get("jobs"), list)
    assert body["jobs"][0]["ingest_id"]


def test_json_records_json_body_dataset_path_optional_upload(ingest_harness):
    """Multipart-less path still validates options when dataset absent."""
    client, _root = ingest_harness
    response = client.post(
        "/ingest/json-records",
        json={
            "split_records": True,
            "index_target": "global",
            "limit": 1,
        },
    )
    # No file and no dataset_path → 400.
    assert response.status_code == 400


def test_document_multipart_accept(ingest_harness):
    client, _root = ingest_harness
    response = client.post(
        "/ingest/document",
        files={
            "file": ("note.txt", BytesIO(b"hello functional\n"), "text/plain")
        },
    )
    assert response.status_code == 202
    body = response.json()
    assert body["ingest_id"]
    status = client.get(f"/ingest/status/{body['ingest_id']}")
    assert status.status_code == 200
    assert status.json()["status"] in {
        "pending",
        "running",
        "succeeded",
        "failed",
        "noop",
    }
