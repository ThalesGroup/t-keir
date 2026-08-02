"""Title: Store

Filesystem-backed staging, jobs, DLQ, and idempotency index.

Author: Eric Blaudez

Copyright (c) 2026 Thales
Licensed under the MIT License.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from thot.action.models import utc_now_rfc3339
from thot.tools.ingest.fetch import write_upload
from thot.tools.ingest.models import IngestJob, IngestJobStatus, IngestManifest


def _atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    os.replace(tmp, path)


def _read_json(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise ValueError(f"Expected object in {path}")
    return data


class IngestStore:
    """Manage ``staging/``, ``jobs/``, ``dlq/``, and idempotency records."""

    def __init__(self, root: Path) -> None:
        """Bind the store to ``root``.

        Example:
            >>> import tempfile
            >>> from pathlib import Path
            >>> from thot.tools.ingest.store import IngestStore
            >>> with tempfile.TemporaryDirectory() as temp_dir:
            ...     store = IngestStore(Path(temp_dir))
            ...     store.root.name == Path(temp_dir).name
            True
        """
        self.root = root
        self.staging_dir = root / "staging"
        self.jobs_dir = root / "jobs"
        self.dlq_dir = root / "dlq"
        self.idempotency_path = root / "idempotency.json"

    def ensure_layout(self) -> None:
        """Create expected directories."""
        self.staging_dir.mkdir(parents=True, exist_ok=True)
        self.jobs_dir.mkdir(parents=True, exist_ok=True)
        self.dlq_dir.mkdir(parents=True, exist_ok=True)
        if not self.idempotency_path.exists():
            _atomic_write_json(self.idempotency_path, {"keys": {}})

    def staging_path(self, doc_id: str) -> Path:
        return self.staging_dir / doc_id

    def manifest_path(self, doc_id: str) -> Path:
        return self.staging_path(doc_id) / "ingest.manifest.json"

    def analyzed_document_path(self, doc_id: str) -> Path:
        return self.staging_path(doc_id) / "analyzed_document.json"

    def source_path(self, doc_id: str, filename: str) -> Path:
        return self.staging_path(doc_id) / filename

    def source_ref_index_path(self) -> Path:
        return self.root / "source_refs.json"

    def job_path(self, ingest_id: str) -> Path:
        return self.jobs_dir / f"{ingest_id}.json"

    def dlq_path(self, ingest_id: str) -> Path:
        return self.dlq_dir / f"{ingest_id}.json"

    def write_manifest(self, manifest: IngestManifest) -> Path:
        path = self.manifest_path(manifest.doc_id)
        _atomic_write_json(path, manifest.to_storage_dict())
        return path

    def read_manifest(self, doc_id: str) -> IngestManifest | None:
        path = self.manifest_path(doc_id)
        if not path.is_file():
            return None
        return IngestManifest.model_validate(_read_json(path))

    def write_job(self, job: IngestJob) -> Path:
        path = self.job_path(job.ingest_id)
        _atomic_write_json(path, job.model_dump(mode="json"))
        return path

    def read_job(self, ingest_id: str) -> IngestJob | None:
        path = self.job_path(ingest_id)
        if not path.is_file():
            return None
        return IngestJob.model_validate(_read_json(path))

    def update_job(
        self,
        ingest_id: str,
        *,
        status: IngestJobStatus | None = None,
        doc_id: str | None = None,
        manifest_path: str | None = None,
        error: str | None = None,
        noop: bool | None = None,
        user_space: str | None = None,
    ) -> IngestJob:
        job = self.read_job(ingest_id)
        if job is None:
            raise KeyError(f"Unknown ingest job: {ingest_id}")
        now = utc_now_rfc3339()
        payload = job.model_dump()
        if status is not None:
            payload["status"] = status.value
        if doc_id is not None:
            payload["doc_id"] = doc_id
        if manifest_path is not None:
            payload["manifest_path"] = manifest_path
        if error is not None:
            payload["error"] = error
        if noop is not None:
            payload["noop"] = noop
        if user_space is not None:
            payload["user_space"] = user_space
        payload["updated_at"] = now
        updated = IngestJob.model_validate(payload)
        self.write_job(updated)
        return updated

    def stage_bytes(
        self,
        doc_id: str,
        content: bytes,
        *,
        filename: str,
    ) -> Path:
        dest = self.source_path(doc_id, filename)
        write_upload(content, dest=dest)
        return dest

    def write_analyzed_document(
        self,
        doc_id: str,
        document: dict[str, Any],
        *,
        source_ref: str | None = None,
    ) -> Path:
        path = self.analyzed_document_path(doc_id)
        _atomic_write_json(path, document)
        if source_ref:
            self.put_source_ref_record(source_ref, doc_id=doc_id)
        return path

    def read_analyzed_document(self, doc_id: str) -> dict[str, Any] | None:
        path = self.analyzed_document_path(doc_id)
        if not path.is_file():
            return None
        return _read_json(path)

    def get_source_ref_record(self, source_ref: str) -> dict[str, Any] | None:
        path = self.source_ref_index_path()
        if not path.is_file():
            return None
        data = _read_json(path)
        refs = data.get("refs")
        if not isinstance(refs, dict):
            return None
        record = refs.get(source_ref)
        return record if isinstance(record, dict) else None

    def put_source_ref_record(self, source_ref: str, *, doc_id: str) -> None:
        self.ensure_layout()
        path = self.source_ref_index_path()
        if path.is_file():
            data = _read_json(path)
        else:
            data = {"refs": {}}
        refs = data.setdefault("refs", {})
        if not isinstance(refs, dict):
            refs = {}
            data["refs"] = refs
        refs[source_ref] = {
            "doc_id": doc_id,
            "updated_at": utc_now_rfc3339(),
        }
        _atomic_write_json(path, data)

    def read_analyzed_document_by_source_ref(
        self, source_ref: str
    ) -> dict[str, Any] | None:
        record = self.get_source_ref_record(source_ref)
        if not record:
            return None
        doc_id = record.get("doc_id")
        if not isinstance(doc_id, str) or not doc_id.strip():
            return None
        return self.read_analyzed_document(doc_id.strip())

    def get_idempotency_record(self, key: str) -> dict[str, Any] | None:
        if not self.idempotency_path.is_file():
            return None
        data = _read_json(self.idempotency_path)
        keys = data.get("keys")
        if not isinstance(keys, dict):
            return None
        record = keys.get(key)
        return record if isinstance(record, dict) else None

    def put_idempotency_record(
        self,
        key: str,
        *,
        doc_id: str,
        ingest_id: str,
        manifest_path: str,
    ) -> None:
        self.ensure_layout()
        if self.idempotency_path.is_file():
            data = _read_json(self.idempotency_path)
        else:
            data = {"keys": {}}
        keys = data.setdefault("keys", {})
        if not isinstance(keys, dict):
            keys = {}
            data["keys"] = keys
        keys[key] = {
            "doc_id": doc_id,
            "ingest_id": ingest_id,
            "manifest_path": manifest_path,
            "updated_at": utc_now_rfc3339(),
        }
        _atomic_write_json(self.idempotency_path, data)

    def write_dlq(
        self,
        ingest_id: str,
        *,
        job: IngestJob,
        manifest: IngestManifest | None,
        reason: str,
    ) -> Path:
        payload = {
            "ingest_id": ingest_id,
            "reason": reason,
            "job": job.model_dump(mode="json"),
            "manifest": (
                manifest.to_storage_dict() if manifest is not None else None
            ),
            "failed_at": utc_now_rfc3339(),
        }
        path = self.dlq_path(ingest_id)
        _atomic_write_json(path, payload)
        return path

    def list_dlq(self) -> list[Path]:
        if not self.dlq_dir.is_dir():
            return []
        return sorted(self.dlq_dir.glob("*.json"))

    def read_dlq(self, ingest_id: str) -> dict[str, Any] | None:
        path = self.dlq_path(ingest_id)
        if not path.is_file():
            return None
        return _read_json(path)
