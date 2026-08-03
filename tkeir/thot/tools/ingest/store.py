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
    """Atomically write a JSON object to ``path``.

    Example:
        >>> import tempfile, json
        >>> from pathlib import Path
        >>> with tempfile.TemporaryDirectory() as temp_dir:
        ...     target = Path(temp_dir) / "data.json"
        ...     _atomic_write_json(target, {"a": 1})
        ...     json.loads(target.read_text())["a"]
        1
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    os.replace(tmp, path)


def _read_json(path: Path) -> dict[str, Any]:
    """Load a JSON object from ``path``.

    Example:
        >>> import tempfile, json
        >>> from pathlib import Path
        >>> with tempfile.TemporaryDirectory() as temp_dir:
        ...     target = Path(temp_dir) / "data.json"
        ...     _ = target.write_text(json.dumps({"x": 1}), encoding="utf-8")
        ...     _read_json(target)["x"]
        1
    """
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
        """Create expected directories.

        Example:
            >>> import tempfile
            >>> from pathlib import Path
            >>> from thot.tools.ingest.store import IngestStore
            >>> with tempfile.TemporaryDirectory() as temp_dir:
            ...     store = IngestStore(Path(temp_dir))
            ...     store.ensure_layout()
            ...     store.jobs_dir.is_dir()
            True
        """
        self.staging_dir.mkdir(parents=True, exist_ok=True)
        self.jobs_dir.mkdir(parents=True, exist_ok=True)
        self.dlq_dir.mkdir(parents=True, exist_ok=True)
        if not self.idempotency_path.exists():
            _atomic_write_json(self.idempotency_path, {"keys": {}})

    def staging_path(self, doc_id: str) -> Path:
        """Return the staging directory for ``doc_id``.

        Example:
            >>> import tempfile
            >>> from pathlib import Path
            >>> from thot.tools.ingest.store import IngestStore
            >>> with tempfile.TemporaryDirectory() as temp_dir:
            ...     store = IngestStore(Path(temp_dir))
            ...     store.staging_path("doc1").name
            'doc1'
        """
        return self.staging_dir / doc_id

    def manifest_path(self, doc_id: str) -> Path:
        """Return the manifest JSON path for ``doc_id``.

        Example:
            >>> import tempfile
            >>> from pathlib import Path
            >>> from thot.tools.ingest.store import IngestStore
            >>> with tempfile.TemporaryDirectory() as temp_dir:
            ...     store = IngestStore(Path(temp_dir))
            ...     store.manifest_path("doc1").name
            'ingest.manifest.json'
        """
        return self.staging_path(doc_id) / "ingest.manifest.json"

    def analyzed_document_path(self, doc_id: str) -> Path:
        """Return the analyzed document JSON path for ``doc_id``.

        Example:
            >>> import tempfile
            >>> from pathlib import Path
            >>> from thot.tools.ingest.store import IngestStore
            >>> with tempfile.TemporaryDirectory() as temp_dir:
            ...     store = IngestStore(Path(temp_dir))
            ...     store.analyzed_document_path("doc1").name
            'analyzed_document.json'
        """
        return self.staging_path(doc_id) / "analyzed_document.json"

    def source_path(self, doc_id: str, filename: str) -> Path:
        """Return the staged source file path for ``doc_id`` / ``filename``.

        Example:
            >>> import tempfile
            >>> from pathlib import Path
            >>> from thot.tools.ingest.store import IngestStore
            >>> with tempfile.TemporaryDirectory() as temp_dir:
            ...     store = IngestStore(Path(temp_dir))
            ...     store.source_path("doc1", "upload.txt").name
            'upload.txt'
        """
        return self.staging_path(doc_id) / filename

    def source_ref_index_path(self) -> Path:
        """Return the source-ref index JSON path.

        Example:
            >>> import tempfile
            >>> from pathlib import Path
            >>> from thot.tools.ingest.store import IngestStore
            >>> with tempfile.TemporaryDirectory() as temp_dir:
            ...     store = IngestStore(Path(temp_dir))
            ...     store.source_ref_index_path().name
            'source_refs.json'
        """
        return self.root / "source_refs.json"

    def job_path(self, ingest_id: str) -> Path:
        """Return the job record path for ``ingest_id``.

        Example:
            >>> import tempfile
            >>> from pathlib import Path
            >>> from thot.tools.ingest.store import IngestStore
            >>> with tempfile.TemporaryDirectory() as temp_dir:
            ...     store = IngestStore(Path(temp_dir))
            ...     store.job_path("job-1").suffix
            '.json'
        """
        return self.jobs_dir / f"{ingest_id}.json"

    def dlq_path(self, ingest_id: str) -> Path:
        """Return the DLQ record path for ``ingest_id``.

        Example:
            >>> import tempfile
            >>> from pathlib import Path
            >>> from thot.tools.ingest.store import IngestStore
            >>> with tempfile.TemporaryDirectory() as temp_dir:
            ...     store = IngestStore(Path(temp_dir))
            ...     store.dlq_path("job-1").parent.name
            'dlq'
        """
        return self.dlq_dir / f"{ingest_id}.json"

    def write_manifest(self, manifest: IngestManifest) -> Path:
        """Persist an ingest manifest under staging.

        Example:
            >>> import tempfile
            >>> from pathlib import Path
            >>> from thot.tools.ingest.store import IngestStore
            >>> from thot.tools.ingest.models import IngestManifest, SourceInfo, EmbedderInfo, LineageInfo
            >>> from thot.action.models import utc_now_rfc3339
            >>> with tempfile.TemporaryDirectory() as temp_dir:
            ...     store = IngestStore(Path(temp_dir))
            ...     now = utc_now_rfc3339()
            ...     manifest = IngestManifest(
            ...         ingest_id="i1", correlation_id="c1", doc_id="d1",
            ...         source=SourceInfo(uri="u://x", filename="f.txt"),
            ...         pipeline_config_sha256="sha", embedder=EmbedderInfo(model="m", provider="p", sha256="e"),
            ...         created_at=now, lineage=LineageInfo(),
            ...     )
            ...     store.write_manifest(manifest).is_file()
            True
        """
        path = self.manifest_path(manifest.doc_id)
        _atomic_write_json(path, manifest.to_storage_dict())
        return path

    def read_manifest(self, doc_id: str) -> IngestManifest | None:
        """Load a manifest by ``doc_id`` (``None`` when missing).

        Example:
            >>> import tempfile
            >>> from pathlib import Path
            >>> from thot.tools.ingest.store import IngestStore
            >>> from thot.tools.ingest.models import IngestManifest, SourceInfo, EmbedderInfo, LineageInfo
            >>> from thot.action.models import utc_now_rfc3339
            >>> with tempfile.TemporaryDirectory() as temp_dir:
            ...     store = IngestStore(Path(temp_dir))
            ...     now = utc_now_rfc3339()
            ...     manifest = IngestManifest(
            ...         ingest_id="i1", correlation_id="c1", doc_id="d1",
            ...         source=SourceInfo(uri="u://x", filename="f.txt"),
            ...         pipeline_config_sha256="sha", embedder=EmbedderInfo(model="m", provider="p", sha256="e"),
            ...         created_at=now, lineage=LineageInfo(),
            ...     )
            ...     _ = store.write_manifest(manifest)
            ...     store.read_manifest("d1").doc_id
            'd1'
        """
        path = self.manifest_path(doc_id)
        if not path.is_file():
            return None
        return IngestManifest.model_validate(_read_json(path))

    def write_job(self, job: IngestJob) -> Path:
        """Persist an ingest job record.

        Example:
            >>> import tempfile
            >>> from pathlib import Path
            >>> from thot.tools.ingest.store import IngestStore
            >>> from thot.tools.ingest.models import IngestJob, IngestJobStatus
            >>> from thot.action.models import utc_now_rfc3339
            >>> with tempfile.TemporaryDirectory() as temp_dir:
            ...     store = IngestStore(Path(temp_dir))
            ...     now = utc_now_rfc3339()
            ...     job = IngestJob(ingest_id="i1", correlation_id="c1", status=IngestJobStatus.PENDING, created_at=now, updated_at=now)
            ...     store.write_job(job).is_file()
            True
        """
        path = self.job_path(job.ingest_id)
        _atomic_write_json(path, job.model_dump(mode="json"))
        return path

    def read_job(self, ingest_id: str) -> IngestJob | None:
        """Load a job by ``ingest_id`` (``None`` when missing).

        Example:
            >>> import tempfile
            >>> from pathlib import Path
            >>> from thot.tools.ingest.store import IngestStore
            >>> from thot.tools.ingest.models import IngestJob, IngestJobStatus
            >>> from thot.action.models import utc_now_rfc3339
            >>> with tempfile.TemporaryDirectory() as temp_dir:
            ...     store = IngestStore(Path(temp_dir))
            ...     now = utc_now_rfc3339()
            ...     job = IngestJob(ingest_id="i1", correlation_id="c1", status=IngestJobStatus.PENDING, created_at=now, updated_at=now)
            ...     _ = store.write_job(job)
            ...     store.read_job("i1").ingest_id
            'i1'
        """
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
        """Update fields on an existing job and persist it.

        Example:
            >>> import tempfile
            >>> from pathlib import Path
            >>> from thot.tools.ingest.store import IngestStore
            >>> from thot.tools.ingest.models import IngestJob, IngestJobStatus
            >>> from thot.action.models import utc_now_rfc3339
            >>> with tempfile.TemporaryDirectory() as temp_dir:
            ...     store = IngestStore(Path(temp_dir))
            ...     now = utc_now_rfc3339()
            ...     job = IngestJob(ingest_id="i1", correlation_id="c1", status=IngestJobStatus.PENDING, created_at=now, updated_at=now)
            ...     _ = store.write_job(job)
            ...     store.update_job("i1", status=IngestJobStatus.RUNNING).status.value
            'running'
        """
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
        """Write raw source bytes under ``staging/<doc_id>/``.

        Example:
            >>> import tempfile
            >>> from pathlib import Path
            >>> from thot.tools.ingest.store import IngestStore
            >>> with tempfile.TemporaryDirectory() as temp_dir:
            ...     store = IngestStore(Path(temp_dir))
            ...     path = store.stage_bytes("d1", b"hello", filename="a.txt")
            ...     path.read_bytes()
            b'hello'
        """
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
        """Persist analyzed pipeline JSON and optionally index ``source_ref``.

        Example:
            >>> import tempfile
            >>> from pathlib import Path
            >>> from thot.tools.ingest.store import IngestStore
            >>> with tempfile.TemporaryDirectory() as temp_dir:
            ...     store = IngestStore(Path(temp_dir))
            ...     path = store.write_analyzed_document("d1", {"title": "x"}, source_ref="s1")
            ...     path.is_file()
            True
        """
        path = self.analyzed_document_path(doc_id)
        _atomic_write_json(path, document)
        if source_ref:
            self.put_source_ref_record(source_ref, doc_id=doc_id)
        return path

    def read_analyzed_document(self, doc_id: str) -> dict[str, Any] | None:
        """Load analyzed pipeline JSON for ``doc_id``.

        Example:
            >>> import tempfile
            >>> from pathlib import Path
            >>> from thot.tools.ingest.store import IngestStore
            >>> with tempfile.TemporaryDirectory() as temp_dir:
            ...     store = IngestStore(Path(temp_dir))
            ...     _ = store.write_analyzed_document("d1", {"title": "x"})
            ...     store.read_analyzed_document("d1")["title"]
            'x'
        """
        path = self.analyzed_document_path(doc_id)
        if not path.is_file():
            return None
        return _read_json(path)

    def get_source_ref_record(self, source_ref: str) -> dict[str, Any] | None:
        """Look up a source-ref index entry.

        Example:
            >>> import tempfile
            >>> from pathlib import Path
            >>> from thot.tools.ingest.store import IngestStore
            >>> with tempfile.TemporaryDirectory() as temp_dir:
            ...     store = IngestStore(Path(temp_dir))
            ...     store.put_source_ref_record("s1", doc_id="d1")
            ...     store.get_source_ref_record("s1")["doc_id"]
            'd1'
        """
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
        """Map ``source_ref`` to ``doc_id`` in the source-ref index.

        Example:
            >>> import tempfile
            >>> from pathlib import Path
            >>> from thot.tools.ingest.store import IngestStore
            >>> with tempfile.TemporaryDirectory() as temp_dir:
            ...     store = IngestStore(Path(temp_dir))
            ...     store.put_source_ref_record("s1", doc_id="d1")
            ...     store.get_source_ref_record("s1") is not None
            True
        """
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
        """Load analyzed JSON via the source-ref index.

        Example:
            >>> import tempfile
            >>> from pathlib import Path
            >>> from thot.tools.ingest.store import IngestStore
            >>> with tempfile.TemporaryDirectory() as temp_dir:
            ...     store = IngestStore(Path(temp_dir))
            ...     _ = store.write_analyzed_document("d1", {"title": "x"}, source_ref="s1")
            ...     store.read_analyzed_document_by_source_ref("s1")["title"]
            'x'
        """
        record = self.get_source_ref_record(source_ref)
        if not record:
            return None
        doc_id = record.get("doc_id")
        if not isinstance(doc_id, str) or not doc_id.strip():
            return None
        return self.read_analyzed_document(doc_id.strip())

    def get_idempotency_record(self, key: str) -> dict[str, Any] | None:
        """Look up an idempotency record by key.

        Example:
            >>> import tempfile
            >>> from pathlib import Path
            >>> from thot.tools.ingest.store import IngestStore
            >>> with tempfile.TemporaryDirectory() as temp_dir:
            ...     store = IngestStore(Path(temp_dir))
            ...     store.get_idempotency_record("missing") is None
            True
        """
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
        """Record an idempotency key → job/manifest mapping.

        Example:
            >>> import tempfile
            >>> from pathlib import Path
            >>> from thot.tools.ingest.store import IngestStore
            >>> with tempfile.TemporaryDirectory() as temp_dir:
            ...     store = IngestStore(Path(temp_dir))
            ...     store.put_idempotency_record("k1", doc_id="d1", ingest_id="i1", manifest_path="m.json")
            ...     store.get_idempotency_record("k1")["doc_id"]
            'd1'
        """
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
        """Write a failed job payload to the DLQ.

        Example:
            >>> import tempfile
            >>> from pathlib import Path
            >>> from thot.tools.ingest.store import IngestStore
            >>> from thot.tools.ingest.models import IngestJob, IngestJobStatus
            >>> from thot.action.models import utc_now_rfc3339
            >>> with tempfile.TemporaryDirectory() as temp_dir:
            ...     store = IngestStore(Path(temp_dir))
            ...     now = utc_now_rfc3339()
            ...     job = IngestJob(ingest_id="i1", correlation_id="c1", status=IngestJobStatus.FAILED, created_at=now, updated_at=now)
            ...     store.write_dlq("i1", job=job, manifest=None, reason="err").is_file()
            True
        """
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
        """List DLQ JSON files.

        Example:
            >>> import tempfile
            >>> from pathlib import Path
            >>> from thot.tools.ingest.store import IngestStore
            >>> with tempfile.TemporaryDirectory() as temp_dir:
            ...     store = IngestStore(Path(temp_dir))
            ...     store.list_dlq()
            []
        """
        if not self.dlq_dir.is_dir():
            return []
        return sorted(self.dlq_dir.glob("*.json"))

    def read_dlq(self, ingest_id: str) -> dict[str, Any] | None:
        """Load one DLQ record by ``ingest_id``.

        Example:
            >>> import tempfile
            >>> from pathlib import Path
            >>> from thot.tools.ingest.store import IngestStore
            >>> from thot.tools.ingest.models import IngestJob, IngestJobStatus
            >>> from thot.action.models import utc_now_rfc3339
            >>> with tempfile.TemporaryDirectory() as temp_dir:
            ...     store = IngestStore(Path(temp_dir))
            ...     now = utc_now_rfc3339()
            ...     job = IngestJob(ingest_id="i1", correlation_id="c1", status=IngestJobStatus.FAILED, created_at=now, updated_at=now)
            ...     _ = store.write_dlq("i1", job=job, manifest=None, reason="err")
            ...     store.read_dlq("i1")["reason"]
            'err'
        """
        path = self.dlq_path(ingest_id)
        if not path.is_file():
            return None
        return _read_json(path)
